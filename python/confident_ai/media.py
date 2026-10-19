import base64
import binascii
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Union
from urllib.parse import urlparse
from uuid import uuid4

_IMAGE_MIME_TYPES = {
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}

_MARKER = re.compile(r"\[CONFIDENT:IMAGE:([^\]]+)\]")

_MAPPING_FIELD = "imagesMapping"

_REGISTRY: Dict[str, "Media"] = {}


def _guess_mime_type(path: str) -> Optional[str]:
    return _IMAGE_MIME_TYPES.get(os.path.splitext(path)[1].lower())


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


class Media:
    def __init__(
        self,
        *,
        url: Optional[str] = None,
        data_base64: Optional[str] = None,
        mime_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> None:
        if (url is None) == (data_base64 is None):
            raise ValueError("A Media needs either a url or data_base64.")
        if not (url or data_base64):
            raise ValueError("A Media can't be empty.")
        if mime_type is not None and not mime_type.startswith("image/"):
            raise ValueError(
                f"Only images are supported for now, got {mime_type!r}."
            )
        if data_base64 is not None and mime_type is None:
            raise ValueError(
                "A local Media needs a mime_type, such as 'image/png'."
            )

        self.url = url
        self.data_base64 = data_base64
        self.mime_type = mime_type
        self.filename = filename
        self._key = url.replace("]", "%5D") if url is not None else uuid4().hex

    @classmethod
    def from_url(cls, url: str, mime_type: Optional[str] = None) -> "Media":
        if not _is_http_url(url):
            raise ValueError(
                f"{url!r} is not an http(s) URL. Use Media.from_file for a "
                "local file."
            )
        parsed = urlparse(url)
        return cls(
            url=url,
            mime_type=mime_type or _guess_mime_type(parsed.path),
            filename=os.path.basename(parsed.path) or None,
        )

    @classmethod
    def from_file(
        cls,
        path: Union[str, "os.PathLike[str]"],
        mime_type: Optional[str] = None,
    ) -> "Media":
        path = os.fspath(path)
        with open(path, "rb") as file:
            data = file.read()
        return cls(
            data_base64=base64.b64encode(data).decode("ascii"),
            mime_type=mime_type or _guess_mime_type(path),
            filename=os.path.basename(path),
        )

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str) -> "Media":
        return cls(
            data_base64=base64.b64encode(data).decode("ascii"),
            mime_type=mime_type,
        )

    @classmethod
    def from_base64(cls, data_base64: str, mime_type: str) -> "Media":
        try:
            base64.b64decode(data_base64, validate=True)
        except binascii.Error:
            raise ValueError(
                "data_base64 is not valid base64. Pass the encoded bytes "
                "alone, without a 'data:' prefix."
            ) from None
        return cls(data_base64=data_base64, mime_type=mime_type)

    @property
    def is_local(self) -> bool:
        return self.data_base64 is not None

    def __str__(self) -> str:
        if self.is_local:
            _REGISTRY[self._key] = self
        return f"[CONFIDENT:IMAGE:{self._key}]"

    def __repr__(self) -> str:
        source = self.url or self.filename or "bytes"
        return f"Media({source!r}, mime_type={self.mime_type!r})"


def _media_for(key: str) -> Optional[Media]:
    if key in _REGISTRY:
        return _REGISTRY[key]
    return Media.from_url(key) if _is_http_url(key) else None


def parse_multimodal(text: str) -> List[Union[str, Media]]:
    parts: List[Union[str, Media]] = []
    last = 0
    for match in _MARKER.finditer(text):
        media = _media_for(match.group(1))
        if media is None:
            continue
        if match.start() > last:
            parts.append(text[last : match.start()])
        parts.append(media)
        last = match.end()
    if last < len(text):
        parts.append(text[last:])
    return parts


def _image(key: str, media: Media) -> Dict[str, Any]:
    if not media.is_local:
        return {"url": key, "local": False}
    image = {
        "url": "",
        "local": True,
        "mimeType": media.mime_type,
        "dataBase64": media.data_base64,
    }
    if media.filename:
        image["filename"] = media.filename
    return image


def _marker_keys(value: Any, keys: Dict[str, None]) -> None:
    if isinstance(value, str):
        keys.update(dict.fromkeys(_MARKER.findall(value)))
    elif isinstance(value, dict):
        for field, item in value.items():
            if field != _MAPPING_FIELD:
                _marker_keys(item, keys)
    elif isinstance(value, list):
        for item in value:
            _marker_keys(item, keys)


def _with_images_mapping(holder: Dict[str, Any]) -> Dict[str, Any]:
    keys: Dict[str, None] = {}
    _marker_keys(holder, keys)
    found = {key: _media_for(key) for key in keys}
    mapping = {
        key: _image(key, media)
        for key, media in found.items()
        if media is not None
    }
    if not mapping:
        return holder
    return {
        **holder,
        _MAPPING_FIELD: {**mapping, **(holder.get(_MAPPING_FIELD) or {})},
    }


def _attach(value: Any, path: List[str]) -> Any:
    if not path:
        return _with_images_mapping(value) if isinstance(value, dict) else value
    head, rest = path[0], path[1:]
    if head == "*":
        if isinstance(value, list):
            return [_attach(item, rest) for item in value]
        return value
    if isinstance(value, dict) and head in value:
        return {**value, head: _attach(value[head], rest)}
    return value


def attach_images_mappings(body: Any, holders: Sequence[str]) -> Any:
    for holder in holders:
        body = _attach(body, holder.split(".")[1:])
    return body
