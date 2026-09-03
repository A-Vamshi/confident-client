from typing import Any, Dict, List, Optional

from confidentai.api import Api, Endpoints, HttpMethods
from .types import (
    CreatePromptVersionResult,
    ModelSettings,
    OutputSchema,
    Prompt,
    PromptBranch,
    PromptBranchList,
    PromptBranchRef,
    PromptCommit,
    PromptCommitList,
    PromptInterpolationType,
    PromptList,
    PromptMessage,
    PromptOutputType,
    PromptSummary,
    PromptVersions,
    PushPromptRequest,
    PushPromptResult,
    Tool,
)

_PULL_SELECTORS = ("label", "version", "commit")

# Sentinel the API accepts in place of a commit hash for the newest commit.
LATEST_COMMIT = "latest"


def _resolve_pull_endpoint(
    label: Optional[str], version: Optional[str], commit: Optional[str]
) -> "tuple[Endpoints, Dict[str, str]]":
    provided = [
        name
        for name, value in zip(_PULL_SELECTORS, (label, version, commit))
        if value is not None
    ]
    if len(provided) > 1:
        raise ValueError(
            f"Provide at most one of {', '.join(_PULL_SELECTORS)}; "
            f"got {', '.join(provided)}."
        )

    if label is not None:
        return Endpoints.PROMPT_LABEL_ENDPOINT, {"label": label}
    if version is not None:
        return Endpoints.PROMPT_VERSION_ENDPOINT, {"version": version}
    return Endpoints.PROMPT_COMMIT_ENDPOINT, {"hash": commit or LATEST_COMMIT}


class Prompts:
    def __init__(self, api: Api) -> None:
        self._api = api

    def list(self) -> List[PromptSummary]:
        data, _ = self._api.send_request(
            HttpMethods.GET, Endpoints.PROMPTS_ENDPOINT
        )
        return PromptList(**data).prompts

    def pull(
        self,
        alias: str,
        *,
        label: Optional[str] = None,
        version: Optional[str] = None,
        commit: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> Prompt:
        endpoint, url_params = _resolve_pull_endpoint(label, version, commit)
        data, _ = self._api.send_request(
            HttpMethods.GET,
            endpoint,
            params={"branch": branch},
            url_params={"alias": alias, **url_params},
        )
        return Prompt(**data)

    def push(
        self,
        alias: str,
        *,
        text: Optional[str] = None,
        messages: Optional[List[PromptMessage]] = None,
        interpolation_type: Optional[PromptInterpolationType] = None,
        model_settings: Optional[ModelSettings] = None,
        output_type: Optional[PromptOutputType] = None,
        output_schema: Optional[OutputSchema] = None,
        tools: Optional[List[Tool]] = None,
        branch: Optional[str] = None,
    ) -> PushPromptResult:
        body = PushPromptRequest(
            alias=alias,
            text=text,
            messages=messages,
            interpolation_type=interpolation_type,
            model_settings=model_settings,
            output_type=output_type,
            output_schema=output_schema,
            tools=tools,
            branch=branch,
        ).model_dump(mode="json", by_alias=True, exclude_none=True)
        data, _ = self._api.send_request(
            HttpMethods.POST, Endpoints.PROMPTS_ENDPOINT, body=body
        )
        return PushPromptResult(**data)

    def list_versions(self, alias: str) -> PromptVersions:
        data, _ = self._api.send_request(
            HttpMethods.GET,
            Endpoints.PROMPT_VERSIONS_ENDPOINT,
            url_params={"alias": alias},
        )
        return PromptVersions(**data)

    def create_version(
        self, alias: str, *, commit: Optional[str] = None
    ) -> CreatePromptVersionResult:
        body: Dict[str, Any] = {"hash": commit} if commit else {}
        data, _ = self._api.send_request(
            HttpMethods.POST,
            Endpoints.PROMPT_VERSIONS_ENDPOINT,
            body=body,
            url_params={"alias": alias},
        )
        return CreatePromptVersionResult(**data)

    def list_commits(
        self, alias: str, *, branch: Optional[str] = None
    ) -> List[PromptCommit]:
        data, _ = self._api.send_request(
            HttpMethods.GET,
            Endpoints.PROMPT_COMMITS_ENDPOINT,
            params={"branch": branch},
            url_params={"alias": alias},
        )
        return PromptCommitList(**data).commits

    def list_branches(self, alias: str) -> List[PromptBranch]:
        data, _ = self._api.send_request(
            HttpMethods.GET,
            Endpoints.PROMPT_BRANCHES_ENDPOINT,
            url_params={"alias": alias},
        )
        return PromptBranchList(**data).branches

    def create_branch(self, alias: str, branch: str) -> PromptBranch:
        data, _ = self._api.send_request(
            HttpMethods.POST,
            Endpoints.PROMPT_BRANCHES_ENDPOINT,
            body={"branch": branch},
            url_params={"alias": alias},
        )
        return PromptBranch(**data)

    def rename_branch(
        self, alias: str, branch: str, *, name: str
    ) -> PromptBranchRef:
        data, _ = self._api.send_request(
            HttpMethods.PUT,
            Endpoints.PROMPT_BRANCH_ENDPOINT,
            body={"name": name},
            url_params={"alias": alias, "name": branch},
        )
        return PromptBranchRef(**data)

    def delete_branch(self, alias: str, branch: str) -> PromptBranchRef:
        data, _ = self._api.send_request(
            HttpMethods.DELETE,
            Endpoints.PROMPT_BRANCH_ENDPOINT,
            url_params={"alias": alias, "name": branch},
        )
        return PromptBranchRef(**data)
