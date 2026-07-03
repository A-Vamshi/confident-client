# Admin SDK Quickstart

Source: https://www.confident-ai.com/docs/settings/project/management/quickstart

Install the SDK, configure it with an Organization API Key, create a client, and
make a first management call. Each operation is shown for both Python and
TypeScript — use the code block matching your project.

## Install

```bash
# Python
pip install confidentai
```

```bash
# TypeScript
npm install confidentai
```

## Configure the Organization API Key

The `ConfidentAI` client requires an **Organization API Key**, which is separate
from the project keys used for tracing and evaluations. The client reads the
`CONFIDENT_ORG_API_KEY` environment variable by default. Because this is
distinct from `CONFIDENT_API_KEY` (tracing/evals), both can be configured at
once.

```bash
export CONFIDENT_ORG_API_KEY="confident_us_org_..."
```

```python
from confidentai import ConfidentAI

client = ConfidentAI()
```

```typescript
import { ConfidentAI } from "confidentai";

const client = new ConfidentAI();
```

You can also pass the key explicitly instead of relying on the environment
variable. This is useful when managing multiple organizations from the same
process.

```python
client = ConfidentAI(api_key="confident_us_org_...")
```

```typescript
const client = new ConfidentAI({ apiKey: "confident_us_org_..." });
```

## Verify the Client

List the projects in your organization to confirm the client is configured
correctly. `client.whoami()` is a shortcut that returns the organization tied to
your key (equivalent to `client.organization().get()`).

```python
# List the projects in your organization
for project in client.projects.list():
    print(project.id, project.name)

# Confirm which organization the key belongs to
org = client.whoami()
print(org.id, org.name)
```

```typescript
// List the projects in your organization
const projects = await client.projects.list();
projects.forEach((project) => console.log(project.id, project.name));

// Confirm which organization the key belongs to
const org = await client.whoami();
console.log(org.id, org.name);
```

## Async (Python)

In Python, every method has an async variant prefixed with `a_` — e.g. `a_list`,
`a_create`, `a_get`, `a_update`, `a_delete`, and `client.a_whoami()`. The
signatures match their sync counterparts; call them with `await` from async
code. (TypeScript is asynchronous by default — every method already returns a
promise.)

```python
import asyncio
from confidentai import ConfidentAI

client = ConfidentAI()

async def main():
    projects = await client.projects.a_list()
    org = await client.a_whoami()
    print(org.id, len(projects))

asyncio.run(main())
```

## Next Steps

- Create, update, and delete projects — `references/projects.md`.
- Manage organization and project membership — `references/members-and-invitations.md`.
- Manage roles, policies, and permissions — `references/roles-policies-permissions.md`.
- Automate key provisioning and rotation — `references/api-keys.md`.
