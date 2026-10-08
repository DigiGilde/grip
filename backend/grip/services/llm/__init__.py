"""Access to the language model, behind one service layer."""

from grip.services.llm.client import (
    ChatClient,
    LlmNotConfiguredError,
    LlmResponseError,
    VlamClient,
    get_chat_client,
    is_llm_configured,
    vlam_missing_settings,
)
from grip.services.llm.vlam_endpoint import (
    normalize_vlam_base_url,
    resolve_vlam_base_url,
)

__all__ = [
    "ChatClient",
    "LlmNotConfiguredError",
    "LlmResponseError",
    "VlamClient",
    "get_chat_client",
    "is_llm_configured",
    "normalize_vlam_base_url",
    "resolve_vlam_base_url",
    "vlam_missing_settings",
]
