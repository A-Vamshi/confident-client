import pytest

from confidentai import ConfidentAI
from confidentai.api import (
    API_BASE_URL_EU,
    API_KEY_HEADER,
    CONFIDENT_ORG_API_KEY_ENV_VAR,
    CONFIDENT_PROJ_API_KEY_ENV_VAR,
    Api,
    ApiKeyKind,
    Endpoints,
    HttpMethods,
)


def test_each_key_kind_names_its_env_var():
    assert ApiKeyKind.ORGANIZATION.env_var == CONFIDENT_ORG_API_KEY_ENV_VAR
    assert ApiKeyKind.PROJECT.env_var == CONFIDENT_PROJ_API_KEY_ENV_VAR


def test_each_key_kind_names_its_client_argument():
    assert ApiKeyKind.ORGANIZATION.client_argument == "api_key"
    assert ApiKeyKind.PROJECT.client_argument == "project_api_key"


def test_project_key_resolves_from_its_env_var(clean_env, monkeypatch):
    monkeypatch.setenv(CONFIDENT_PROJ_API_KEY_ENV_VAR, "confident_us_proj_env")
    client = ConfidentAI()
    assert client.project_api_key == "confident_us_proj_env"
    assert client.api_key is None


def test_explicit_project_key_beats_its_env_var(clean_env, monkeypatch):
    monkeypatch.setenv(CONFIDENT_PROJ_API_KEY_ENV_VAR, "confident_us_proj_env")
    client = ConfidentAI(project_api_key="confident_us_proj_explicit")
    assert client.project_api_key == "confident_us_proj_explicit"


def test_organization_env_var_never_supplies_a_project_key(
    clean_env, monkeypatch
):
    monkeypatch.setenv(CONFIDENT_ORG_API_KEY_ENV_VAR, "confident_us_org_env")
    client = ConfidentAI()
    assert client.api_key == "confident_us_org_env"
    assert client.project_api_key is None


def test_project_env_var_never_supplies_an_organization_key(
    clean_env, monkeypatch
):
    monkeypatch.setenv(CONFIDENT_PROJ_API_KEY_ENV_VAR, "confident_us_proj_env")
    client = ConfidentAI()
    assert client.project_api_key == "confident_us_proj_env"
    assert client.api_key is None


def test_project_key_alone_builds_a_client(clean_env):
    client = ConfidentAI(project_api_key="confident_us_proj_abc")
    assert client.project_api_key == "confident_us_proj_abc"


def test_no_key_at_all_names_both_env_vars(clean_env):
    with pytest.raises(ValueError) as excinfo:
        ConfidentAI()
    message = str(excinfo.value)
    assert CONFIDENT_ORG_API_KEY_ENV_VAR in message
    assert CONFIDENT_PROJ_API_KEY_ENV_VAR in message


def test_management_access_without_an_organization_key_names_it(clean_env):
    client = ConfidentAI(project_api_key="confident_us_proj_abc")
    with pytest.raises(ValueError) as excinfo:
        client.organization()
    message = str(excinfo.value)
    assert CONFIDENT_ORG_API_KEY_ENV_VAR in message
    assert ApiKeyKind.ORGANIZATION.client_argument in message


def test_project_access_without_a_project_key_names_it(clean_env):
    client = ConfidentAI(api_key="confident_us_org_abc")
    with pytest.raises(ValueError) as excinfo:
        client._api(ApiKeyKind.PROJECT)
    message = str(excinfo.value)
    assert CONFIDENT_PROJ_API_KEY_ENV_VAR in message
    assert ApiKeyKind.PROJECT.client_argument in message


def test_each_key_kind_gets_its_own_cached_api(clean_env):
    client = ConfidentAI(
        api_key="confident_us_org_abc",
        project_api_key="confident_us_proj_abc",
    )
    organization_api = client._api(ApiKeyKind.ORGANIZATION)
    project_api = client._api(ApiKeyKind.PROJECT)

    assert organization_api is not project_api
    assert organization_api is client._api(ApiKeyKind.ORGANIZATION)
    assert project_api is client._api(ApiKeyKind.PROJECT)
    assert organization_api.api_key == "confident_us_org_abc"
    assert project_api.api_key == "confident_us_proj_abc"


def test_project_key_is_sent_as_the_request_credential(clean_env, http):
    api = Api(api_key="confident_us_proj_abc", key_kind=ApiKeyKind.PROJECT)
    api.send_request(HttpMethods.GET, Endpoints.ORGANIZATION_ENDPOINT)
    assert http.last["headers"][API_KEY_HEADER] == "confident_us_proj_abc"


def test_region_is_inferred_from_the_project_key(clean_env):
    client = ConfidentAI(project_api_key="confident_eu_proj_abc")
    assert client.base_url == API_BASE_URL_EU


def test_api_defaults_to_the_organization_kind(clean_env, monkeypatch):
    monkeypatch.setenv(CONFIDENT_ORG_API_KEY_ENV_VAR, "confident_us_org_env")
    api = Api()
    assert api.key_kind is ApiKeyKind.ORGANIZATION
    assert api.api_key == "confident_us_org_env"
