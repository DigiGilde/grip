"""The language model client: configuration, or a clear error."""

from __future__ import annotations

import pytest

from grip.core.config import Settings
from grip.services.llm import (
    LlmNotConfiguredError,
    VlamClient,
    get_chat_client,
    is_llm_configured,
    vlam_missing_settings,
)


def _settings(**overrides) -> Settings:
    values = {
        "DEV_NO_AUTH": True,
        "VLAM_API_URL": "",
        "VLAM_BASE_URL": "",
        "VLAM_API_KEY": "",
        "VLAM_MODEL_ID": "",
    }
    return Settings(_env_file=None, **(values | overrides))


def test_nothing_configured_names_everything_that_is_missing():
    settings = _settings()
    assert not is_llm_configured(settings)
    assert vlam_missing_settings(settings) == [
        "VLAM_API_URL of VLAM_BASE_URL",
        "VLAM_API_KEY",
        "VLAM_MODEL_ID",
    ]
    with pytest.raises(LlmNotConfiguredError) as raised:
        get_chat_client(settings)
    assert "niet geconfigureerd" in str(raised.value)
    assert "VLAM_MODEL_ID" in str(raised.value)


def test_model_is_configuration_and_never_a_default():
    settings = _settings(VLAM_API_URL="http://proxy.example:8081", VLAM_API_KEY="k")
    assert vlam_missing_settings(settings) == ["VLAM_MODEL_ID"]


def test_configured_client_uses_the_platform_address_and_the_model():
    settings = _settings(
        VLAM_API_URL="http://proxy.example:8081",
        VLAM_BASE_URL="https://old.example/v1",
        VLAM_API_KEY="k",
        VLAM_MODEL_ID="een-model",
    )
    client = get_chat_client(settings)
    assert isinstance(client, VlamClient)
    assert client.model_id == "een-model"
    assert str(client._client.base_url).rstrip("/") == "http://proxy.example:8081/v1"
