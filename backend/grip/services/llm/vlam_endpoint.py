"""Resolve the VLAM base address from platform or manual configuration.

There are two ways grip reaches VLAM, and they deliver the address in a
different shape:

1. The hosting platform's ``vlam`` service (deployed). The platform injects
   ``VLAM_API_URL`` with the address of an internal proxy, as a base address
   without a path. That proxy sets up the verified TLS session to VLAM
   itself, so the container does not need to trust an extra CA certificate.
2. A manual address (``VLAM_BASE_URL``), for local work or a direct endpoint.
   That one is usually given with a path, including ``/v1``.

The OpenAI client appends ``/chat/completions`` to the ``base_url``, so it
must contain exactly one ``/v1``. One too many or too few is a 404 that looks
like an outage in the logs. Hence one function with tests around it instead
of a string operation at the call site.

Ported from Bouwmeester.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# The path segment the OpenAI-compatible API expects. The client appends
# ``/chat/completions`` or ``/models`` itself.
_OPENAI_PATH_SUFFIX = "v1"


def normalize_vlam_base_url(raw: str | None) -> str:
    """Turn ``raw`` into a ``base_url`` the OpenAI client can use.

    The result ends in exactly one ``/v1``, whether or not the source already
    had the path. Empty or unusable input gives an empty string, so the caller
    can treat that as "not configured".

    >>> normalize_vlam_base_url("http://proxy.svc.cluster.local:8081")
    'http://proxy.svc.cluster.local:8081/v1'
    >>> normalize_vlam_base_url("https://vlam.example/v1/")
    'https://vlam.example/v1'
    """
    url = (raw or "").strip()
    if not url:
        return ""

    # Without a scheme urlsplit finds no host and everything lands in the
    # path; that is not a usable address.
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""

    path = parts.path.rstrip("/")
    segments = [s for s in path.split("/") if s]
    # Compare case-insensitively: an address ending in ``/V1`` would get a
    # second ``/v1`` otherwise.
    if not segments or segments[-1].lower() != _OPENAI_PATH_SUFFIX:
        segments.append(_OPENAI_PATH_SUFFIX)

    rebuilt_path = "/" + "/".join(segments)
    return f"{parts.scheme}://{parts.netloc}{rebuilt_path}"


def resolve_vlam_base_url(platform_url: str | None, manual_url: str | None) -> str:
    """Choose between the platform address and a manual address.

    The platform address wins: the platform derives it from the cluster
    configuration and keeps it in step with the network rule that allows the
    traffic. A manual value can linger after an endpoint has moved.
    """
    return normalize_vlam_base_url(platform_url) or normalize_vlam_base_url(manual_url)
