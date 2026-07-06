# Organization

Source: https://www.confident-ai.com/docs/settings/project/management/organization

Your organization is the top-level account that owns every project, member,
role, and API key. With the Admin SDK you can read and rename the organization
tied to your API key.

All methods here require an **Organization API Key**. See
`references/quickstart.md` to create a client. Each operation is shown for both
Python and TypeScript — use the code block matching your project.

## Get Your Organization

Retrieve the organization tied to your API key, including its `id` and `name`.

```python
from confidentai import ConfidentAI

client = ConfidentAI()

org = client.organization()
organization = org.get()
print(organization.id, organization.name)
```

```typescript
import { ConfidentAI } from "confidentai";

const client = new ConfidentAI();

const org = client.organization();
const organization = await org.get();
console.log(organization.id, organization.name);
```

## Rename Your Organization

Update your organization's `name`.

```python
org = client.organization()
organization = org.update(name="Example Org")
```

```typescript
const org = client.organization();
const organization = await org.update({ name: "Example Org" });
```

## Next Steps

- Create, update, and delete projects — `references/projects.md`.
- Invite members and assign roles — `references/members-and-invitations.md`.
