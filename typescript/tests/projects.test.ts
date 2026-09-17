import { ConfidentAI } from "../src";
import { clearConfidentEnv, lastCall, mockData, resetAxios } from "./helpers";

jest.mock("axios");

function makeClient(): ConfidentAI {
  return new ConfidentAI({ apiKey: "confident_us_org_testkey" });
}

const aProject = (overrides: Record<string, unknown> = {}) => ({
  id: "<PROJECT-ID>",
  name: "Prod",
  description: null,
  organizationId: "<ORGANIZATION-ID>",
  created_at: "2026-01-01T00:00:00.000Z",
  governancePolicy: null,
  ...overrides,
});

describe("projects", () => {
  beforeEach(() => {
    resetAxios();
    clearConfidentEnv();
  });

  // ===== The collection =====

  it("reads every project", async () => {
    mockData({ projects: [aProject()] });

    const projects = await makeClient().projects.list();

    expect(projects.projects[0].id).toBe("<PROJECT-ID>");
    expect(projects.projects[0].organizationId).toBe("<ORGANIZATION-ID>");
    expect(lastCall().method).toBe("GET");
    expect(lastCall().url).toContain("/v2/projects");
  });

  it("returns the project and its first API key on create", async () => {
    mockData({
      project: {
        id: "<PROJECT-ID>",
        name: "New",
        description: "desc",
        organizationId: "<ORGANIZATION-ID>",
        created_at: "2026-01-01T00:00:00.000Z",
      },
      apiKey: {
        id: 7,
        name: "Default Key",
        valid: true,
        value: "confident_us_proj_secret",
        shadowValue: null,
        rotatesAt: null,
        created_at: "2026-01-01T00:00:00.000Z",
        lastUsed: null,
        expiresAt: null,
      },
    });

    const created = await makeClient().projects.create("New", "desc");

    expect(created.project.id).toBe("<PROJECT-ID>");
    expect(created.apiKey?.value).toBe("confident_us_proj_secret");
    expect(lastCall().method).toBe("POST");
    expect(lastCall().data).toEqual({ name: "New", description: "desc" });
  });

  it("gets, updates and deletes by id", async () => {
    const client = makeClient();

    mockData(aProject());
    const fetched = await client.projects.get("<PROJECT-ID>");
    expect(fetched.name).toBe("Prod");
    expect(lastCall().url).toContain("/v2/projects/<PROJECT-ID>");

    mockData(aProject({ name: "Renamed" }));
    const updated = await client.projects.update("<PROJECT-ID>", "Renamed");
    expect(updated.name).toBe("Renamed");
    expect(lastCall().method).toBe("PUT");
    expect(lastCall().data).toEqual({ name: "Renamed" });

    mockData({ id: "<PROJECT-ID>" });
    const deleted = await client.projects.delete("<PROJECT-ID>");
    expect(deleted.id).toBe("<PROJECT-ID>");
    expect(lastCall().method).toBe("DELETE");
  });

  // ===== The handle =====

  it("holds the project id", () => {
    const project = makeClient().project("<PROJECT-ID>");

    expect(project.projectId).toBe("<PROJECT-ID>");
  });

  it("says so when it has no id", async () => {
    await expect(makeClient().project().get()).rejects.toThrow(/no projectId/);
  });

  it("fills the handle and returns it on get", async () => {
    mockData(aProject({ description: "The production project" }));
    const project = makeClient().project("<PROJECT-ID>");

    const returned = await project.get();

    // A load returns the handle itself, so a caller can chain off it.
    expect(returned).toBe(project);
    expect(project.name).toBe("Prod");
    expect(project.description).toBe("The production project");
    expect(project.organizationId).toBe("<ORGANIZATION-ID>");
    expect(lastCall().url).toContain("/v2/projects/<PROJECT-ID>");
  });

  it("sends what the handle holds on update", async () => {
    mockData(aProject());
    const project = await makeClient().project("<PROJECT-ID>").get();

    project.name = "Renamed";
    mockData(aProject({ name: "Renamed" }));
    const result = await project.update();

    expect(result.name).toBe("Renamed");
    expect(lastCall().method).toBe("PUT");
    // The handle loaded `description: null`, and this SDK sends it. Python
    // dumps the body with `exclude_none=True` and omits it instead, so the
    // two SDKs put different bodies on the wire for the same calls — see the
    // note on the same test in the Python twin.
    expect(lastCall().data).toEqual({ name: "Renamed", description: null });
    expect(lastCall().url).toContain("/v2/projects/<PROJECT-ID>");
  });

  it("needs no argument to delete", async () => {
    mockData({ id: "<PROJECT-ID>" });

    const deleted = await makeClient().project("<PROJECT-ID>").delete();

    expect(deleted.id).toBe("<PROJECT-ID>");
    expect(lastCall().method).toBe("DELETE");
    expect(lastCall().url).toContain("/v2/projects/<PROJECT-ID>");
  });

  it("scopes a sub-resource path", async () => {
    mockData({ apiKeys: [] });

    await makeClient().project("<PROJECT-ID>").listApiKeys();

    expect(lastCall().url).toContain("/v2/projects/<PROJECT-ID>/api-keys");
  });

  it("sends the project role id when inviting", async () => {
    mockData({
      invitations: [
        {
          id: 1,
          email: "new@acme.com",
          status: "PENDING",
          created_at: "2026-01-01T00:00:00.000Z",
          projectRoleId: "<PROJECT-ROLE-ID>",
          token: null,
        },
      ],
    });

    await makeClient()
      .project("<PROJECT-ID>")
      .createInvitations(["new@acme.com"], "<PROJECT-ROLE-ID>");

    expect(lastCall().data).toEqual({
      emails: ["new@acme.com"],
      projectRoleId: "<PROJECT-ROLE-ID>",
    });
    expect(lastCall().url).toContain("/v2/projects/<PROJECT-ID>/invitations");
  });

  it("returns the project role when updating a member", async () => {
    mockData({
      id: "<USER-ID>",
      email: "engineer@acme.com",
      name: "Sam Rivera",
      image: null,
      projectRole: { id: "<PROJECT-ROLE-ID>", name: "Owner" },
    });

    const member = await makeClient()
      .project("<PROJECT-ID>")
      .updateMemberRole("<USER-ID>", "<PROJECT-ROLE-ID>");

    expect(member.projectRole?.name).toBe("Owner");
    expect(lastCall().data).toEqual({ roleId: "<PROJECT-ROLE-ID>" });
    expect(lastCall().url).toContain(
      "/v2/projects/<PROJECT-ID>/members/<USER-ID>",
    );
  });
});
