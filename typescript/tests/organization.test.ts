import { ConfidentAI } from "../src";
import { clearConfidentEnv, lastCall, mockData, resetAxios } from "./helpers";

jest.mock("axios");

function makeClient(): ConfidentAI {
  return new ConfidentAI({ apiKey: "confident_us_org_testkey" });
}

const anOrganization = (overrides: Record<string, unknown> = {}) => ({
  id: "<ORGANIZATION-ID>",
  name: "Acme",
  plan: "PREMIUM",
  created_at: "2026-01-01T00:00:00.000Z",
  ...overrides,
});

const anApiKey = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  name: "CI",
  valid: true,
  created_at: "2026-01-01T00:00:00.000Z",
  expiresAt: null,
  value: "confident_us_org_***abc",
  shadowValue: null,
  rotatesAt: null,
  lastUsed: null,
  ...overrides,
});

describe("the organization", () => {
  beforeEach(() => {
    resetAxios();
    clearConfidentEnv();
  });

  // ===== The organization itself =====

  it("reads the organization", async () => {
    mockData(anOrganization());

    const organization = await makeClient().organization.get();

    expect(organization.id).toBe("<ORGANIZATION-ID>");
    expect(organization.plan).toBe("PREMIUM");
    expect(lastCall().method).toBe("GET");
    expect(lastCall().url).toContain("/v2/organization");
  });

  it("sends the new name on update", async () => {
    mockData(anOrganization({ name: "Acme Inc." }));

    const organization = await makeClient().organization.update("Acme Inc.");

    expect(organization.name).toBe("Acme Inc.");
    expect(lastCall().method).toBe("PUT");
    expect(lastCall().data).toEqual({ name: "Acme Inc." });
  });

  // ===== API keys =====

  it("runs an API key through its lifecycle", async () => {
    const organization = makeClient().organization;

    mockData({ apiKeys: [anApiKey()] });
    const listed = await organization.listApiKeys();
    expect(listed.apiKeys[0].id).toBe(1);
    expect(lastCall().url).toContain("/v2/organization/api-keys");

    mockData(anApiKey({ id: 2, value: "confident_us_org_secret" }));
    const created = await organization.createApiKey("CI");
    expect(created.value).toBe("confident_us_org_secret");
    expect(lastCall().method).toBe("POST");
    // An optional nobody set is left out of the body, not sent as null.
    expect(lastCall().data).toEqual({ name: "CI" });

    mockData(anApiKey({ id: 2, valid: false }));
    const updated = await organization.updateApiKey("2", false);
    expect(updated.valid).toBe(false);
    expect(lastCall().method).toBe("PUT");
    expect(lastCall().data).toEqual({ valid: false });
    expect(lastCall().url).toContain("/v2/organization/api-keys/2");

    mockData({ id: 2 });
    const deleted = await organization.deleteApiKey("2");
    expect(deleted.id).toBe(2);
    expect(lastCall().method).toBe("DELETE");
  });

  it("passes an expiry when one is given", async () => {
    mockData(anApiKey());

    await makeClient().organization.createApiKey("CI", 30);

    expect(lastCall().data).toEqual({ name: "CI", expiresInDays: 30 });
  });

  // ===== Members and invitations =====

  it("sends the role id when updating a member", async () => {
    mockData({
      id: "<USER-ID>",
      email: "engineer@acme.com",
      name: "Sam Rivera",
      image: null,
      organizationRole: { id: "<ROLE-ID>", name: "Admin" },
    });

    const member = await makeClient().organization.updateMemberRole(
      "<USER-ID>",
      "<ROLE-ID>",
    );

    expect(member.organizationRole?.name).toBe("Admin");
    expect(lastCall().method).toBe("PUT");
    expect(lastCall().data).toEqual({ roleId: "<ROLE-ID>" });
    expect(lastCall().url).toContain("/v2/organization/members/<USER-ID>");
  });

  it("returns the id it removed", async () => {
    mockData({ id: "<USER-ID>" });

    const removed = await makeClient().organization.removeMember("<USER-ID>");

    expect(removed.id).toBe("<USER-ID>");
    expect(lastCall().method).toBe("DELETE");
  });

  it("passes pagination through as query parameters", async () => {
    mockData({
      members: [],
      totalOrganizationMembers: 0,
      page: 2,
      pageSize: 50,
    });

    await makeClient().organization.listMembers(2, 50);

    expect(lastCall().params).toEqual({ page: 2, pageSize: 50 });
  });

  it("sends the organization role id when inviting", async () => {
    mockData({
      invitations: [
        {
          id: 1,
          email: "new@acme.com",
          status: "PENDING",
          created_at: "2026-01-01T00:00:00.000Z",
          organizationRoleId: "<ROLE-ID>",
          token: null,
        },
      ],
    });

    const invitations = await makeClient().organization.createInvitations(
      ["new@acme.com"],
      "<ROLE-ID>",
    );

    expect(invitations.invitations[0].email).toBe("new@acme.com");
    expect(lastCall().data).toEqual({
      emails: ["new@acme.com"],
      organizationRoleId: "<ROLE-ID>",
    });
  });

  // ===== Roles, policies and permissions =====

  it("sends policy ids when creating a role", async () => {
    mockData({
      id: "<ROLE-ID>",
      name: "Analyst",
      description: "read only",
      policies: [],
      organizationId: "<ORGANIZATION-ID>",
    });

    const role = await makeClient().organization.createRole(
      "Analyst",
      ["<POLICY-ID>"],
      "read only",
    );

    expect(role.name).toBe("Analyst");
    expect(lastCall().data).toEqual({
      name: "Analyst",
      policyIds: ["<POLICY-ID>"],
      description: "read only",
    });
  });

  it("sends permission ids when creating a policy", async () => {
    mockData({
      id: "<POLICY-ID>",
      name: "Billing",
      description: null,
      permissions: [],
    });

    await makeClient().organization.createPolicy("Billing", [
      "<PERMISSION-ID>",
    ]);

    expect(lastCall().data).toEqual({
      name: "Billing",
      permissionIds: ["<PERMISSION-ID>"],
    });
  });

  it("lists permissions", async () => {
    mockData({
      permissions: [
        { id: "<PERMISSION-ID>", name: "billing:read", description: null },
      ],
    });

    const permissions = await makeClient().organization.listPermissions();

    expect(permissions.permissions[0].name).toBe("billing:read");
    expect(lastCall().url).toContain("/v2/organization/permissions");
  });

  // ===== Governance =====

  it("lists governance policies", async () => {
    mockData({
      governancePolicies: [
        {
          id: "<GOVERNANCE-POLICY-ID>",
          name: "Production Gate",
          description: null,
          projectsCount: 5,
          isBasePolicy: false,
          controls: [
            {
              id: "<CONTROL-ID>",
              name: "Logs traces",
              type: "PRE_DEPLOYMENT_EVALS",
            },
          ],
        },
      ],
    });

    const policies = await makeClient().organization.listGovernancePolicies();

    const policy = policies.governancePolicies[0];
    expect(policy.id).toBe("<GOVERNANCE-POLICY-ID>");
    expect(policy.projectsCount).toBe(5);
    expect(policy.isBasePolicy).toBe(false);
    expect(policy.controls[0].type).toBe("PRE_DEPLOYMENT_EVALS");
    expect(lastCall().url).toContain("/v2/organization/governance-policies");
  });

  it("paginates the projects of a governance policy", async () => {
    mockData({
      projects: [{ id: "<PROJECT-ID>", name: "Prod" }],
      totalGovernancePolicyProjects: 1,
      page: 2,
      pageSize: 50,
    });

    const projects =
      await makeClient().organization.listGovernancePolicyProjects(
        "<GOVERNANCE-POLICY-ID>",
        2,
        50,
      );

    expect(projects.projects[0].id).toBe("<PROJECT-ID>");
    expect(lastCall().params).toEqual({ page: 2, pageSize: 50 });
    expect(lastCall().url).toContain(
      "/v2/organization/governance-policies/<GOVERNANCE-POLICY-ID>/projects",
    );
  });

  it("assigns projects to a governance policy", async () => {
    mockData({
      governancePolicy: {
        id: "<GOVERNANCE-POLICY-ID>",
        name: "Production Gate",
      },
      assignedProjectIds: ["<PROJECT-ID>", "<OTHER-PROJECT-ID>"],
      notFoundProjectIds: [],
      count: 2,
    });

    const result =
      await makeClient().organization.assignProjectsToGovernancePolicy(
        "<GOVERNANCE-POLICY-ID>",
        ["<PROJECT-ID>", "<OTHER-PROJECT-ID>"],
      );

    expect(result.governancePolicy.id).toBe("<GOVERNANCE-POLICY-ID>");
    expect(result.assignedProjectIds).toEqual([
      "<PROJECT-ID>",
      "<OTHER-PROJECT-ID>",
    ]);
    expect(result.notFoundProjectIds).toEqual([]);
    expect(result.count).toBe(2);
    expect(lastCall().method).toBe("POST");
    expect(lastCall().data).toEqual({
      projectIds: ["<PROJECT-ID>", "<OTHER-PROJECT-ID>"],
    });
  });

  it("unassigns projects from a governance policy", async () => {
    mockData({
      governancePolicy: {
        id: "<GOVERNANCE-POLICY-ID>",
        name: "Production Gate",
      },
      unassignedProjectIds: ["<PROJECT-ID>"],
      skippedProjectIds: [],
      count: 1,
    });

    const result =
      await makeClient().organization.unassignProjectsFromGovernancePolicy(
        "<GOVERNANCE-POLICY-ID>",
        ["<PROJECT-ID>"],
      );

    expect(result.unassignedProjectIds).toEqual(["<PROJECT-ID>"]);
    expect(result.skippedProjectIds).toEqual([]);
    expect(result.count).toBe(1);
    expect(lastCall().method).toBe("POST");
    expect(lastCall().data).toEqual({ projectIds: ["<PROJECT-ID>"] });
  });
});
