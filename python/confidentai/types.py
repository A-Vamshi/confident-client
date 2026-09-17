"""The base model every generated type inherits, and the transport's own
shapes. Everything else the SDK declares is generated per resource.
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ConfidentBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class ApiResponse(ConfidentBaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    deprecated: Optional[bool] = None
    link: Optional[str] = None


class ConfidentApiError(Exception):
    """Custom exception that preserves API response metadata"""

    def __init__(self, message: str, link: Optional[str] = None):
        super().__init__(message)
        self.link = link
