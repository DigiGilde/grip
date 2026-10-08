"""The VLAM base address: exactly one /v1, platform before manual."""

from __future__ import annotations

import pytest

from grip.services.llm.vlam_endpoint import (
    normalize_vlam_base_url,
    resolve_vlam_base_url,
)

# The shape the hosting platform injects: a base address without a path.
PLATFORM_URL = "http://vlam-proxy-intern.example-namespace.svc.cluster.local:8081"


class TestNormalize:
    def test_platform_address_gets_v1(self):
        assert normalize_vlam_base_url(PLATFORM_URL) == f"{PLATFORM_URL}/v1"

    def test_existing_v1_is_not_doubled(self):
        assert (
            normalize_vlam_base_url("https://vlam.example/v1")
            == "https://vlam.example/v1"
        )

    def test_trailing_slash_disappears(self):
        assert (
            normalize_vlam_base_url("https://vlam.example/v1/")
            == "https://vlam.example/v1"
        )

    def test_longer_path_is_kept(self):
        raw = "https://api.vlam.example/v2.1/projects/poc/openai-compatible/v1"
        assert normalize_vlam_base_url(raw) == raw

    def test_longer_path_without_v1_gets_v1(self):
        raw = "https://api.vlam.example/v2.1/projects/poc/openai-compatible"
        assert normalize_vlam_base_url(raw) == f"{raw}/v1"

    def test_uppercase_v1_is_not_doubled(self):
        assert (
            normalize_vlam_base_url("https://vlam.example/V1")
            == "https://vlam.example/V1"
        )

    def test_v1_inside_a_longer_segment_does_not_count(self):
        assert normalize_vlam_base_url("https://h/apiv1") == "https://h/apiv1/v1"
        assert normalize_vlam_base_url("https://h/v10") == "https://h/v10/v1"

    def test_query_and_fragment_disappear(self):
        assert normalize_vlam_base_url("https://h/v1?x=1#f") == "https://h/v1"

    def test_surrounding_spaces_do_not_matter(self):
        assert normalize_vlam_base_url(f"  {PLATFORM_URL}  ") == f"{PLATFORM_URL}/v1"

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_stays_empty(self, raw):
        assert normalize_vlam_base_url(raw) == ""

    @pytest.mark.parametrize("raw", ["vlam.example", "/v1", "not a url"])
    def test_unusable_address_gives_empty(self, raw):
        assert normalize_vlam_base_url(raw) == ""


class TestResolve:
    def test_platform_wins_over_manual(self):
        resolved = resolve_vlam_base_url(PLATFORM_URL, "https://old.example/x/v1")
        assert resolved == f"{PLATFORM_URL}/v1"

    def test_manual_when_platform_is_missing(self):
        manual = "https://vlam.example/v1"
        assert resolve_vlam_base_url("", manual) == manual

    def test_unusable_platform_address_falls_back(self):
        manual = "https://vlam.example/v1"
        assert resolve_vlam_base_url("not a url", manual) == manual

    def test_neither_gives_empty(self):
        assert resolve_vlam_base_url("", "") == ""
