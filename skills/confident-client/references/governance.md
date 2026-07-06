# Governance Policies

Governance policies are **organization-level** bundles of compliance _controls_
(for example, `PRE_DEPLOYMENT_EVALS`) that you attach to projects to enforce
standards across the account. They are defined in the platform and are
**read-only** through the SDK: you can list them, see which projects they cover,
and assign or unassign them to projects — but you cannot create, update, or
delete them here.

Governance exists **only at the organization scope** (`client.organization()`);
there is no project-scoped governance client. A project's currently attached
policy is visible on the project itself (`project.governance_policy` in Python,
`project.governancePolicy` in TypeScript).

All methods here require an **Organization API Key**. See
`references/quickstart.md` to create a client. Each operation is shown for both
Python and TypeScript — use the code block matching your project.

## List Governance Policies

List every governance policy in the organization. Each policy includes its
`controls` and a count of the projects it covers.

```python
from confidentai import ConfidentAI

client = ConfidentAI()

policies = client.organization().governance.policies.list()
for policy in policies:
    print(policy.id, policy.name, policy.projects_count)
    for control in policy.controls:
        print("  control:", control.name, control.type)
```

```typescript
import { ConfidentAI } from "confidentai";

const client = new ConfidentAI();

const policies = await client.organization().governance.policies.list();
policies.forEach((policy) => {
  console.log(policy.id, policy.name, policy.projectsCount);
  policy.controls.forEach((control) =>
    console.log("  control:", control.name, control.type),
  );
});
```

## List Projects Covered by a Policy

List the projects a governance policy is assigned to, by its ID. Supports page
and page size for pagination.

```python
governance = client.organization().governance.policies

projects = governance.list_projects("gp1", page=1, page_size=25)
for project in projects:
    print(project.id, project.name)
```

```typescript
const governance = client.organization().governance.policies;

const projects = await governance.listProjects("gp1", {
  page: 1,
  pageSize: 25,
});
projects.forEach((project) => console.log(project.id, project.name));
```

## Assign a Policy to Projects

Attach a governance policy to one or more projects by their ids. The result
reports which project ids were assigned and which were not found. A project can
have at most one governance policy, so assigning **moves** each project off any
policy it was already on (re-assigning the same policy is a no-op).

```python
governance = client.organization().governance.policies

result = governance.assign("gp1", project_ids=["p1", "p2"])
print(result.assigned_project_ids)   # e.g. ["p1", "p2"]
print(result.not_found_project_ids)  # e.g. []
print(result.count)
```

```typescript
const governance = client.organization().governance.policies;

const result = await governance.assign("gp1", { projectIds: ["p1", "p2"] });
console.log(result.assignedProjectIds); // e.g. ["p1", "p2"]
console.log(result.notFoundProjectIds); // e.g. []
console.log(result.count);
```

## Unassign a Policy from Projects

Detach a governance policy from projects by their ids. The result reports which
projects were unassigned and any that were skipped (projects the policy was not
assigned to).

```python
governance = client.organization().governance.policies

result = governance.unassign("gp1", project_ids=["p1"])
print(result.unassigned_project_ids)  # e.g. ["p1"]
print(result.skipped_project_ids)     # e.g. []
print(result.count)
```

```typescript
const governance = client.organization().governance.policies;

const result = await governance.unassign("gp1", { projectIds: ["p1"] });
console.log(result.unassignedProjectIds); // e.g. ["p1"]
console.log(result.skippedProjectIds); // e.g. []
console.log(result.count);
```

## Next Steps

- Manage the projects governance policies apply to — `references/projects.md`.
- Define who can administer the account — `references/roles-policies-permissions.md`.
