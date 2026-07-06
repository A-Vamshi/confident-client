# API Keys

Source: https://www.confident-ai.com/docs/settings/project/management/api-keys

API keys authenticate requests to Confident AI, and come in two scopes:

- **Organization API keys** authenticate at the organization level. They're used
  for account-wide administration — including every management method in this
  SDK.
- **Project API keys** are scoped to a single project. They're the keys your
  application uses to send traces and run evaluations against that project.

Use the Admin SDK to list, create, enable, disable, and delete keys at either
scope.

```
Organization API Key → authenticates account-wide management (this SDK)
Project API Key       → authenticates traces & evaluations in one project
```

The full secret `value` of an API key is **only returned when it is created**.
Subsequent reads return a masked value, so store the secret securely at creation
time.

All methods here require an **Organization API Key**. See
`references/quickstart.md` to create a client. Each operation is shown for both
Python and TypeScript — use the code block matching your project.

## List API Keys

List every API key at the organization or project level, with secret values
masked.

```python
from confidentai import ConfidentAI

client = ConfidentAI()

org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

api_keys = org.api_keys.list()
project_api_keys = project.api_keys.list()
```

```typescript
import { ConfidentAI } from "confidentai";

const client = new ConfidentAI();

const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

const apiKeys = await org.apiKeys.list();
const projectApiKeys = await project.apiKeys.list();
```

## Get an API Key

Retrieve a single API key by its ID, with its secret value masked.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

api_key = org.api_keys.get(7)
project_api_key = project.api_keys.get(7)
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

const apiKey = await org.apiKeys.get(7);
const projectApiKey = await project.apiKeys.get(7);
```

## Create an API Key

Create a new key at the organization or project level. The returned object's
`value` is the full secret, so store it securely when the key is created.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

api_key = org.api_keys.create("ci-pipeline")
print(api_key.value)  # e.g. "confident_us_org_...", shown only once

project_api_key = project.api_keys.create("ci-pipeline")
print(project_api_key.value)  # e.g. "confident_us_proj_..."
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

const apiKey = await org.apiKeys.create({ name: "ci-pipeline" });
console.log(apiKey.value); // e.g. "confident_us_org_...", shown only once

const projectApiKey = await project.apiKeys.create({ name: "ci-pipeline" });
console.log(projectApiKey.value); // e.g. "confident_us_proj_..."
```

## Enable or Disable an API Key

Set `valid` to false to revoke a key without deleting it, or back to true to
re-enable it.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

api_key = org.api_keys.update(7, valid=False)
project_api_key = project.api_keys.update(7, valid=False)
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

const apiKey = await org.apiKeys.update(7, { valid: false });
const projectApiKey = await project.apiKeys.update(7, { valid: false });
```

## Delete an API Key

Permanently delete an API key by its ID, which immediately revokes it.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

org.api_keys.delete(7)
project.api_keys.delete(7)
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

await org.apiKeys.delete(7);
await project.apiKeys.delete(7);
```

## Next Steps

- Learn how organization- and project-level auth works (Confident AI
  authentication docs).
- Manage the projects your keys are scoped to — `references/projects.md`.
