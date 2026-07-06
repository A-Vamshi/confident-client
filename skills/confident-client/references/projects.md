# Projects

Source: https://www.confident-ai.com/docs/settings/project/management/projects

Projects are isolated workspaces for your datasets, prompts, traces, and
evaluations. With the Admin SDK you can create, update, and delete projects
programmatically. This supports project-per-agent, project-per-environment, and
project-per-customer organization models.

All methods here require an **Organization API Key**. See
`references/quickstart.md` to create a client. Each operation is shown for both
Python and TypeScript — use the code block matching your project.

## List Projects

List every project in your organization.

```python
from confidentai import ConfidentAI

client = ConfidentAI()

projects = client.projects.list()
for project in projects:
    print(project.id, project.name)
```

```typescript
import { ConfidentAI } from "confidentai";

const client = new ConfidentAI();

const projects = await client.projects.list();
projects.forEach((project) => console.log(project.id, project.name));
```

## Create a Project

Create a new project with just a `name`. Both `description` and `email` are
optional. Pass `email` to assign that user — by their email address — as the
project's **owner** (use this whenever the request is to create a project owned
by a specific person); the email must belong to an existing organization member.
Project names must be unique within the organization. Creating a project also
generates its first project API key, so the call returns both the `project` and
that API key — and the full secret is only available here.

If the request doesn't say who should own the project, **ask whether to assign
an owner (`email`) before creating** rather than silently omitting it.

```python
created = client.projects.create(
    "Customer Support Bot",
    description="Production support assistant",
    email="owner@example.com",  # optional — assigns this user as the project owner
)
print(created.project.id)  # e.g. "clq9z3x1k0001la08f7t3g5p2"
print(created.api_key.value)  # e.g. "confident_us_proj_...", shown only once
```

```typescript
const created = await client.projects.create({
  name: "Customer Support Bot",
  description: "Production support assistant",
  email: "owner@example.com", // optional — assigns this user as the project owner
});
console.log(created.project.id); // e.g. "clq9z3x1k0001la08f7t3g5p2"
console.log(created.apiKey?.value); // e.g. "confident_us_proj_...", shown only once
```

## Get a Project

Retrieve a single project by its ID.

```python
project = client.project("clq9z3x1k0001la08f7t3g5p2")
project.get()
```

```typescript
const project = client.project("clq9z3x1k0001la08f7t3g5p2");
await project.get();
```

## Update a Project

Update a project's `name`, `description`, or both; only the fields you pass are
changed.

```python
project = client.project("clq9z3x1k0001la08f7t3g5p2")
project.update(name="Support Bot (v2)")
```

```typescript
const project = client.project("clq9z3x1k0001la08f7t3g5p2");
await project.update({ name: "Support Bot (v2)" });
```

## Delete a Project

Permanently delete a project from your organization. This permanently removes
all of its datasets, prompts, traces, and evaluations, and cannot be undone.

```python
project = client.project("clq9z3x1k0001la08f7t3g5p2")
project.delete()
```

```typescript
const project = client.project("clq9z3x1k0001la08f7t3g5p2");
await project.delete();
```

## Next Steps

- Add users to projects and assign roles — `references/members-and-invitations.md`.
- Provision project-scoped API keys — `references/api-keys.md`.
