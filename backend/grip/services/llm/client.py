"""A slim client for VLAM, the language model the government operates itself.

VLAM speaks the OpenAI-compatible API. The hosting platform delivers only an
address (``VLAM_API_URL``); the API key and the model are the instance's own
configuration. Which models exist is whatever ``/v1/models`` answers, so the
model id is configuration and never a constant in the code.
"""

from __future__ import annotations

from typing import Protocol

from openai import AsyncOpenAI

from grip.core.config import Settings, get_settings
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


class ChatClient(Protocol):
    """What drafting needs from a language model."""

    @property
    def model_id(self) -> str: ...

    async def complete(
        self, *, system: str, user: str, max_tokens: int = 1500
    ) -> str: ...


class VlamClient:
    """VLAM through its OpenAI-compatible API."""

    def __init__(self, *, api_key: str, base_url: str, model_id: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    async def complete(self, *, system: str, user: str, max_tokens: int = 1500) -> str:
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


def is_llm_configured(settings: Settings | None = None) -> bool:
    return not vlam_missing_settings(settings or get_settings())


def get_chat_client(settings: Settings | None = None) -> VlamClient:
    """Build the client, or raise a clear error when configuration is missing."""
    settings = settings or get_settings()
    missing = vlam_missing_settings(settings)
    if missing:
        raise LlmNotConfiguredError(missing)
    return VlamClient(
        api_key=settings.VLAM_API_KEY,
        base_url=resolve_vlam_base_url(settings.VLAM_API_URL, settings.VLAM_BASE_URL),
        model_id=settings.VLAM_MODEL_ID,
    )
