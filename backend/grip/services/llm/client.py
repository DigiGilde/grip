"""A slim client for VLAM, the language model the government operates itself.

VLAM speaks the OpenAI-compatible API. The hosting platform delivers only an
address (``VLAM_API_URL``); the API key and the model are the instance's own
configuration. Which models exist is whatever ``/v1/models`` answers, so the
model id is configuration and never a constant in the code.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import Protocol

from openai import AsyncOpenAI

from grip.core.config import Settings, get_settings
from grip.core.rate_limit import KeyedLimiter, caller_key
from grip.services.llm.vlam_endpoint import resolve_vlam_base_url


class LlmNotConfiguredError(RuntimeError):
    """Drafting was asked for, but the instance has no language model set up."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(
            "Het taalmodel is niet geconfigureerd: "
            + ", ".join(missing)
            + " ontbreekt. Een concept opstellen kan pas als de beheerder "
            "dit heeft ingesteld."
        )


class LlmResponseError(RuntimeError):
    """The model answered, but not with usable text."""


class LlmBusyError(LlmResponseError):
    """Someone asked the model more often than one person reasonably does."""


# The model costs money and time per call, and nothing else in grip does. One
# person gets a generous number of drafts per hour, and the instance as a
# whole a ceiling, so that one session cannot spend the budget of all. In
# memory and per process, like the other limits (grip.core.rate_limit).
CALLS_PER_PERSON_PER_HOUR = 40
CALLS_PER_INSTANCE_PER_HOUR = 400
_per_person = KeyedLimiter(limit=CALLS_PER_PERSON_PER_HOUR, window=3600)
_per_instance = KeyedLimiter(limit=CALLS_PER_INSTANCE_PER_HOUR, window=3600)


def count_call() -> None:
    """Count one call to the model, or refuse it with ``LlmBusyError``."""
    if not _per_person.allow(caller_key()):
        raise LlmBusyError(
            "Je hebt het taalmodel het afgelopen uur vaak gebruikt. "
            "Probeer het later opnieuw."
        )
    if not _per_instance.allow("instance"):
        raise LlmBusyError(
            "Het taalmodel is het afgelopen uur veel gebruikt. "
            "Probeer het later opnieuw."
        )


def reset_call_counts() -> None:
    _per_person.reset()
    _per_instance.reset()


class ChatClient(Protocol):
    """What drafting needs from a language model."""

    @property
    def model_id(self) -> str: ...

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1500
    ) -> str: ...


class VlamClient:
    """VLAM through its OpenAI-compatible API."""

    provider = "vlam"

    def __init__(self, *, api_key: str, base_url: str, model_id: str) -> None:
        # A call that hangs holds a request open; two minutes is ample for
        # a draft, and one retry is enough for a hiccup.
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=120.0, max_retries=1
        )
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    async def complete(self, *, system: str, user: str, max_tokens: int = 1500) -> str:
        count_call()
        response = await self._client.chat.completions.create(
            model=self._model_id,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        if not response.choices:
            raise LlmResponseError("Het taalmodel gaf geen antwoord.")
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise LlmResponseError("Het taalmodel gaf een leeg antwoord.")
        return text

    async def list_models(self) -> list[str]:
        """The model ids this endpoint offers, for the beheerder to pick from."""
        page = await self._client.models.list()
        return sorted(model.id for model in page.data)


def vlam_missing_settings(settings: Settings) -> list[str]:
    """Names of the settings that still have to be filled in, if any."""
    missing: list[str] = []
    if not resolve_vlam_base_url(settings.VLAM_API_URL, settings.VLAM_BASE_URL):
        missing.append("VLAM_API_URL of VLAM_BASE_URL")
    if not settings.VLAM_API_KEY:
        missing.append("VLAM_API_KEY")
    if not settings.VLAM_MODEL_ID:
        missing.append("VLAM_MODEL_ID")
    return missing


PROVIDER_VLAM = "vlam"
PROVIDER_CLAUDE_CLI = "claude_cli"
PROVIDER_NONE = "none"

# Stored as the model of a draft, so a local draft can never pass as one of
# VLAM: "claude-cli:<model>".
CLI_MODEL_PREFIX = "claude-cli:"


class ClaudeCliClient:
    """The command-line tool on a developer's machine, as a model provider.

    Development only. It runs the tool as a subprocess in print mode with
    the person's own login: no key in grip, no tools, no stored session. The
    settings refuse this provider outside local development, and so does the
    constructor.
    """

    provider = PROVIDER_CLAUDE_CLI

    def __init__(self, *, command: str, model: str, timeout: float) -> None:
        self._command = command
        self._model = model
        self._timeout = timeout
        self._answered_model: str | None = None

    @property
    def model_id(self) -> str:
        return CLI_MODEL_PREFIX + (self._answered_model or self._model)

    def _arguments(self, system: str) -> list[str]:
        return [
            self._command,
            "--print",
            "--output-format",
            "json",
            "--tools",
            "",
            "--no-session-persistence",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--model",
            self._model,
            "--system-prompt",
            system,
        ]

    async def complete(self, *, system: str, user: str, max_tokens: int = 1500) -> str:
        if shutil.which(self._command) is None:
            raise LlmResponseError(
                "Het lokale ontwikkelmodel is niet gevonden: het commando "
                f"'{self._command}' staat niet op deze computer."
            )
        process = await asyncio.create_subprocess_exec(
            *self._arguments(system),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(
                process.communicate(user.encode("utf-8")), timeout=self._timeout
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise LlmResponseError(
                "Het lokale ontwikkelmodel gaf binnen "
                f"{int(self._timeout)} seconden geen antwoord."
            ) from exc
        return self._parse(
            out.decode("utf-8", "replace"), err.decode("utf-8", "replace")
        )

    async def list_models(self) -> list[str]:
        """The one model this provider is set to."""
        return [self.model_id]

    def _parse(self, out: str, err: str) -> str:
        try:
            answer = json.loads(out)
        except ValueError as exc:
            detail = (err or out).strip().splitlines()[-1:] or [""]
            if "login" in (err + out).lower():
                raise LlmResponseError(
                    "Het lokale ontwikkelmodel is niet ingelogd. Log in met het "
                    "commando zelf en probeer het opnieuw."
                ) from exc
            raise LlmResponseError(
                "Het lokale ontwikkelmodel gaf geen leesbaar antwoord. "
                + detail[0][:200]
            ) from exc
        if not isinstance(answer, dict) or answer.get("is_error"):
            text = str((answer or {}).get("result") or "")[:200]
            if "login" in text.lower() or "auth" in text.lower():
                raise LlmResponseError(
                    "Het lokale ontwikkelmodel is niet ingelogd. Log in met het "
                    "commando zelf en probeer het opnieuw."
                )
            raise LlmResponseError("Het lokale ontwikkelmodel gaf een fout. " + text)
        usage = answer.get("modelUsage")
        if isinstance(usage, dict) and usage:
            self._answered_model = next(iter(usage))
        text = str(answer.get("result") or "").strip()
        if not text:
            raise LlmResponseError("Het lokale ontwikkelmodel gaf een leeg antwoord.")
        return text


def active_provider(settings: Settings | None = None) -> str:
    """Which provider drafts: the setting, or VLAM when it is configured."""
    settings = settings or get_settings()
    chosen = settings.LLM_PROVIDER.strip().lower()
    if chosen == PROVIDER_NONE:
        return PROVIDER_NONE
    if chosen == PROVIDER_CLAUDE_CLI:
        # The settings refuse this outside local development; checked again
        # here because a Settings object can be built by hand.
        return PROVIDER_CLAUDE_CLI if settings.is_local_development else PROVIDER_NONE
    return PROVIDER_VLAM if not vlam_missing_settings(settings) else PROVIDER_NONE


def provider_label(model_id: str | None) -> str | None:
    """How a draft's origin reads, from the model id stored with it."""
    if not model_id:
        return None
    if model_id.startswith(CLI_MODEL_PREFIX):
        model = model_id[len(CLI_MODEL_PREFIX) :]
        return f"Claude via de lokale ontwikkelomgeving, {model}"
    return f"VLAM, {model_id}"


def is_llm_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    provider = active_provider(settings)
    if provider == PROVIDER_CLAUDE_CLI:
        return shutil.which(settings.CLAUDE_CLI_COMMAND) is not None
    return provider == PROVIDER_VLAM


def get_chat_client(settings: Settings | None = None) -> ChatClient:
    """Build the client, or raise a clear error when configuration is missing."""
    settings = settings or get_settings()
    if active_provider(settings) == PROVIDER_CLAUDE_CLI:
        return ClaudeCliClient(
            command=settings.CLAUDE_CLI_COMMAND,
            model=settings.CLAUDE_CLI_MODEL,
            timeout=float(settings.CLAUDE_CLI_TIMEOUT_SECONDS),
        )
    missing = vlam_missing_settings(settings)
    if missing or settings.LLM_PROVIDER.strip().lower() == PROVIDER_NONE:
        raise LlmNotConfiguredError(missing or ["LLM_PROVIDER"])
    return VlamClient(
        api_key=settings.VLAM_API_KEY,
        base_url=resolve_vlam_base_url(settings.VLAM_API_URL, settings.VLAM_BASE_URL),
        model_id=settings.VLAM_MODEL_ID,
    )
