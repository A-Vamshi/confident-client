import json as _json
import logging
import math
import os
from enum import Enum
from functools import lru_cache
from typing import Any, Mapping, Optional, Tuple, Union

import aiohttp
import requests
from pydantic import BaseModel, TypeAdapter
from tenacity import (
    retry,
    retry_if_exception_type,
    wait_exponential_jitter,
    RetryCallState,
)

from ._version import __version__
from .endpoints import Endpoints
from .types import ApiResponse, ConfidentApiError
from .utils.request import join_url, serialize_params

CONFIDENT_ORG_API_KEY_ENV_VAR = "CONFIDENT_ORG_API_KEY"
CONFIDENT_PROJ_API_KEY_ENV_VAR = "CONFIDENT_PROJ_API_KEY"
CONFIDENT_BASE_URL_ENV_VAR = "CONFIDENT_BASE_URL"
CONFIDENT_REGION_ENV_VAR = "CONFIDENT_REGION"

API_BASE_URL = "https://api.confident-ai.com"
API_BASE_URL_EU = "https://eu.api.confident-ai.com"

API_KEY_HEADER = "CONFIDENT_API_KEY"
SDK_VERSION_HEADER = "X-Confident-SDK-Version"

DEFAULT_TIMEOUT = 30.0

retryable_exceptions = requests.exceptions.SSLError
async_retryable_exceptions = (
    aiohttp.ClientConnectionError,
    aiohttp.ClientSSLError,
)


class ApiKeyKind(Enum):
    ORGANIZATION = "organization"
    PROJECT = "project"

    @property
    def env_var(self) -> str:
        return _API_KEY_ENV_VARS[self]

    @property
    def client_argument(self) -> str:
        return _API_KEY_CLIENT_ARGUMENTS[self]


_API_KEY_ENV_VARS = {
    ApiKeyKind.ORGANIZATION: CONFIDENT_ORG_API_KEY_ENV_VAR,
    ApiKeyKind.PROJECT: CONFIDENT_PROJ_API_KEY_ENV_VAR,
}

_API_KEY_CLIENT_ARGUMENTS = {
    ApiKeyKind.ORGANIZATION: "api_key",
    ApiKeyKind.PROJECT: "project_api_key",
}


def _infer_region_from_api_key(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    key = api_key.strip().lower()
    if key.startswith("confident_eu_"):
        return "EU"
    if key.startswith("confident_us_"):
        return "US"
    return None


def get_confident_api_key(
    api_key: Optional[str] = None,
    key_kind: ApiKeyKind = ApiKeyKind.ORGANIZATION,
) -> Optional[str]:
    if api_key:
        return api_key
    return os.getenv(key_kind.env_var) or None


def get_base_api_url(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> str:
    if base_url:
        return base_url.rstrip("/")

    env_base_url = os.getenv(CONFIDENT_BASE_URL_ENV_VAR)
    if env_base_url:
        return env_base_url.rstrip("/")

    region = os.getenv(CONFIDENT_REGION_ENV_VAR) or _infer_region_from_api_key(
        api_key
    )
    region = (region or "US").upper()
    if region == "EU":
        return API_BASE_URL_EU
    return API_BASE_URL


def log_retry_error(retry_state: RetryCallState):
    exception = retry_state.outcome.exception()
    logging.error(
        f"Confident AI Error: {exception}. Retrying: {retry_state.attempt_number} time(s)..."
    )


class HttpMethods(Enum):
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"
    PUT = "PUT"


def _sanitize_body(obj):
    """Recursively replace non-finite floats (NaN, Inf, -Inf) with None."""
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        return {k: _sanitize_body(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_body(v) for v in obj]
    return obj


@lru_cache(maxsize=None)
def _adapter(schema: Any) -> TypeAdapter:
    # Building a TypeAdapter compiles a validator, which is far too costly to redo on every call.
    return TypeAdapter(schema)


def _parse_body(schema: Optional[Any], body: Optional[Any]) -> Optional[Any]:
    if body is None:
        return None
    if schema is not None:
        body = _adapter(schema).validate_python(body)
    if isinstance(body, BaseModel):
        return body.model_dump(mode="json", by_alias=True, exclude_none=True)
    return body


class _AsyncResponse:
    """Response shim so ``a_send_request`` can reuse the sync handling path.

    Mirrors the parts of ``requests.Response`` that the response handling
    relies on: ``status_code``, ``json()`` (raising ``ValueError`` on a
    non-JSON body, like ``requests`` does), and ``text``.
    """

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        return _json.loads(self.text)


class Api:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        key_kind: ApiKeyKind = ApiKeyKind.ORGANIZATION,
    ) -> None:
        api_key = get_confident_api_key(api_key, key_kind)
        if not api_key:
            raise ValueError(
                f"No Confident AI {key_kind.value} API key found. Please set the "
                f"{key_kind.env_var} environment variable or pass "
                f"{key_kind.client_argument}."
            )

        self.key_kind = key_kind
        self.api_key = api_key
        self.base_url = get_base_api_url(api_key, base_url)
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self._headers = {
            "Content-Type": "application/json",
            API_KEY_HEADER: api_key,
            SDK_VERSION_HEADER: f"confidentai-python/{__version__}",
        }

    @staticmethod
    @retry(
        wait=wait_exponential_jitter(initial=1, exp_base=2, jitter=2, max=10),
        retry=retry_if_exception_type(retryable_exceptions),
        after=log_retry_error,
    )
    def _http_request(
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Optional[Mapping[str, Any]],
        json: Optional[Any],
        timeout: float,
    ) -> requests.Response:
        session = requests.Session()
        return session.request(
            method=method,
            url=url,
            headers=dict(headers),
            params=params,
            json=json,
            timeout=timeout,
            verify=True,
        )

    def _handle_response(
        self, response_data: Union[dict, Any]
    ) -> Tuple[Any, Optional[str]]:
        if not isinstance(response_data, dict):
            return response_data, None

        try:
            api_response = ApiResponse(**response_data)
        except Exception:
            return response_data, None

        if api_response.deprecated:
            deprecation_msg = "You are using a deprecated API endpoint. Please update your confidentai version."
            if api_response.link:
                deprecation_msg += f" See: {api_response.link}"
            logging.warning(deprecation_msg)

        if not api_response.success:
            error_message = api_response.error or "Request failed"
            raise ConfidentApiError(error_message, api_response.link)

        return api_response.data, api_response.link

    def _format_url(
        self, endpoint: Endpoints, path: Optional[Mapping[str, Any]]
    ) -> str:
        route = endpoint.value
        for key, value in (path or {}).items():
            route = route.replace(f":{key}", str(value))
        return join_url(self.base_url, route)

    def _parse_response(self, res: Any) -> Tuple[Any, Optional[str]]:
        if res.status_code == 200:
            try:
                return self._handle_response(res.json())
            except ValueError:
                return res.text, None
        try:
            payload = res.json()
        except ValueError:
            raise Exception(res.text) from None
        return self._handle_response(payload)

    def send_request(
        self,
        method: HttpMethods,
        endpoint: Endpoints,
        body=None,
        params=None,
        url_params=None,
    ) -> Tuple[Any, Optional[str]]:
        res = self._http_request(
            method.value,
            self._format_url(endpoint, url_params),
            self._headers,
            serialize_params(params),
            None if body is None else _sanitize_body(body),
            self.timeout,
        )
        return self._parse_response(res)

    def request(
        self,
        method: HttpMethods,
        endpoint: Endpoints,
        *,
        response_schema: Any,
        request_schema: Optional[Any] = None,
        body: Optional[Any] = None,
        path: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """Call one endpoint and return its payload as ``response_schema``.

        The envelope is unwrapped before validation, so the value returned is
        the endpoint's ``data`` and never the envelope around it.
        """
        data, _ = self.send_request(
            method,
            endpoint,
            body=_parse_body(request_schema, body),
            params=query,
            url_params=path,
        )
        return _adapter(response_schema).validate_python(data)

    @staticmethod
    @retry(
        wait=wait_exponential_jitter(initial=1, exp_base=2, jitter=2, max=10),
        retry=retry_if_exception_type(async_retryable_exceptions),
        after=log_retry_error,
    )
    async def _a_http_request(
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Optional[Mapping[str, Any]],
        json: Optional[Any],
        timeout: float,
    ) -> _AsyncResponse:
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=url,
                headers=dict(headers),
                json=json,
                params=params,
                ssl=True,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as res:
                return _AsyncResponse(res.status, await res.text())

    async def a_send_request(
        self,
        method: HttpMethods,
        endpoint: Endpoints,
        body=None,
        params=None,
        url_params=None,
    ) -> Tuple[Any, Optional[str]]:
        res = await self._a_http_request(
            method.value,
            self._format_url(endpoint, url_params),
            self._headers,
            serialize_params(params),
            None if body is None else _sanitize_body(body),
            self.timeout,
        )
        return self._parse_response(res)

    async def a_request(
        self,
        method: HttpMethods,
        endpoint: Endpoints,
        *,
        response_schema: Any,
        request_schema: Optional[Any] = None,
        body: Optional[Any] = None,
        path: Optional[Mapping[str, Any]] = None,
        query: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """Call one endpoint and return its payload as ``response_schema``.

        The envelope is unwrapped before validation, so the value returned is
        the endpoint's ``data`` and never the envelope around it.
        """
        data, _ = await self.a_send_request(
            method,
            endpoint,
            body=_parse_body(request_schema, body),
            params=query,
            url_params=path,
        )
        return _adapter(response_schema).validate_python(data)
