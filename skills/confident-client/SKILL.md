---
name: confident-client
description: >
  Manage a Confident AI account programmatically with the Admin SDK (the
  `confidentai` package for Python and TypeScript). TRIGGER when the user wants
  to create, read, update, or delete organizations, projects, members,
  invitations, roles, policies, permissions, governance policies, or API keys on
  Confident AI; provision or rotate organization- and project-scoped API keys;
  onboard or offboard team members; set up RBAC (permissions → policies → roles →
  members); assign governance policies to projects; or automate project
  provisioning (project-per-agent,
  project-per-environment, project-per-customer). All administrative operations
  require an Organization API Key (`CONFIDENT_ORG_API_KEY`). DO NOT TRIGGER for
  sending traces or running evaluations against a project (that uses a project
  key `CONFIDENT_API_KEY` — see the `deepeval`, `deepeval-tracing`, and
  `deepeval-otel` skills); this skill is account and project administration
  only, not tracing or evals.
license: Apache-2.0
metadata:
  author: Confident AI
  version: "1.0.0"
  category: administration
  tags: "confident-ai, admin-sdk, confidentai, organizations, projects, members, invitations, rbac, roles, governance, api-keys"
  compatibility: "Python (`pip install confidentai`) or TypeScript (`npm install confidentai`). Every method requires an Organization API Key, read by default from `CONFIDENT_ORG_API_KEY` (distinct from the project-scoped `CONFIDENT_API_KEY` used for tracing and evals)."
---

# Confident AI Admin SDK

Use this skill to manage a **Confident AI account programmatically** with the
Admin SDK — the `confidentai` package, available for both Python and
TypeScript. The work is account and project administration: organizations,
projects, members and invitations, RBAC (permissions, policies, roles),
governance policies, and API keys.

This skill stops at administration. Sending traces and running evaluations
against a project is a different job with a different key — see the `deepeval`,
`deepeval-tracing`, and `deepeval-otel` skills.

## Scope: Account Administration Only

Use the Admin SDK for administrative workflows that would otherwise be done by
hand in the platform UI — project provisioning, member onboarding, role
synchronization, and API key rotation. Every operation is scoped to either the
**organization** (account-wide resources) or a single **project**
(project-scoped resources).

Do not reach for this skill to instrument an app or score outputs. Tracing and
evals authenticate with a project key (`CONFIDENT_API_KEY`); administration
authenticates with an Organization API Key (`CONFIDENT_ORG_API_KEY`).

## When to Use vs the Eval / Tracing Skills

- **This skill (`confident-client`)** — administer the account: create and
  rename the organization, CRUD projects, invite and manage members, define
  RBAC, and provision or rotate API keys. Requires an **Organization API Key**.
- **`deepeval` skill** — build pytest eval suites: datasets, metrics, traced
  evals, `deepeval test run`, iteration. Requires a **project key**.
- **`deepeval-tracing` skill** — instrument an app with the DeepEval SDK
  (`@observe`, integrations). Requires a **project key**.
- **`deepeval-otel` skill** — export raw OpenTelemetry / OTLP traces to
  Confident AI. Requires a **project key**.

## Prerequisites

- The Admin SDK installed: `pip install confidentai` (Python) or
  `npm install confidentai` (TypeScript).
- An **Organization API Key** (e.g. `confident_us_org_...`), read by default
  from the `CONFIDENT_ORG_API_KEY` environment variable. This is separate from
  the project-scoped `CONFIDENT_API_KEY` used for tracing and evals, so both can
  be configured at once. Retrieve the org key from the Confident AI settings
  under organization-level authentication.

## Language Detection

Each reference file contains both Python and TypeScript examples. Before writing
code, determine which language the user is working in, then use the matching
code block (```` ```python ```` or ```` ```typescript ````) within the
reference.

1. **Honor an explicit request first** — if the user names a language or shows a
   snippet, use that regardless of the project files.
2. **Otherwise infer from the project — but only for a _clean single-language_
   project** (markers from one ecosystem and none from the other):
   - Python markers: `*.py`, `pyproject.toml`, `requirements.txt`, `setup.py`, `Pipfile`, a `.venv`/`venv`
   - TypeScript/Node markers: `*.ts`, `*.tsx`, `package.json`, `tsconfig.json`, `node_modules` (JavaScript-only counts as TypeScript — same `confidentai` package)
3. **If markers from BOTH ecosystems are present — even if one side has more
   code — or the project is empty/unclear, it is AMBIGUOUS: STOP and ask which
   language before writing any code.** Do not rationalize a "dominant" or
   "obvious" language from which files happen to have more content (e.g. a
   populated `ts/` next to a bare `.venv` is still ambiguous). Fall back to
   **Python** (never TypeScript) only after asking and getting no answer, and say
   you're defaulting.

Within each reference, the code block for the target language is authoritative
for exact method names, argument shapes (keyword arguments vs an options
object), and casing (snake_case vs camelCase). Do not guess a binding from the
other language's examples.

## Workflow

1. Confirm the task is administration (managing orgs, projects, members, roles,
   or keys). If the user instead wants to send traces or run evals, stop and use
   the `deepeval` / `deepeval-tracing` / `deepeval-otel` skills.
2. Determine the target language — **Python** or **TypeScript** — using the
   **Language Detection** section above, then read `references/<topic>.md` and
   use the code blocks for that language.
3. Configure the client with an Organization API Key. Read
   `references/quickstart.md`.
4. Pick the right scope: organization-wide (`client.organization()`) vs a single
   project (`client.project(project_id)`). Read `references/introduction.md` for
   scope and capabilities.
5. Read the exact reference for the resource being managed
   (organization, projects, members and invitations, RBAC, governance policies,
   or API keys) before writing code, and follow its examples.
6. For RBAC, compose in order: list `permissions`, bundle them into `policies`,
   bundle policies into `roles`, then assign roles to members. Read
   `references/roles-policies-permissions.md`.
7. When creating an API key (or a project, which mints its first key), capture
   the full secret `value` immediately — it is shown only once. Read
   `references/api-keys.md`.

## Core Principles

1. Administration uses an **Organization API Key**
   (`CONFIDENT_ORG_API_KEY`), never a project key. Keep it out of source
   control and logs.
2. Choose scope deliberately: organization-scoped calls affect the whole
   account; project-scoped calls (`client.project(id)`) affect one project.
3. An API key's full secret `value` is returned **only at creation** (creating a
   project also mints its first project key). Store it securely then; later
   reads are masked.
4. RBAC composes in one direction: permissions → policies → roles → members.
   Permissions are predefined and read-only; you can only list them.
5. A user must be an **organization member** before being added to a project.
   Invitations create membership when accepted.
6. Destructive operations are irreversible — deleting a project permanently
   removes its datasets, prompts, traces, and evaluations; deleting a key
   immediately revokes it. Prefer disabling a key (set `valid` to false) over
   deleting when you only need to revoke temporarily.
7. Never hardcode secrets or raw sensitive data; prefer environment variables
   for keys.
8. Governance policies are **organization-scoped only** and read-only through
   the SDK — list them and assign/unassign them to projects, but do not expect
   create/update/delete. (Python only: every method also has an async `a_*`
   variant.)
9. **Clarify before mutating.** For create/update calls, confirm the required
   inputs and ask about consequential optional ones the user hasn't specified
   rather than silently omitting them or guessing. In particular: whether a new
   project should have an **owner** (`email`), and which **role** (`role_id`) to
   grant when inviting members or adding them to a project. Ask first, then act.

## References

Each topic has one reference file containing both Python and TypeScript
examples; use the code block matching the target language.

| Topic | File |
| --- | --- |
| Install, configure the Organization API Key, first call | `references/quickstart.md` |
| Read and rename the organization | `references/organization.md` |
| Create, read, update, delete projects | `references/projects.md` |
| Members, invitations, and role assignment | `references/members-and-invitations.md` |
| RBAC: permissions, policies, and roles | `references/roles-policies-permissions.md` |
| Provision, rotate, enable/disable, and delete API keys | `references/api-keys.md` |
| Governance policies: list and assign/unassign to projects (org-only) | `references/governance.md` |
| Admin SDK overview, org vs project scope, and key capabilities | `references/introduction.md` |
| Background: why observability matters for AI products | `references/ai-pm-observability.md` |
