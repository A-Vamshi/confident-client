import {
  Api,
  ApiKeyKind,
  DEFAULT_TIMEOUT_MS,
  apiKeyClientOption,
  apiKeyEnvVar,
  getBaseApiUrl,
  getConfidentApiKey,
} from "./api";
import { OrganizationClient } from "./organization/client";
import { ProjectClient, ProjectsClient } from "./projects/client";
import { Organization } from "./types";

export interface ConfidentAIOptions {
  apiKey?: string;
  projectApiKey?: string;
  baseUrl?: string;
  timeout?: number;
}

const KEY_KINDS = [ApiKeyKind.ORGANIZATION, ApiKeyKind.PROJECT] as const;

export class ConfidentAI {
  private readonly apiKeys: Record<ApiKeyKind, string | undefined>;
  private readonly explicitBaseUrl?: string;
  private readonly explicitTimeout?: number;
  private readonly apis = new Map<ApiKeyKind, Api>();

  constructor(options: ConfidentAIOptions = {}) {
    this.apiKeys = {
      [ApiKeyKind.ORGANIZATION]: options.apiKey,
      [ApiKeyKind.PROJECT]: options.projectApiKey,
    };
    this.explicitBaseUrl = options.baseUrl;
    this.explicitTimeout = options.timeout;

    if (!KEY_KINDS.some((keyKind) => this.resolve(keyKind))) {
      throw new Error(
        `No Confident AI API key found. Set ${apiKeyEnvVar(
          ApiKeyKind.ORGANIZATION,
        )} for organization management or ${apiKeyEnvVar(
          ApiKeyKind.PROJECT,
        )} for project resources, or pass { ${apiKeyClientOption(
          ApiKeyKind.ORGANIZATION,
        )} } / { ${apiKeyClientOption(ApiKeyKind.PROJECT)} } explicitly.`,
      );
    }
  }

  private resolve(keyKind: ApiKeyKind): string | undefined {
    return getConfidentApiKey(this.apiKeys[keyKind], keyKind);
  }

  private api(keyKind: ApiKeyKind): Api {
    const existing = this.apis.get(keyKind);
    if (existing) return existing;

    const api = new Api({
      apiKey: this.apiKeys[keyKind],
      baseUrl: this.explicitBaseUrl,
      timeout: this.explicitTimeout,
      keyKind,
    });
    this.apis.set(keyKind, api);
    return api;
  }

  get apiKey(): string | undefined {
    return this.resolve(ApiKeyKind.ORGANIZATION);
  }

  get projectApiKey(): string | undefined {
    return this.resolve(ApiKeyKind.PROJECT);
  }

  get baseUrl(): string {
    return getBaseApiUrl(
      this.apiKey ?? this.projectApiKey,
      this.explicitBaseUrl,
    );
  }

  get timeout(): number {
    return this.explicitTimeout ?? DEFAULT_TIMEOUT_MS;
  }

  get projects(): ProjectsClient {
    return new ProjectsClient(this.api(ApiKeyKind.ORGANIZATION));
  }

  organization(): OrganizationClient {
    return new OrganizationClient(this.api(ApiKeyKind.ORGANIZATION));
  }

  project(projectId: string): ProjectClient {
    return new ProjectClient(this.api(ApiKeyKind.ORGANIZATION), projectId);
  }

  whoami(): Promise<Organization> {
    return this.organization().get();
  }
}
