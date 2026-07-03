# Roles, Policies & Permissions (RBAC)

Source: https://www.confident-ai.com/docs/settings/project/management/roles-policies-permissions

Confident AI uses role-based access control (RBAC). Access is granted by
composing three building blocks — bundle permissions into policies, bundle
policies into roles, then assign roles to members:

- **Permissions** are the atomic actions you can grant (e.g. `traces:read`).
  They are predefined by the platform, so you can only list them.
- **Policies** are named bundles of permissions.
- **Roles** are named bundles of policies that you assign to members.

```
Permissions (atomic actions)
  → bundled into Policies
      → bundled into Roles
          → assigned to Members
```

Each building block exists independently at both the **organization** and
**project** level. Organization-level roles govern access across the
organization; project-level roles govern access within a single project.

All methods here require an **Organization API Key**. See
`references/quickstart.md` to create a client. Permissions, policies, and roles
are grouped under the **`iam`** namespace on both clients —
`client.organization().iam` and `client.project(id).iam`. Each operation is
shown for both Python and TypeScript — use the code block matching your project.

## Permissions

Permissions are read-only. List them to discover the ids to attach to policies.

```python
from confidentai import ConfidentAI

client = ConfidentAI()

org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

permissions = org.iam.permissions.list()
project_permissions = project.iam.permissions.list()
```

```typescript
import { ConfidentAI } from "confidentai";

const client = new ConfidentAI();

const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

const permissions = await org.iam.permissions.list();
const projectPermissions = await project.iam.permissions.list();
```

## Policies

A policy bundles permissions together. Provide the permission ids from the
permissions listing above. Each policy takes a name, a list of permission ids,
and an optional description.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

# List
policies = org.iam.policies.list()
project_policies = project.iam.policies.list()

# Create
policy = org.iam.policies.create(
    "Dataset Editor",
    permission_ids=["5e9a1c3d-7b2f-4e8a-9c1d-3a6b5f0e2d4c", "8d2c4f6a-1e3b-4c7d-9a5e-2b8f1d0c6a3e"],
    description="Can edit datasets",
)

# Update
policy = org.iam.policies.update(
    "a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d",
    name="Dataset Editor",
    permission_ids=["5e9a1c3d-7b2f-4e8a-9c1d-3a6b5f0e2d4c", "8d2c4f6a-1e3b-4c7d-9a5e-2b8f1d0c6a3e", "2a7e9c1d-4b6f-4a8c-1d3e-7f5a9b2c0e4d"],
)

# Delete
org.iam.policies.delete("a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d")
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

// List
const policies = await org.iam.policies.list();
const projectPolicies = await project.iam.policies.list();

// Create
const policy = await org.iam.policies.create({
  name: "Dataset Editor",
  permissionIds: [
    "5e9a1c3d-7b2f-4e8a-9c1d-3a6b5f0e2d4c",
    "8d2c4f6a-1e3b-4c7d-9a5e-2b8f1d0c6a3e",
  ],
  description: "Can edit datasets",
});

// Update
const updatedPolicy = await org.iam.policies.update(
  "a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d",
  {
    name: "Dataset Editor",
    permissionIds: [
      "5e9a1c3d-7b2f-4e8a-9c1d-3a6b5f0e2d4c",
      "8d2c4f6a-1e3b-4c7d-9a5e-2b8f1d0c6a3e",
      "2a7e9c1d-4b6f-4a8c-1d3e-7f5a9b2c0e4d",
    ],
  },
);

// Delete
await org.iam.policies.delete("a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d");
```

Project-scoped policies use the same list, create, update, and delete operations
as organization-scoped policies.

## Roles

A role bundles policies together and is assigned to members. Provide the policy
ids from the policies above. Each role takes a name, a list of policy ids, and
an optional description.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

# List
roles = org.iam.roles.list()
project_roles = project.iam.roles.list()

# Create
role = org.iam.roles.create(
    "Data Scientist",
    policy_ids=["a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d"],
    description="Read/write datasets and prompts",
)

# Update
role = org.iam.roles.update(
    "b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
    name="Data Scientist",
    policy_ids=["a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d", "c4f8a2e6-1d3b-4e9a-8c7d-5b2f1a0e6d3c"],
)

# Delete
org.iam.roles.delete("b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e")
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

// List
const roles = await org.iam.roles.list();
const projectRoles = await project.iam.roles.list();

// Create
const role = await org.iam.roles.create({
  name: "Data Scientist",
  policyIds: ["a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d"],
  description: "Read/write datasets and prompts",
});

// Update
const updatedRole = await org.iam.roles.update(
  "b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
  {
    name: "Data Scientist",
    policyIds: [
      "a17c4e2d-9b3f-4a6c-8d1e-2f5a9c3b7e0d",
      "c4f8a2e6-1d3b-4e9a-8c7d-5b2f1a0e6d3c",
    ],
  },
);

// Delete
await org.iam.roles.delete("b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e");
```

Project-scoped roles use the same list, create, update, and delete operations as
organization-scoped roles.

Role and policy names must be unique within their scope, and a custom role can't
reuse a built-in role name (for example `Owner` or `Admin`).

## Next Steps

- Assign roles to members and invitees — `references/members-and-invitations.md`.
