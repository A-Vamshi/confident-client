from typing import Any, Dict, List, Optional, Tuple

from confidentai.api import Api, Endpoints, HttpMethods
from .types import (
    CreatePromptVersionResult,
    ModelSettings,
    OutputSchema,
    PromptBranch,
    PromptBranchList,
    PromptCommit,
    PromptCommitList,
    PromptInterpolationType,
    PromptMessage,
    PromptOutputType,
    PromptType,
    PromptVersions,
    PushPromptRequest,
    PushPromptResult,
    Tool,
)
from .types import Prompt as PromptPayload
from .utils import Interpolated, interpolate

_SELECTORS = ("label", "version", "commit")
LATEST_COMMIT = "latest"


class Prompt:
    def __init__(self, api: Api, alias: str) -> None:
        self._api = api
        self.alias = alias

        self.id: Optional[str] = None
        self.hash: Optional[str] = None
        self.version: Optional[str] = None
        self.label: Optional[str] = None
        self.type: Optional[PromptType] = None
        self.text: Optional[str] = None
        self.messages: Optional[List[PromptMessage]] = None
        self.interpolation_type: Optional[PromptInterpolationType] = None
        self.model_settings: Optional[ModelSettings] = None
        self.output_type: Optional[PromptOutputType] = None
        self.output_schema: Optional[OutputSchema] = None
        self.tools: Optional[List[Tool]] = None

    def __repr__(self) -> str:
        state = "empty" if self.type is None else f"version={self.version}"
        return f"Prompt(alias={self.alias!r}, {state})"

    def pull(
        self,
        *,
        label: Optional[str] = None,
        version: Optional[str] = None,
        commit: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> "Prompt":
        endpoint, selector = self._resolve_pull_endpoint(label, version, commit)
        data, _ = self._api.send_request(
            HttpMethods.GET,
            endpoint,
            params={"branch": branch},
            url_params={"alias": self.alias, **selector},
        )
        self._load_prompt(PromptPayload(**data))
        return self

    def push(self, *, branch: Optional[str] = None) -> PushPromptResult:
        if self.text is None and self.messages is None:
            raise ValueError(
                f"Prompt {self.alias!r} has nothing to push. Pull it first, or "
                "set text or messages."
            )
        prompt = PushPromptRequest(
            alias=self.alias,
            text=self.text,
            messages=self.messages,
            interpolation_type=self.interpolation_type,
            model_settings=self.model_settings,
            output_type=self.output_type,
            output_schema=self.output_schema,
            tools=self.tools,
            branch=branch,
        )
        body = prompt.model_dump(mode="json", by_alias=True, exclude_none=True)

        data, _ = self._api.send_request(
            HttpMethods.POST, Endpoints.PROMPTS_ENDPOINT, body=body
        )
        return PushPromptResult(**data)

    def interpolate(self, **values: Any) -> Interpolated:
        return interpolate(
            self.type,
            self.interpolation_type,
            values,
            text=self.text,
            messages=self.messages,
        )

    def list_versions(self) -> PromptVersions:
        data, _ = self._api.send_request(
            HttpMethods.GET,
            Endpoints.PROMPT_VERSIONS_ENDPOINT,
            url_params={"alias": self.alias},
        )
        return PromptVersions(**data)

    def create_version(
        self, *, commit: Optional[str] = None
    ) -> CreatePromptVersionResult:
        body: Dict[str, Any] = {"hash": commit} if commit else {}
        data, _ = self._api.send_request(
            HttpMethods.POST,
            Endpoints.PROMPT_VERSIONS_ENDPOINT,
            body=body,
            url_params={"alias": self.alias},
        )
        return CreatePromptVersionResult(**data)

    def list_commits(
        self, *, branch: Optional[str] = None
    ) -> List[PromptCommit]:
        data, _ = self._api.send_request(
            HttpMethods.GET,
            Endpoints.PROMPT_COMMITS_ENDPOINT,
            params={"branch": branch},
            url_params={"alias": self.alias},
        )
        return PromptCommitList(**data).commits

    def list_branches(self) -> List[PromptBranch]:
        data, _ = self._api.send_request(
            HttpMethods.GET,
            Endpoints.PROMPT_BRANCHES_ENDPOINT,
            url_params={"alias": self.alias},
        )
        return PromptBranchList(**data).branches

    def _resolve_pull_endpoint(
        self,
        label: Optional[str],
        version: Optional[str],
        commit: Optional[str],
    ) -> Tuple[Endpoints, Dict[str, str]]:
        provided = [
            name
            for name, value in zip(_SELECTORS, (label, version, commit))
            if value is not None
        ]
        if len(provided) > 1:
            raise ValueError(
                f"Provide at most one of {', '.join(_SELECTORS)}; "
                f"got {', '.join(provided)}."
            )

        if label is not None:
            return Endpoints.PROMPT_LABEL_ENDPOINT, {"label": label}
        if version is not None:
            return Endpoints.PROMPT_VERSION_ENDPOINT, {"version": version}
        return Endpoints.PROMPT_COMMIT_ENDPOINT, {
            "hash": commit or LATEST_COMMIT
        }

    def _load_prompt(self, payload: PromptPayload) -> None:
        self.id = payload.id
        self.hash = payload.hash
        self.version = payload.version
        self.label = payload.label
        self.type = payload.type
        self.text = payload.text
        self.messages = payload.messages
        self.interpolation_type = payload.interpolation_type
        self.model_settings = payload.model_settings
        self.output_type = payload.output_type
        self.output_schema = payload.output_schema
        self.tools = payload.tools
