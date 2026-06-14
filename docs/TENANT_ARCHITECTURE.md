# Tenant / Workspace Architecture

## Concept

A **Workspace** is the tenant boundary. Every piece of data belongs to exactly one workspace. Users can belong to multiple workspaces but operate within one at a time (the "active workspace").

---

## Layers

### 1. Storage — Thread-local tenant

**`core/tenant.py`**

```python
set_current_tenant(ws)   # store in threading.local()
get_current_tenant()     # retrieve
clear_current_tenant()   # clean up
tenant_context(None)     # context manager to temporarily disable
```

Pure thread-local storage — no DB, no cache. Each request thread holds its own tenant reference.

### 2. Middleware — Wires session → thread-local

**`core/middleware.py → TenantMiddleware`** (runs after `AuthenticationMiddleware`)

```
Request arrives
  → user authenticated?
    → session has active_workspace_id?
      → membership valid? → request.tenant = workspace, set_current_tenant(workspace)
      → invalid?          → clear session key, request.tenant = None
    → no active_ws        → request.tenant = None, set_current_tenant(None)
  → not authenticated     → request.tenant = None

Response sent
  → clear_current_tenant()
```

### 3. Manager — Auto-scopes all queries

**`core/tenant.py → TenantManager`**

13 models assign `objects = TenantManager()`:

| App | Models |
|---|---|
| `campaigns` | `Campaign`, `EmailTemplate` |
| `senders` | `Sender` |
| `inbox` | `EmailInbox` |
| `contacts` | `ContactList`, `Contact`, `ContactTag`, `ContactListTag` |
| `social_accounts` | `SocialPost` |
| `content_studio` | `ContentItem` |
| `media_assets` | `MediaFolder`, `MediaAsset` |
| `automations` | `Workflow` |


When `get_current_tenant()` returns a workspace, `TenantManager.get_queryset()` appends `.filter(workspace=tenant)` to every query — `Model.objects.all()` becomes `SELECT ... WHERE workspace_id = <active>` automatically.

When no tenant is active (personal mode), no filter is added — all records are visible.

### 4. Safety net — Explicit scoping

**`apps/workspaces/query_helpers.py → filter_by_context()`**

Explicit function used in views as a second layer:

- If tenant is active → filters by `workspace=tenant`
- If no tenant but `active_workspace_id` in session → validates membership, filters by workspace
- Otherwise → filters by `user=request.user` (personal mode)
- Superuser/staff → bypass all filters

---

## Access Control

### Roles (`WorkspaceMembership`)

| Role | Scope |
|---|---|
| **Owner** | Full access, can manage everything |
| **Admin** | Full module access, can manage members/settings |
| **Member** | Can use features (campaigns, content, social) but not settings/billing |

### Permissions (`WorkspacePermission`)

Per-module CRUD toggles per role. Module list: `campaigns`, `contacts`, `social`, `media`, `workflows`, `inbox`, `content_studio`, `workspace`, `billing`, `audit_log`, `storage`, `members`, `export`.

Defaults defined in `DEFAULT_PERMISSIONS` dict in `models.py`, seeded via `seed_default_permissions()` at workspace creation.

### Template tags (`workspace_tags.py`)

```django
{% can_read "campaigns" %}    → True/False
{% can_create "contacts" %}   → True/False
{% can_edit "social" %}       → True/False
{% can_delete "media" %}      → True/False
{% can_manage_workspace %}    → True if owner or admin
```

Checks `context.workspace_permissions` dict (set by views).

---

## Lifecycle

```
User creates workspace
  → Workspace object created
  → Owner membership created
  → Default permissions seeded
  → Session active_workspace_id set
  → Redirect to onboarding

Onboarding steps:
  1. Connect social accounts
  2. Invite team members
  3. Configure permissions
  4. Set up storage

User can dismiss onboarding checklist (WorkspaceOnboarding model)
```

---

## Edge Cases & Patterns

| Situation | Pattern |
|---|---|
| `get_or_create` with TenantManager | Wrap in `tenant_context(None)` to bypass auto-filter, otherwise the lookup won't find records with a different/null workspace |
| Cross-workspace admin queries | Use `_base_manager` or `tenant_context(None)` — but verify intent first |
| Personal mode (no active workspace) | `TenantManager` returns all records; `filter_by_context` falls back to user filter |
| Bypass for specific queries | `EmailTemplate._base_manager.get_or_create(...)` or `with tenant_context(None): ...` |
| Testing | Use `tenant_context(workspace)` to scope tests, or `override_settings` for manager behavior |

---

## File Map

```
core/
  tenant.py              — TenantManager, thread-local helpers, tenant_context
  middleware.py           — TenantMiddleware (plugs session → thread-local)

apps/workspaces/
  models.py              — Workspace, WorkspaceMembership, WorkspacePermission,
                           TeamInvitation, AuditLog, DEFAULT_PERMISSIONS,
                           seed_default_permissions()
  query_helpers.py       — filter_by_context() explicit scoping
  onboarding.py          — WorkspaceOnboarding model + helpers
  templatetags/
    workspace_tags.py    — can_read/can_create/can_edit/can_delete template tags
  views.py               — CRUD views, permissions view, onboarding, audit log
  urls.py                — All workspace routes

apps/*/models.py          — 13 models with objects = TenantManager()
```
