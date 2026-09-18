import pytest

from confidentai import ConfidentAI
from confidentai.api import (
    API_BASE_URL,
    API_BASE_URL_EU,
    ApiKeyKind,
)


def test_initializes_with_explicit_api_key():
    client = ConfidentAI(api_key="confident_us_org_abc")
    assert client.api_key == "confident_us_org_abc"
    assert client.base_url == API_BASE_URL


def test_initializes_from_env_var(monkeypatch):
    monkeypatch.setenv("CONFIDENT_ORG_API_KEY", "confident_us_org_fromenv")
    client = ConfidentAI()
    assert client.api_key == "confident_us_org_fromenv"


def test_missing_api_key_raises(clean_env):
    with pytest.raises(ValueError):
        ConfidentAI()


def test_base_url_override():
    client = ConfidentAI(api_key="k", base_url="https://example.test/api/")
    assert client.base_url == "https://example.test/api"


def test_base_url_from_env(monkeypatch):
    monkeypatch.setenv("CONFIDENT_BASE_URL", "https://from-env.test")
    client = ConfidentAI(api_key="k")
    assert client.base_url == "https://from-env.test"


def test_region_env_selects_base_url(monkeypatch):
    monkeypatch.delenv("CONFIDENT_BASE_URL", raising=False)
    monkeypatch.setenv("CONFIDENT_REGION", "EU")
    client = ConfidentAI(api_key="k")
    assert client.base_url == API_BASE_URL_EU


def test_region_inferred_from_api_key_prefix(monkeypatch):
    monkeypatch.delenv("CONFIDENT_BASE_URL", raising=False)
    monkeypatch.delenv("CONFIDENT_REGION", raising=False)
    client = ConfidentAI(api_key="confident_eu_org_xyz")
    assert client.base_url == API_BASE_URL_EU


def test_timeout_override():
    client = ConfidentAI(api_key="k", timeout=5.0)
    assert client.timeout == 5.0
    assert client._api(ApiKeyKind.ORGANIZATION).timeout == 5.0


def test_generated_clients_are_reachable(client):
    from confidentai.organization.client import OrganizationClient
    from confidentai.projects.client import ProjectsClient

    assert isinstance(client.organization, OrganizationClient)
    assert isinstance(client.projects, ProjectsClient)


def test_whoami_returns_organization(client, http):
    http.enqueue_data(
        {
            "id": "org_1",
            "name": "Acme",
            "plan": "TEAM",
            "created_at": "2026-01-01",
        }
    )
    org = client.whoami()
    assert org.id == "org_1"
    assert org.name == "Acme"
    assert http.last["url"].endswith("/v2/organization")
    assert http.last["method"] == "GET"
