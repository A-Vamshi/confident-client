from typing import Dict, Optional

from .api import (
    DEFAULT_TIMEOUT,
    Api,
    ApiKeyKind,
    get_base_api_url,
    get_confident_api_key,
)
from .organization import OrganizationClient
from .prompts import Prompt, Prompts
from .projects import ProjectClient, ProjectsClient
from .types import Organization


class ConfidentAI:
    def __init__(
        self,
        api_key: Optional[str] = None,
        project_api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._api_keys: Dict[ApiKeyKind, Optional[str]] = {
            ApiKeyKind.ORGANIZATION: api_key,
            ApiKeyKind.PROJECT: project_api_key,
        }
        self._base_url = base_url
        self._timeout = timeout
        self._apis: Dict[ApiKeyKind, Api] = {}

        if not any(self._resolve(key_kind) for key_kind in ApiKeyKind):
            raise ValueError(
                "No Confident AI API key found. Please set "
                f"{ApiKeyKind.ORGANIZATION.env_var} for organization management "
                f"or {ApiKeyKind.PROJECT.env_var} for project resources, or "
                f"pass {ApiKeyKind.ORGANIZATION.client_argument} / "
                f"{ApiKeyKind.PROJECT.client_argument} explicitly."
            )

    def _resolve(self, key_kind: ApiKeyKind) -> Optional[str]:
        return get_confident_api_key(self._api_keys[key_kind], key_kind)

    def _api(self, key_kind: ApiKeyKind) -> Api:
        if key_kind not in self._apis:
            self._apis[key_kind] = Api(
                api_key=self._api_keys[key_kind],
                base_url=self._base_url,
                timeout=self._timeout,
                key_kind=key_kind,
            )
        return self._apis[key_kind]

    @property
    def api_key(self) -> Optional[str]:
        return self._resolve(ApiKeyKind.ORGANIZATION)

    @property
    def project_api_key(self) -> Optional[str]:
        return self._resolve(ApiKeyKind.PROJECT)

    @property
    def base_url(self) -> str:
        return get_base_api_url(
            self.api_key or self.project_api_key, self._base_url
        )

    @property
    def timeout(self) -> float:
        return self._timeout if self._timeout is not None else DEFAULT_TIMEOUT

    @property
    def projects(self) -> ProjectsClient:
        return ProjectsClient(self._api(ApiKeyKind.ORGANIZATION))

    ##################################
    ###### STATELESS  ################
    ##################################
    @property
    def prompts(self) -> Prompts:
        """
        This one can be used to just call the API via different methods:
            - client.prompts.push(...)
            - client.prompts.pull(...)
            - client.prompts.list_versions(...)
        """
        return Prompts(self._api(ApiKeyKind.PROJECT))

    ##################################
    ###### STATEFULL #################
    ##################################

    def prompt(self, alias: str) -> Prompt:
        """
        This one can be used to hold an object in memory, mutate and use methods on instance:
            - prompt = client.prompt(alias="new-prompt-1")
                - prompt.text = "..."
                - prompt.interpolation_type = ...
            - prompt.push()
            - prompt.pull(...)
            - prompt.list_versions(...)
        """
        return Prompt(self._api(ApiKeyKind.PROJECT), alias)

    def organization(self) -> OrganizationClient:
        return OrganizationClient(self._api(ApiKeyKind.ORGANIZATION))

    def project(self, project_id: str) -> ProjectClient:
        return ProjectClient(self._api(ApiKeyKind.ORGANIZATION), project_id)

    def whoami(self) -> Organization:
        return self.organization().get()

    async def a_whoami(self) -> Organization:
        return await self.organization().a_get()
