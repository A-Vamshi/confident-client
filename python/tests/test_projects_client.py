from typing import Any, Dict


def a_project(**overrides: Any) -> Dict[str, Any]:
    return {
        "id": "<PROJECT-ID>",
        "name": "Prod",
        "description": None,
        "organizationId": "<ORGANIZATION-ID>",
        "created_at": "2026-01-01T00:00:00.000Z",
        "governancePolicy": None,
        **overrides,
    }


# ===== The collection =====


def test_list_reads_every_project(client, http):
    http.enqueue_data({"projects": [a_project()]})

    projects = client.projects.list()

    assert projects.projects[0].id == "<PROJECT-ID>"
    assert projects.projects[0].organization_id == "<ORGANIZATION-ID>"
    assert http.last["method"] == "GET"
    assert http.last["url"].endswith("/v2/projects")


def test_create_returns_the_project_and_its_first_api_key(client, http):
    http.enqueue_data(
        {
            "project": {
                "id": "<PROJECT-ID>",
                "name": "New",
                "description": "desc",
                "organizationId": "<ORGANIZATION-ID>",
                "created_at": "2026-01-01T00:00:00.000Z",
            },
            "apiKey": {
                "id": 7,
                "name": "Default Key",
                "valid": True,
                "value": "confident_us_proj_secret",
                "shadowValue": None,
                "rotatesAt": None,
                "created_at": "2026-01-01T00:00:00.000Z",
                "lastUsed": None,
                "expiresAt": None,
            },
        }
    )

    created = client.projects.create("New", description="desc")

    assert created.project.id == "<PROJECT-ID>"
    assert created.api_key.value == "confident_us_proj_secret"
    assert http.last["method"] == "POST"
    assert http.last["json"] == {"name": "New", "description": "desc"}


def test_get_update_and_delete_by_id(client, http):
    http.enqueue_data(a_project())
    fetched = client.projects.get("<PROJECT-ID>")
    assert fetched.name == "Prod"
    assert http.last["url"].endswith("/v2/projects/<PROJECT-ID>")

    http.enqueue_data(a_project(name="Renamed"))
    updated = client.projects.update("<PROJECT-ID>", name="Renamed")
    assert updated.name == "Renamed"
    assert http.last["method"] == "PUT"
    assert http.last["json"] == {"name": "Renamed"}

    http.enqueue_data({"id": "<PROJECT-ID>"})
    deleted = client.projects.delete("<PROJECT-ID>")
    assert deleted.id == "<PROJECT-ID>"
    assert http.last["method"] == "DELETE"


# ===== The handle =====


def test_the_handle_holds_the_project_id(client):
    project = client.project("<PROJECT-ID>")

    assert project.project_id == "<PROJECT-ID>"
    assert repr(project).startswith("Project(project_id='<PROJECT-ID>'")


def test_a_handle_without_an_id_says_so(client):
    import pytest

    with pytest.raises(ValueError, match="no project_id"):
        client.project().get()


def test_get_fills_the_handle_and_returns_it(client, http):
    http.enqueue_data(a_project(description="The production project"))
    project = client.project("<PROJECT-ID>")

    returned = project.get()

    # A load returns the handle itself, so a caller can chain off it.
    assert returned is project
    assert project.name == "Prod"
    assert project.description == "The production project"
    assert project.organization_id == "<ORGANIZATION-ID>"
    assert http.last["url"].endswith("/v2/projects/<PROJECT-ID>")


def test_update_sends_what_the_handle_holds(client, http):
    http.enqueue_data(a_project())
    project = client.project("<PROJECT-ID>").get()

    project.name = "Renamed"
    http.enqueue_data(a_project(name="Renamed"))
    result = project.update()

    assert result.name == "Renamed"
    assert http.last["method"] == "PUT"
    # The handle loaded `description: None`, and the body is dumped with
    # `exclude_none=True`, so it is left out. TypeScript sends it as null —
    # the two SDKs put different bodies on the wire for the same calls.
    assert http.last["json"] == {"name": "Renamed"}
    assert http.last["url"].endswith("/v2/projects/<PROJECT-ID>")


def test_delete_needs_no_argument(client, http):
    http.enqueue_data({"id": "<PROJECT-ID>"})

    deleted = client.project("<PROJECT-ID>").delete()

    assert deleted.id == "<PROJECT-ID>"
    assert http.last["method"] == "DELETE"
    assert http.last["url"].endswith("/v2/projects/<PROJECT-ID>")


def test_the_handle_scopes_a_sub_resource_path(client, http):
    http.enqueue_data({"apiKeys": []})

    client.project("<PROJECT-ID>").list_api_keys()

    assert http.last["url"].endswith("/v2/projects/<PROJECT-ID>/api-keys")


def test_create_invitations_sends_the_project_role_id(client, http):
    http.enqueue_data(
        {
            "invitations": [
                {
                    "id": 1,
                    "email": "new@acme.com",
                    "status": "PENDING",
                    "created_at": "2026-01-01T00:00:00.000Z",
                    "projectRoleId": "<PROJECT-ROLE-ID>",
                    "token": None,
                }
            ]
        }
    )

    client.project("<PROJECT-ID>").create_invitations(
        ["new@acme.com"], project_role_id="<PROJECT-ROLE-ID>"
    )

    assert http.last["json"] == {
        "emails": ["new@acme.com"],
        "projectRoleId": "<PROJECT-ROLE-ID>",
    }
    assert http.last["url"].endswith("/v2/projects/<PROJECT-ID>/invitations")


def test_update_member_role_returns_the_project_role(client, http):
    http.enqueue_data(
        {
            "id": "<USER-ID>",
            "email": "engineer@acme.com",
            "name": "Sam Rivera",
            "image": None,
            "projectRole": {"id": "<PROJECT-ROLE-ID>", "name": "Owner"},
        }
    )

    member = client.project("<PROJECT-ID>").update_member_role(
        "<USER-ID>", "<PROJECT-ROLE-ID>"
    )

    assert member.project_role.name == "Owner"
    assert http.last["json"] == {"roleId": "<PROJECT-ROLE-ID>"}
    assert http.last["url"].endswith(
        "/v2/projects/<PROJECT-ID>/members/<USER-ID>"
    )
