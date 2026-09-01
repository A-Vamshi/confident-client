/**
 * Verify how the two Confident AI credentials are resolved and kept apart.
 *
 * The SDK holds one credential per ApiKeyKind: an organization key for the
 * management API and a project key for project resources. Each resolves from
 * its own environment variable, and a client configured with only one kind must
 * still work for that kind while failing clearly for the other.
 */

import { ConfidentAI } from "../src";
import {
  API_BASE_URL_EU,
  API_KEY_HEADER,
  CONFIDENT_ORG_API_KEY_ENV_VAR,
  CONFIDENT_PROJ_API_KEY_ENV_VAR,
  Api,
  ApiKeyKind,
  Endpoints,
  HttpMethods,
  apiKeyClientOption,
  apiKeyEnvVar,
} from "../src/api";
import { clearConfidentEnv, lastCall, mockData, resetAxios } from "./helpers";

jest.mock("axios");

function projectApi(client: ConfidentAI): Api {
  return client["api"](ApiKeyKind.PROJECT);
}

function organizationApi(client: ConfidentAI): Api {
  return client["api"](ApiKeyKind.ORGANIZATION);
}

describe("credential resolution", () => {
  const ORIGINAL_ENV = { ...process.env };

  beforeEach(() => {
    resetAxios();
    clearConfidentEnv();
  });

  afterAll(() => {
    process.env = ORIGINAL_ENV;
  });

  it("names the env var for each key kind", () => {
    expect(apiKeyEnvVar(ApiKeyKind.ORGANIZATION)).toBe(
      CONFIDENT_ORG_API_KEY_ENV_VAR,
    );
    expect(apiKeyEnvVar(ApiKeyKind.PROJECT)).toBe(
      CONFIDENT_PROJ_API_KEY_ENV_VAR,
    );
  });

  it("names the client option for each key kind", () => {
    expect(apiKeyClientOption(ApiKeyKind.ORGANIZATION)).toBe("apiKey");
    expect(apiKeyClientOption(ApiKeyKind.PROJECT)).toBe("projectApiKey");
  });

  it("resolves the project key from its env var", () => {
    process.env[CONFIDENT_PROJ_API_KEY_ENV_VAR] = "confident_us_proj_env";
    const client = new ConfidentAI();
    expect(client.projectApiKey).toBe("confident_us_proj_env");
    expect(client.apiKey).toBeUndefined();
  });

  it("prefers an explicit project key over its env var", () => {
    process.env[CONFIDENT_PROJ_API_KEY_ENV_VAR] = "confident_us_proj_env";
    const client = new ConfidentAI({
      projectApiKey: "confident_us_proj_explicit",
    });
    expect(client.projectApiKey).toBe("confident_us_proj_explicit");
  });

  it("never supplies a project key from the organization env var", () => {
    process.env[CONFIDENT_ORG_API_KEY_ENV_VAR] = "confident_us_org_env";
    const client = new ConfidentAI();
    expect(client.apiKey).toBe("confident_us_org_env");
    expect(client.projectApiKey).toBeUndefined();
  });

  it("never supplies an organization key from the project env var", () => {
    process.env[CONFIDENT_PROJ_API_KEY_ENV_VAR] = "confident_us_proj_env";
    const client = new ConfidentAI();
    expect(client.projectApiKey).toBe("confident_us_proj_env");
    expect(client.apiKey).toBeUndefined();
  });

  it("builds a client from a project key alone", () => {
    const client = new ConfidentAI({ projectApiKey: "confident_us_proj_abc" });
    expect(client.projectApiKey).toBe("confident_us_proj_abc");
  });

  it("names both env vars when no key is available", () => {
    expect(() => new ConfidentAI()).toThrow(CONFIDENT_ORG_API_KEY_ENV_VAR);
    expect(() => new ConfidentAI()).toThrow(CONFIDENT_PROJ_API_KEY_ENV_VAR);
  });

  it("names the organization key when management is used without it", () => {
    const client = new ConfidentAI({ projectApiKey: "confident_us_proj_abc" });
    expect(() => client.organization()).toThrow(CONFIDENT_ORG_API_KEY_ENV_VAR);
    expect(() => client.organization()).toThrow(
      apiKeyClientOption(ApiKeyKind.ORGANIZATION),
    );
  });

  it("names the project key when project resources are used without it", () => {
    const client = new ConfidentAI({ apiKey: "confident_us_org_abc" });
    expect(() => projectApi(client)).toThrow(CONFIDENT_PROJ_API_KEY_ENV_VAR);
    expect(() => projectApi(client)).toThrow(
      apiKeyClientOption(ApiKeyKind.PROJECT),
    );
  });

  it("gives each key kind its own cached Api", () => {
    const client = new ConfidentAI({
      apiKey: "confident_us_org_abc",
      projectApiKey: "confident_us_proj_abc",
    });

    expect(organizationApi(client)).not.toBe(projectApi(client));
    expect(organizationApi(client)).toBe(organizationApi(client));
    expect(projectApi(client)).toBe(projectApi(client));
    expect(organizationApi(client).apiKey).toBe("confident_us_org_abc");
    expect(projectApi(client).apiKey).toBe("confident_us_proj_abc");
  });

  it("sends the project key as the request credential", async () => {
    const api = new Api({
      apiKey: "confident_us_proj_abc",
      keyKind: ApiKeyKind.PROJECT,
    });
    mockData({});
    await api.sendRequest(HttpMethods.GET, Endpoints.ORGANIZATION_ENDPOINT);
    expect(lastCall().headers[API_KEY_HEADER]).toBe("confident_us_proj_abc");
  });

  it("infers the region from the project key", () => {
    const client = new ConfidentAI({ projectApiKey: "confident_eu_proj_abc" });
    expect(client.baseUrl).toBe(API_BASE_URL_EU);
  });

  it("defaults an Api to the organization kind", () => {
    process.env[CONFIDENT_ORG_API_KEY_ENV_VAR] = "confident_us_org_env";
    const api = new Api({});
    expect(api.keyKind).toBe(ApiKeyKind.ORGANIZATION);
    expect(api.apiKey).toBe("confident_us_org_env");
  });
});
