from enum import Enum
from typing import Any, Dict, Mapping, Optional


def drop_none(data: Optional[Mapping]) -> Optional[Dict]:
    if data is None:
        return None
    return {key: value for key, value in data.items() if value is not None}


def _get_valid_params_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def serialize_params(data: Optional[Mapping]) -> Optional[Dict]:
    if data is None:
        return None

    params: Dict[str, Any] = {}
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            for inner_key, inner_value in value.items():
                if inner_value is not None:
                    params[f"{key}[{inner_key}]"] = _get_valid_params_value(
                        inner_value
                    )
            continue
        params[key] = _get_valid_params_value(value)
    return params


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
