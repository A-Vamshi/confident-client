# Introduction to the Admin SDK

Source: https://www.confident-ai.com/docs/settings/project/management/introduction

The Admin SDK lets you manage organizations, projects, team members, roles,
governance policies, and API keys programmatically. It is available for Python
and TypeScript through the `confidentai` package.

Use the Admin SDK when administrative workflows need to run programmatically
instead of through the platform UI. Common use cases: project provisioning,
member onboarding, role synchronization, and API key rotation.

All management operations require an **Organization API Key**. See the
quickstart for your language to create a configured client, and the Confident AI
authentication docs (organization-level auth) for retrieving the key.

## Reference Convention

Every topic below has one reference file (`references/<topic>.md`) containing
both Python and TypeScript examples. Within each file, use the code block for
your language (```` ```python ```` or ```` ```typescript ````). The APIs are
otherwise equivalent; only idioms differ (snake_case vs camelCase, keyword
arguments vs an options object, and `await` in TypeScript).

## Organization vs Project Scope

Every Admin SDK operation is scoped to either the organization or a single
project. The scope determines whether an operation affects account-wide
resources or resources inside one project.

- **Organization-scoped** resources operate across the entire organization —
  `client.organization()`.
- **Project-scoped** resources operate within a single project —
  `client.project(project_id)`.

## Key Capabilities

Each capability links to its reference below (both Python and TypeScript
examples live in the same file).

- **Organization** — read and rename the organization tied to your API key.
  See `references/organization.md`.
- **Projects** — create, read, update, and delete projects.
  See `references/projects.md`.
- **Members & invitations** — invite members, manage memberships, and assign
  roles. See `references/members-and-invitations.md`.
- **RBAC** — define roles, policies, and permissions.
  See `references/roles-policies-permissions.md`.
- **API keys** — provision and rotate organization- and project-scoped keys.
  See `references/api-keys.md`.
- **Governance policies** (organization scope only) — list compliance policies
  and assign/unassign them to projects.
  See `references/governance.md`.
