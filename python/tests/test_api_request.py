"""The typed request layer: what it sends, and what it hands back.

``Api.request`` is the single seam every generated client calls, so these
cover the transforms it owns — body validation and dumping, query
serialization, path substitution, and response validation.
"""

import asyncio
from enum import Enum

import pytest

from confidentai.api import Api, HttpMethods
from confidentai.endpoints import Endpoints
from confidentai.transformers.types import (
    CreateTransformerRequest,
    TransformerCodeRunFailure,
    TransformerCodeRunResult,
    TransformerCodeRunSuccess,
    TransformerLanguage,
    TransformerRef,
)
from confidentai.types import ConfidentApiError


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def api(clean_env, http):
    return Api(api_key="confident_us_org_testkey")


def test_returns_the_payload_as_the_response_schema(api, http):
    http.enqueue_data({"id": "t_1"})

    result = api.request(
        HttpMethods.GET,
        Endpoints.PROJECTS_ENDPOINT,
        response_schema=TransformerRef,
    )

    assert isinstance(result, TransformerRef)
    assert result.id == "t_1"


def test_unwraps_the_envelope(api, http):
    http.enqueue_raw(
        {"success": True, "data": {"id": "t_1"}, "deprecated": False}
    )

    result = api.request(
        HttpMethods.GET,
        Endpoints.PROJECTS_ENDPOINT,
        response_schema=TransformerRef,
    )

    assert result == TransformerRef(id="t_1")


def test_validates_into_the_matching_branch_of_a_union(api, http):
    http.enqueue_data({"success": True, "output": 42, "verboseLogs": None})

    result = api.request(
        HttpMethods.POST,
        Endpoints.PROJECTS_ENDPOINT,
        response_schema=TransformerCodeRunResult,
    )

    assert isinstance(result, TransformerCodeRunSuccess)
    assert result.output == 42


def test_validates_into_the_other_branch_of_a_union(api, http):
    http.enqueue_data(
        {
            "success": False,
            "error": "boom",
            "reason": "SyntaxError",
            "verboseLogs": None,
        }
    )

    result = api.request(
        HttpMethods.POST,
        Endpoints.PROJECTS_ENDPOINT,
        response_schema=TransformerCodeRunResult,
    )

    assert isinstance(result, TransformerCodeRunFailure)
    assert result.error == "boom"


def test_body_is_dumped_by_alias_without_unset_fields(api, http):
    http.enqueue_data({"id": "t_1"})

    api.request(
        HttpMethods.POST,
        Endpoints.PROJECTS_ENDPOINT,
        response_schema=TransformerRef,
        request_schema=CreateTransformerRequest,
        body=CreateTransformerRequest(
            name="strip",
            code_definition={
                "code": "x",
                "language": TransformerLanguage.PYTHON,
            },
        ),
    )

    assert http.last["json"] == {
        "name": "strip",
        "codeDefinition": {"code": "x", "language": "PYTHON"},
    }


def test_a_plain_dict_body_is_coerced_through_the_request_schema(api, http):
    http.enqueue_data({"id": "t_1"})

    api.request(
        HttpMethods.POST,
        Endpoints.PROJECTS_ENDPOINT,
        response_schema=TransformerRef,
        request_schema=CreateTransformerRequest,
        body={
            "name": "strip",
            "codeDefinition": {"code": "x", "language": "PYTHON"},
        },
    )

    assert http.last["json"] == {
        "name": "strip",
        "codeDefinition": {"code": "x", "language": "PYTHON"},
    }


def test_an_invalid_body_is_refused_before_any_request(api, http):
    with pytest.raises(Exception):
        api.request(
            HttpMethods.POST,
            Endpoints.PROJECTS_ENDPOINT,
            response_schema=TransformerRef,
            request_schema=CreateTransformerRequest,
            body={"name": "strip"},
        )

    assert http.calls == []


def test_path_parameters_are_substituted(api, http):
    http.enqueue_data({"id": "t_1"})

    api.request(
        HttpMethods.GET,
        Endpoints.PROJECT_API_KEY_ENDPOINT,
        response_schema=TransformerRef,
        path={"projectId": "p_1", "apiKeyId": "k_2"},
    )

    assert http.last["url"].endswith("/v2/projects/p_1/api-keys/k_2")


def test_query_values_are_serialized_for_the_wire(api, http):
    class Sort(Enum):
        CREATED_AT = "createdAt"

    http.enqueue_data({"id": "t_1"})

    api.request(
        HttpMethods.GET,
        Endpoints.PROJECTS_ENDPOINT,
        response_schema=TransformerRef,
        query={
            "page": 1,
            "cursor": None,
            "sortBy": Sort.CREATED_AT,
            "ascending": True,
            "metadata": {"client": "acme", "skipped": None},
        },
    )

    assert http.last["params"] == {
        "page": 1,
        "sortBy": "createdAt",
        "ascending": "true",
        "metadata[client]": "acme",
    }


def test_an_unsuccessful_envelope_raises(api, http):
    http.enqueue_raw({"success": False, "error": "nope"})

    with pytest.raises(ConfidentApiError, match="nope"):
        api.request(
            HttpMethods.GET,
            Endpoints.PROJECTS_ENDPOINT,
            response_schema=TransformerRef,
        )


def test_a_request_mirrors_request(api, http):
    http.enqueue_data({"id": "t_1"})

    result = run(
        api.a_request(
            HttpMethods.GET,
            Endpoints.PROJECTS_ENDPOINT,
            response_schema=TransformerRef,
        )
    )

    assert result == TransformerRef(id="t_1")


def test_a_request_sends_the_same_body(api, http):
    http.enqueue_data({"id": "t_1"})

    run(
        api.a_request(
            HttpMethods.POST,
            Endpoints.PROJECTS_ENDPOINT,
            response_schema=TransformerRef,
            request_schema=CreateTransformerRequest,
            body=CreateTransformerRequest(
                name="strip",
                code_definition={
                    "code": "x",
                    "language": TransformerLanguage.PYTHON,
                },
            ),
        )
    )

    assert http.last["json"] == {
        "name": "strip",
        "codeDefinition": {"code": "x", "language": "PYTHON"},
    }


def test_a_generated_v2_endpoint_routes_through_request(api, http):
    http.enqueue_data({"id": "t_1"})

    api.request(
        HttpMethods.POST,
        Endpoints.TRANSFORMER_TEST_CODE_ENDPOINT,
        response_schema=TransformerRef,
        path={"transformerId": "t_1"},
    )

    assert http.last["url"].endswith("/v2/transformers/t_1/test-code")
