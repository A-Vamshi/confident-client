# Members and Invitations

Source: https://www.confident-ai.com/docs/settings/project/management/members-and-invitations

Members are the people with access to your account, and they exist at two
levels:

- **Organization members** belong to your entire organization. Invited users
  become organization members and can receive an organization-level role.
- **Project members** belong to a single project. Add organization members to
  projects to grant project access with a project-level role.

A user must be an organization member before they can be added to a project. New
members join by accepting an invitation, and project membership grants access to
specific projects.

```
Invitation (email + optional role)
  → Organization Member (organization-level role)
      → Project A Member (project-level role)
      → Project B Member (project-level role)
```

All methods here require an **Organization API Key**. See
`references/quickstart.md` to create a client. Each operation is shown for both
Python and TypeScript — use the code block matching your project.

## Members

### List Members

List members page by page; the listing defaults to the first page and a page
size of 25.

```python
from confidentai import ConfidentAI

client = ConfidentAI()

org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

# Organization members
members = org.members.list(page=1, page_size=25)

# Project members
project_members = project.members.list(page=1)
```

```typescript
import { ConfidentAI } from "confidentai";

const client = new ConfidentAI();

const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

// Organization members
const members = await org.members.list({ page: 1, pageSize: 25 });

// Project members
const projectMembers = await project.members.list({ page: 1 });
```

### Update a Member's Role

Assign a role to a member by their user ID. Roles are managed in
`references/roles-policies-permissions.md`.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

# Organization-level role
member = org.members.update_role("clq8n3p9k0002la09a1b7c4d2", role_id="b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e")

# Project-level role
project_member = project.members.update_role("clq8n3p9k0002la09a1b7c4d2", role_id="b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e")
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

// Organization-level role
const member = await org.members.updateRole("clq8n3p9k0002la09a1b7c4d2", {
  roleId: "b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
});

// Project-level role
const projectMember = await project.members.updateRole(
  "clq8n3p9k0002la09a1b7c4d2",
  {
    roleId: "b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
  },
);
```

The Owner is protected: you can't change the Owner's role or remove the Owner
directly. Assigning the Owner role to another member instead **transfers
ownership**, demoting the previous Owner (to Admin at the organization level,
Manager at the project level).

### Remove a Member

Remove a member from your organization or a specific project by their user ID.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

org.members.remove("clq8n3p9k0002la09a1b7c4d2")
project.members.remove("clq8n3p9k0002la09a1b7c4d2")
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

await org.members.remove("clq8n3p9k0002la09a1b7c4d2");
await project.members.remove("clq8n3p9k0002la09a1b7c4d2");
```

## Invitations

Invite new people to your organization or projects, and manage invitations that
are still pending.

### List Invitations

List the pending invitations at the organization or project level.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

invitations = org.invitations.list()
project_invitations = project.invitations.list()
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

const invitations = await org.invitations.list();
const projectInvitations = await project.invitations.list();
```

### Create Invitations

Invite one or more emails at once; the optional role ID assigns a role to
invitees when they join.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

# Organization invitations
invitations = org.invitations.create(
    ["alice@example.com", "bob@example.com"],
    role_id="b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
)

# Project invitations
project_invitations = project.invitations.create(
    ["alice@example.com"],
    role_id="b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
)
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

// Organization invitations
const invitations = await org.invitations.create({
  emails: ["alice@example.com", "bob@example.com"],
  roleId: "b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
});

// Project invitations
const projectInvitations = await project.invitations.create({
  emails: ["alice@example.com"],
  roleId: "b3f1c2a9-7d4e-4c1b-9a2f-1e6d8c0a4b7e",
});
```

Inviting requires a paid plan, and you can't invite anyone as Owner. Emails that
are already invited or already members are skipped, so the returned list may be
shorter than the emails you passed.

### Resend & Revoke Invitations

Resend a pending invitation by its ID, or revoke it to cancel access before it's
accepted.

```python
org = client.organization()
project = client.project("clq9z3x1k0001la08f7t3g5p2")

# Resend
org.invitations.resend(42)
project.invitations.resend(42)

# Revoke
org.invitations.revoke(42)
project.invitations.revoke(42)
```

```typescript
const org = client.organization();
const project = client.project("clq9z3x1k0001la08f7t3g5p2");

// Resend
await org.invitations.resend(42);
await project.invitations.resend(42);

// Revoke
await org.invitations.revoke(42);
await project.invitations.revoke(42);
```

## Next Steps

- Define roles before assigning access — `references/roles-policies-permissions.md`.
- Manage the projects members belong to — `references/projects.md`.
