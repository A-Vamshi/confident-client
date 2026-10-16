import asyncio
import base64
import re

import pytest

from confident_ai import ConfidentAI, Media, parse_multimodal
from confident_ai.common import MLLMImage, Turn, TurnRole
from confident_ai.datasets import MultiTurnGolden, SingleTurnGolden
from confident_ai.evaluate import SingleTurnTestCase

PNG = b"\x89PNG\r\n\x1a\n"
LOCAL_MARKER = re.compile(r"^\[CONFIDENT:IMAGE:[0-9a-f]{32}\]$")
MARKER_KEY = re.compile(r"\[CONFIDENT:IMAGE:([^\]]+)\]")
PNG_BASE64 = base64.b64encode(PNG).decode()


def test_url_media_keeps_the_url_in_its_marker():
    media = Media.from_url("https://cdn.example.com/cat.png")

    assert str(media) == "[CONFIDENT:IMAGE:https://cdn.example.com/cat.png]"
    assert media.mime_type == "image/png"
    assert media.filename == "cat.png"
    assert not media.is_local


def test_url_media_escapes_closing_brackets():
    media = Media.from_url("https://example.com/a[1].png")

    assert str(media) == "[CONFIDENT:IMAGE:https://example.com/a[1%5D.png]"


def test_url_without_an_extension_has_no_mime_type():
    assert Media.from_url("https://example.com/image?id=3").mime_type is None


@pytest.mark.parametrize("url", ["cat.png", "file:///tmp/cat.png", "ftp://x/a"])
def test_from_url_rejects_non_http_urls(url):
    with pytest.raises(ValueError, match="not an http"):
        Media.from_url(url)


def test_file_media_is_sent_as_base64(tmp_path):
    path = tmp_path / "cat.PNG"
    path.write_bytes(PNG)

    media = Media.from_file(path)

    assert media.is_local
    assert media.data_base64 == base64.b64encode(PNG).decode()
    assert media.mime_type == "image/png"
    assert media.filename == "cat.PNG"
    assert media.url is None
    assert LOCAL_MARKER.match(str(media))
    assert str(media) == str(media)


def test_each_local_media_gets_its_own_marker():
    first = Media.from_bytes(PNG, "image/png")
    second = Media.from_bytes(PNG, "image/png")

    assert str(first) != str(second)


def test_formats_into_strings():
    media = Media.from_bytes(PNG, "image/png")

    assert re.fullmatch(
        r"What is in \[CONFIDENT:IMAGE:[0-9a-f]{32}\]\?", f"What is in {media}?"
    )


def test_from_file_needs_a_mime_type_it_cannot_guess(tmp_path):
    path = tmp_path / "cat.raw"
    path.write_bytes(PNG)

    with pytest.raises(ValueError, match="mime_type"):
        Media.from_file(path)
    assert Media.from_file(path, "image/png").mime_type == "image/png"


def test_from_file_raises_for_a_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        Media.from_file(tmp_path / "missing.png")


def test_from_base64_keeps_the_encoded_bytes():
    encoded = base64.b64encode(PNG).decode()

    assert Media.from_base64(encoded, "image/png").data_base64 == encoded


def test_from_base64_rejects_data_uris():
    encoded = base64.b64encode(PNG).decode()

    with pytest.raises(ValueError, match="not valid base64"):
        Media.from_base64(f"data:image/png;base64,{encoded}", "image/png")


def test_only_images_are_supported():
    with pytest.raises(ValueError, match="Only images"):
        Media.from_bytes(b"%PDF", "application/pdf")
    with pytest.raises(ValueError, match="Only images"):
        Media.from_url("https://example.com/a", "application/pdf")


def test_empty_media_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        Media.from_bytes(b"", "image/png")


@pytest.fixture
def project(http, clean_env):
    http.enqueue_data({"id": "<ID>"})
    return ConfidentAI(project_api_key="confident_us_proj_testkey")


def key_of(text):
    return MARKER_KEY.search(text).group(1)


def sent_goldens(http):
    return http.last["json"]["goldens"]


def test_push_maps_the_local_media_of_each_golden(http, project):
    goldens = [
        SingleTurnGolden(
            input=f"Golden {i}: {Media.from_bytes(PNG, 'image/png')}"
        )
        for i in range(20)
    ]

    project.datasets.push(alias="screenshots", goldens=goldens)

    for golden in sent_goldens(http):
        assert golden["imagesMapping"] == {
            key_of(golden["input"]): {
                "url": "",
                "local": True,
                "mimeType": "image/png",
                "dataBase64": PNG_BASE64,
            }
        }


def test_url_media_are_sent_by_reference(http, project):
    media = Media.from_url("https://cdn.example.com/cat.png")

    project.datasets.push(
        alias="screenshots",
        goldens=[SingleTurnGolden(input=f"{media} What is this?")],
    )

    assert sent_goldens(http)[0]["imagesMapping"] == {
        "https://cdn.example.com/cat.png": {
            "url": "https://cdn.example.com/cat.png",
            "local": False,
        }
    }


def test_media_in_turns_are_mapped_on_the_golden(http, project, tmp_path):
    path = tmp_path / "cat.png"
    path.write_bytes(PNG)
    content = f"What is in {Media.from_file(path)}?"
    golden = MultiTurnGolden(
        scenario="A user asks about a photo",
        turns=[Turn(role=TurnRole.USER, content=content)],
    )

    project.datasets.push(alias="photos", goldens=[golden])

    sent = sent_goldens(http)[0]
    assert "imagesMapping" not in sent["turns"][0]
    assert sent["imagesMapping"][key_of(content)]["filename"] == "cat.png"


def test_goldens_without_media_are_sent_unchanged(http, project):
    project.datasets.push(
        alias="plain", goldens=[SingleTurnGolden(input="Hello")]
    )

    assert "imagesMapping" not in sent_goldens(http)[0]


def test_unknown_markers_are_left_to_the_server(http, project):
    project.datasets.push(
        alias="plain",
        goldens=[SingleTurnGolden(input="[CONFIDENT:IMAGE:0123abcd]")],
    )

    assert "imagesMapping" not in sent_goldens(http)[0]


def test_a_supplied_images_mapping_wins(http, project):
    text = f"{Media.from_bytes(PNG, 'image/png')}"
    supplied = MLLMImage(url="https://cdn.example.com/cat.png", local=False)
    golden = SingleTurnGolden(
        input=text, images_mapping={key_of(text): supplied}
    )

    project.datasets.push(alias="screenshots", goldens=[golden])

    assert sent_goldens(http)[0]["imagesMapping"] == {
        key_of(text): {"url": "https://cdn.example.com/cat.png", "local": False}
    }


def test_sending_leaves_the_goldens_untouched(http, project):
    golden = SingleTurnGolden(input=f"{Media.from_bytes(PNG, 'image/png')}")

    project.datasets.push(alias="screenshots", goldens=[golden])

    assert golden.images_mapping is None


def test_update_golden_maps_media_on_the_body(http, project):
    text = f"{Media.from_bytes(PNG, 'image/png')}"

    project.datasets.update_golden(
        "<DATASET-ID>", "<GOLDEN-ID>", SingleTurnGolden(input=text)
    )

    assert key_of(text) in http.last["json"]["imagesMapping"]


def test_run_evals_maps_media_per_test_case(http, project):
    text = f"{Media.from_bytes(PNG, 'image/png')}"

    asyncio.run(
        project.evaluate.a_run_evals(
            metric_collection="Vision",
            test_cases=[SingleTurnTestCase(input=text, actual_output="A cat")],
        )
    )

    test_case = http.last["json"]["testCases"][0]
    assert key_of(text) in test_case["imagesMapping"]


def test_parse_multimodal_returns_text_and_media():
    media = Media.from_bytes(PNG, "image/png")
    pulled = "[CONFIDENT:IMAGE:https://bucket.example.com/dog.png?sig=abc]"

    parts = parse_multimodal(f"Compare {media} with {pulled}.")

    assert parts[0] == "Compare "
    assert parts[1] is media
    assert parts[2] == " with "
    assert parts[3].url == "https://bucket.example.com/dog.png?sig=abc"
    assert parts[3].mime_type == "image/png"
    assert parts[4] == "."


def test_parse_multimodal_keeps_unknown_markers_as_text():
    text = "Before [CONFIDENT:IMAGE:0123abcd] after"

    assert parse_multimodal(text) == [text]
