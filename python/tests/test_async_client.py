"""Async method tests.

These mirror the sync suites but exercise the ``a_``-prefixed async methods on
the same ``ConfidentAI`` client (deepeval-style: one class exposes both ``foo``
and ``a_foo``). The async network seam (``Api._a_http_request``) is patched onto
the same ``RequestRecorder`` as the sync seam (see ``conftest.py``), so the
canned responses and request assertions are identical to the sync tests.
Coroutines are driven with ``asyncio.run`` to avoid a pytest-asyncio dependency.
"""

import asyncio

import pytest

from confidentai import ConfidentAI
from confidentai.types import ConfidentApiError


def run(coro):
    return asyncio.run(coro)


def test_factories_return_clients(async_client):
    from confidentai.organization.client import OrganizationClient
    from confidentai.projects.client import ProjectsClient

    assert isinstance(async_client.organization, OrganizationClient)
    assert isinstance(async_client.projects, ProjectsClient)


def test_client_constructs():
    client = ConfidentAI(api_key="confident_us_org_abc")
    assert client.api_key == "confident_us_org_abc"


def test_whoami(async_client, http):
    http.enqueue_data(
        {
            "id": "org_1",
            "name": "Acme",
            "plan": "TEAM",
            "created_at": "2026-01-01",
        }
    )
    org = run(async_client.a_whoami())
    assert org.id == "org_1"
    assert org.name == "Acme"
    assert http.last["method"] == "GET"
    assert http.last["url"].endswith("/v2/organization")


def test_error_envelope_raises_confident_api_error(async_client, http):
    http.enqueue_raw({"success": False, "error": "boom"})
    with pytest.raises(ConfidentApiError) as excinfo:
        run(async_client.a_whoami())
    assert str(excinfo.value) == "boom"
