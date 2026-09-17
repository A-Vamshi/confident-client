from typing import Any, Dict


# ===== Payloads the generated models accept =====
#
# A model field with no default is required even when its type is optional, so
# these builders spell out the nulls the API really sends rather than leaving
# a test to fail on a field nobody was asserting.


def an_organization(**overrides: Any) -> Dict[str, Any]:
    return {
        "id": "<ORGANIZATION-ID>",
        "name": "Acme",
        "plan": "PREMIUM",
        "created_at": "2026-01-01T00:00:00.000Z",
        **overrides,
    }


def an_api_key(**overrides: Any) -> Dict[str, Any]:
    return {
        "id": 1,
        "name": "CI",
        "valid": True,
        "created_at": "2026-01-01T00:00:00.000Z",
        "expiresAt": None,
        "value": "confident_us_org_***abc",
        "shadowValue": None,
        "rotatesAt": None,
        "lastUsed": None,
        **overrides,
    }


def a_member(**overrides: Any) -> Dict[str, Any]:
    return {
        "id": "<USER-ID>",
        "email": "engineer@acme.com",
        "name": "Sam Rivera",
        "image": None,
        "organizationRole": {"id": "<ROLE-ID>", "name": "Admin"},
        **overrides,
    }


def a_governance_policy_summary(**overrides: Any) -> Dict[str, Any]:
    return {
        "id": "<GOVERNANCE-POLICY-ID>",
        "name": "Production Gate",
        "description": None,
        "projectsCount": 5,
        "isBasePolicy": False,
        "controls": [
            {
                "id": "<CONTROL-ID>",
                "name": "Logs traces",
                "type": "PRE_DEPLOYMENT_EVALS",
            },
        ],
        **overrides,
    }


# ===== The organization itself =====


def test_get_reads_the_organization(client, http):
    http.enqueue_data(an_organization())

    organization = client.organization.get()

    assert organization.id == "<ORGANIZATION-ID>"
    assert organization.plan.value == "PREMIUM"
    assert http.last["method"] == "GET"
    assert http.last["url"].endswith("/v2/organization")


def test_update_sends_the_new_name(client, http):
    http.enqueue_data(an_organization(name="Acme Inc."))

    organization = client.organization.update("Acme Inc.")

    assert organization.name == "Acme Inc."
    assert http.last["method"] == "PUT"
    assert http.last["json"] == {"name": "Acme Inc."}


# ===== API keys =====


def test_api_key_lifecycle(client, http):
    organization = client.organization

    http.enqueue_data({"apiKeys": [an_api_key()]})
    listed = organization.list_api_keys()
    assert listed.api_keys[0].id == 1
    assert http.last["url"].endswith("/v2/organization/api-keys")

    http.enqueue_data(an_api_key(id=2, value="confident_us_org_secret"))
    created = organization.create_api_key("CI")
    assert created.value == "confident_us_org_secret"
    assert http.last["method"] == "POST"
    # An optional nobody set is left out of the body, not sent as null.
    assert http.last["json"] == {"name": "CI"}

    http.enqueue_data(an_api_key(id=2, valid=False))
    updated = organization.update_api_key("2", False)
    assert updated.valid is False
    assert http.last["method"] == "PUT"
    assert http.last["json"] == {"valid": False}
    assert http.last["url"].endswith("/v2/organization/api-keys/2")

    http.enqueue_data({"id": 2})
    deleted = organization.delete_api_key("2")
    assert deleted.id == 2
    assert http.last["method"] == "DELETE"


def test_create_api_key_passes_an_expiry(client, http):
    http.enqueue_data(an_api_key())

    client.organization.create_api_key("CI", expires_in_days=30)

    assert http.last["json"] == {"name": "CI", "expiresInDays": 30}


# ===== Members and invitations =====


def test_update_member_role_sends_the_role_id(client, http):
    http.enqueue_data(a_member())

    member = client.organization.update_member_role("<USER-ID>", "<ROLE-ID>")

    assert member.organization_role.name == "Admin"
    assert http.last["method"] == "PUT"
    assert http.last["json"] == {"roleId": "<ROLE-ID>"}
    assert http.last["url"].endswith("/v2/organization/members/<USER-ID>")


def test_remove_member_returns_the_id_it_removed(client, http):
    http.enqueue_data({"id": "<USER-ID>"})

    removed = client.organization.remove_member("<USER-ID>")

    assert removed.id == "<USER-ID>"
    assert http.last["method"] == "DELETE"


def test_list_members_maps_page_size_to_the_wire_name(client, http):
    http.enqueue_data(
        {
            "members": [],
            "totalOrganizationMembers": 0,
            "page": 2,
            "pageSize": 50,
        }
    )

    client.organization.list_members(page=2, page_size=50)

    # snake_case in, camelCase out: the mapping every query parameter relies on.
    assert http.last["params"] == {"page": 2, "pageSize": 50}


def test_create_invitations_sends_the_organization_role_id(client, http):
    http.enqueue_data(
        {
            "invitations": [
                {
                    "id": 1,
                    "email": "new@acme.com",
                    "status": "PENDING",
                    "created_at": "2026-01-01T00:00:00.000Z",
                    "organizationRoleId": "<ROLE-ID>",
                    "token": None,
                }
            ]
        }
    )

    invitations = client.organization.create_invitations(
        ["new@acme.com"], organization_role_id="<ROLE-ID>"
    )

    assert invitations.invitations[0].email == "new@acme.com"
    assert http.last["json"] == {
        "emails": ["new@acme.com"],
        "organizationRoleId": "<ROLE-ID>",
    }


# ===== Roles, policies and permissions =====


def test_create_role_sends_its_policy_ids(client, http):
    http.enqueue_data(
        {
            "id": "<ROLE-ID>",
            "name": "Analyst",
            "description": "read only",
            "policies": [],
            "organizationId": "<ORGANIZATION-ID>",
        }
    )

    role = client.organization.create_role(
        "Analyst", ["<POLICY-ID>"], description="read only"
    )

    assert role.name == "Analyst"
    assert http.last["json"] == {
        "name": "Analyst",
        "policyIds": ["<POLICY-ID>"],
        "description": "read only",
    }


def test_create_policy_sends_its_permission_ids(client, http):
    http.enqueue_data(
        {
            "id": "<POLICY-ID>",
            "name": "Billing",
            "description": None,
            "permissions": [],
        }
    )

    client.organization.create_policy("Billing", ["<PERMISSION-ID>"])

    assert http.last["json"] == {
        "name": "Billing",
        "permissionIds": ["<PERMISSION-ID>"],
    }


def test_list_permissions(client, http):
    http.enqueue_data(
        {
            "permissions": [
                {
                    "id": "<PERMISSION-ID>",
                    "name": "billing:read",
                    "description": None,
                }
            ]
        }
    )

    permissions = client.organization.list_permissions()

    assert permissions.permissions[0].name == "billing:read"
    assert http.last["url"].endswith("/v2/organization/permissions")


# ===== Governance =====


def test_list_governance_policies(client, http):
    http.enqueue_data({"governancePolicies": [a_governance_policy_summary()]})

    policies = client.organization.list_governance_policies()

    policy = policies.governance_policies[0]
    assert policy.id == "<GOVERNANCE-POLICY-ID>"
    assert policy.projects_count == 5
    assert policy.is_base_policy is False
    assert policy.controls[0].name == "Logs traces"
    assert policy.controls[0].type.value == "PRE_DEPLOYMENT_EVALS"
    assert http.last["url"].endswith("/v2/organization/governance-policies")


def test_list_governance_policy_projects_paginates(client, http):
    http.enqueue_data(
        {
            "projects": [{"id": "<PROJECT-ID>", "name": "Prod"}],
            "totalGovernancePolicyProjects": 1,
            "page": 2,
            "pageSize": 50,
        }
    )

    projects = client.organization.list_governance_policy_projects(
        "<GOVERNANCE-POLICY-ID>", page=2, page_size=50
    )

    assert projects.projects[0].id == "<PROJECT-ID>"
    assert http.last["params"] == {"page": 2, "pageSize": 50}
    assert http.last["url"].endswith(
        "/v2/organization/governance-policies/<GOVERNANCE-POLICY-ID>/projects"
    )


def test_assign_projects_to_a_governance_policy(client, http):
    http.enqueue_data(
        {
            "governancePolicy": {
                "id": "<GOVERNANCE-POLICY-ID>",
                "name": "Production Gate",
            },
            "assignedProjectIds": ["<PROJECT-ID>", "<OTHER-PROJECT-ID>"],
            "notFoundProjectIds": [],
            "count": 2,
        }
    )

    result = client.organization.assign_projects_to_governance_policy(
        "<GOVERNANCE-POLICY-ID>", ["<PROJECT-ID>", "<OTHER-PROJECT-ID>"]
    )

    assert result.governance_policy.id == "<GOVERNANCE-POLICY-ID>"
    assert result.assigned_project_ids == [
        "<PROJECT-ID>",
        "<OTHER-PROJECT-ID>",
    ]
    assert result.not_found_project_ids == []
    assert result.count == 2
    assert http.last["method"] == "POST"
    assert http.last["json"] == {
        "projectIds": ["<PROJECT-ID>", "<OTHER-PROJECT-ID>"]
    }


def test_unassign_projects_from_a_governance_policy(client, http):
    http.enqueue_data(
        {
            "governancePolicy": {
                "id": "<GOVERNANCE-POLICY-ID>",
                "name": "Production Gate",
            },
            "unassignedProjectIds": ["<PROJECT-ID>"],
            "skippedProjectIds": [],
            "count": 1,
        }
    )

    result = client.organization.unassign_projects_from_governance_policy(
        "<GOVERNANCE-POLICY-ID>", ["<PROJECT-ID>"]
    )

    assert result.unassigned_project_ids == ["<PROJECT-ID>"]
    assert result.skipped_project_ids == []
    assert result.count == 1
    assert http.last["method"] == "POST"
    assert http.last["json"] == {"projectIds": ["<PROJECT-ID>"]}
