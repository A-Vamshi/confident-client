import pytest

from confident_ai.api import API_KEY_HEADER
from confident_ai.cli import main

PROJECT_KEY = "confident_us_proj_testkey"
POLICY = {"id": "<GOVERNANCE-POLICY-ID>", "name": "EU AI Act"}


@pytest.fixture
def project_key(clean_env, monkeypatch):
    monkeypatch.setenv("CONFIDENT_PROJ_API_KEY", PROJECT_KEY)


def test_gate_passes(http, project_key, capsys):
    http.enqueue_data({"passed": True, "governancePolicy": POLICY})

    assert main(["gate"]) == 0
    assert http.last["method"] == "POST"
    assert http.last["url"].endswith("/v2/governance/assess")
    assert http.last["headers"][API_KEY_HEADER] == PROJECT_KEY
    assert "passed against EU AI Act" in capsys.readouterr().out


def test_gate_fails(http, project_key, capsys):
    http.enqueue_data({"passed": False, "governancePolicy": POLICY})

    assert main(["gate"]) == 1
    assert "failed against EU AI Act" in capsys.readouterr().out


def test_gate_quiet_prints_nothing(http, project_key, capsys):
    http.enqueue_data({"passed": False, "governancePolicy": POLICY})

    assert main(["gate", "--quiet"]) == 1
    assert capsys.readouterr() == ("", "")


def test_gate_reports_api_errors(http, project_key, capsys):
    http.enqueue_raw(
        {"success": False, "error": "Project has no governance policy"},
        status_code=400,
    )

    assert main(["gate"]) == 1
    err = capsys.readouterr().err
    assert "Project has no governance policy" in err
    assert "organization administrator" in err


def test_gate_needs_a_project_key(http, clean_env, monkeypatch, capsys):
    monkeypatch.setenv("CONFIDENT_ORG_API_KEY", "confident_us_org_testkey")

    assert main(["gate", "-q"]) == 1
    assert http.calls == []

    assert main(["gate"]) == 1
    assert "CONFIDENT_PROJ_API_KEY" in capsys.readouterr().err


def test_requires_a_command(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
