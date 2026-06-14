# MailFlow AI — Architecture

> **Platform**: AI-Powered Communication & Social Media Automation  
> **Framework**: Django 6.0.2 + DRF 3.15.2  
> **Python**: 3.12  
> **Database**: SQLite (dev) / PostgreSQL (prod via psycopg2-binary)  
> **Task Queue**: Celery 5.6.2 + Redis 7  
> **Frontend**: Django Templates + Tailwind CSS (CDN) + django-compressor

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Core Infrastructure](#2-core-infrastructure)
3. [Multi-Tenant Architecture](#3-multi-tenant-architecture)
4. [Django Apps](#4-django-apps)
5. [REST API Layer](#5-rest-api-layer)
6. [Template & Component Library](#6-template--component-library)
7. [Celery Task Layout](#7-celery-task-layout)
8. [Authentication & Security](#8-authentication--security)
9. [Billing & Subscriptions](#9-billing--subscriptions)
10. [Key Architectural Patterns](#10-key-architectural-patterns)
11. [Testing & Linting](#11-testing--linting)

---

## 1. Project Structure

```
MailFlow AI/
├── core/                     # Django project config & shared infra
│   ├── settings.py           # All settings (auth, DB, Celery, Stripe, etc.)
│   ├── urls.py               # Root URL conf (18 app namespaces + API + Swagger)
│   ├── views.py              # Landing page (537 lines)
│   ├── middleware.py          # TenantMiddleware, DevHTTPMiddleware, CSPMiddleware
│   ├── tenant.py             # TenantManager, thread-local tenant context
│   ├── celery.py             # Celery app + beat schedule
│   ├── context_processors.py # Template context (static version, active workspace)
│   ├── wsgi.py / asgi.py
│   └── api/                  # DRF REST API layer
│       ├── views.py          # 16 ViewSets
│       ├── serializers.py    # 17 serializers
│       ├── permissions.py    # TenantPermission, TenantModelPermission
│       ├── authentication.py # APIKeyAuthentication
│       ├── router.py         # DefaultRouter with 16 routes
│       └── urls.py           # JWT auth + router includes
│
├── apps/                     # 21 Django apps
│   ├── accounts/             # Auth, registration, password reset
│   ├── api_keys/             # Workspace API key management
│   ├── audit/                # Audit trail signals + middleware
│   ├── automations/          # Visual workflow builder
│   ├── billing/              # Stripe subscriptions & plans
│   ├── campaigns/            # Email campaign engine
│   ├── contacts/             # Contact/segment management
│   ├── content_studio/       # Unified content generation hub
│   ├── dashboard/            # Main command center & KPIs
│   ├── inbox/                # Unified email inbox (Gmail/Outlook)
│   ├── intelligence/         # AI/ML services (spam, copilot, auto-reply)
│   ├── locks/                # Edit locking (GenericForeignKey)
│   ├── media_assets/         # Media library (S3/local/Google Drive)
│   ├── mfa/                  # Multi-factor authentication
│   ├── senders/              # SMTP sender management
│   ├── social_accounts/      # Social media publishing & analytics
│   ├── webhooks/             # Outbound webhook delivery
│   ├── workspaces/           # Multi-tenant workspace engine
│   │
│   │   # Legacy apps (superseded by newer versions above):
│   ├── content/              # Content generation (legacy)
│   ├── media/                # Media library (legacy)
│   └── social/               # Social media (legacy)
│
├── templates/
│   ├── base_dashboard.html   # Dashboard shell (sidebar, nav, mobile tabs)
│   ├── components/           # Reusable UI components
│   │   ├── button.html, badge.html, modal.html, form_field.html
│   │   ├── skeleton.html, empty_state.html
│   │   └── ...
│   ├── onboarding/checklist.html
│   └── landing/              # Marketing landing page
│
├── static/                   # Source static files
│   ├── css/style.css         # Design system (purple/cyan palette)
│   ├── css/app.css           # Deprecated
│   └── images/               # Logo, social platform icons
│
├── staticfiles/              # Collected static (Whitenoise)
├── conftest.py               # Shared pytest fixtures
├── pyproject.toml            # Ruff, pytest, coverage config
├── requirements.txt          # 79 pinned dependencies
├── Dockerfile                # Python 3.12-slim, gunicorn
├── docker-compose.yml        # Postgres 16, Redis 7, app, Celery workers
└── docs/
    ├── TENANT_ARCHITECTURE.md
    └── DNS_AUDIT_GUIDE.md
```

---

## 2. Core Infrastructure

### 2.1 Settings (`core/settings.py` — 538 lines)

Key configuration groups:
- **Auth**: AUTH_USER_MODEL = `accounts.User`, email-as-username, session + JWT
- **Middleware**: `TenantMiddleware`, `AuditContextMiddleware`, `MfaEnforcementMiddleware`, `CSPMiddleware`
- **Installed Apps**: All 21 apps + `rest_framework`, `drf_spectacular`, `celery`, `django_otp`, `storages`
- **Celery**: Broker=Redis, 4 queues (critical/default/low), beat schedule
- **Stripe**: Keys, webhook secret, PLAN_LIMITS dict
- **Encryption**: `FERNET_KEY` for Fernet symmetric encryption
- **Storage**: AWS S3 + Google Drive + local backends

### 2.2 URL Routing (`core/urls.py`)

```
/                           → Landing page
/accounts/                  → Auth (login, register, password reset)
/dashboard/                 → Main dashboard & settings
/campaign/                  → Campaign CRUD, send, analytics, templates
/contacts/                  → Contact lists, segments, GDPR
/senders/                   → SMTP verification
/inbox/                     → Email inbox, drafts
/social-accounts/           → Social media hub, posts, analytics
/content-studio/            → Content generation hub
/media-assets/              → Media library
/automations/               → Workflow builder
/intelligence/              → Spam analysis, AI copilot
/workspaces/                → Workspace CRUD, members, permissions, audit, onboarding
/billing/                   → Subscription plans, Stripe checkout
/webhooks/                  → Outbound webhook endpoints
/api-keys/                  → (registered but not exposed via URL)
/mfa/                       → MFA settings, enable, disable
/api/v1/                    → DRF REST API (16 endpoints)
/api/schema/                → OpenAPI schema (Swagger UI, Redoc)
/webhooks/                  → Stripe webhook handler
```

### 2.3 Context Processors (`core/context_processors.py`)

Injects into all templates:
- `STATIC_VERSION` — cache-busting timestamp
- `active_workspace` / `active_membership` — current workspace + membership
- `workspace_permissions` — user's permission dict for the active workspace
- `workspace_list` — user's available workspaces

---

## 3. Multi-Tenant Architecture

### 3.1 Core Mechanism

```
Request → TenantMiddleware → session[active_workspace_id]
  → validates membership → set_current_tenant(workspace) [thread-local]
  → request.tenant = workspace

Model.objects.all() → TenantManager.get_queryset()
  → get_current_tenant() not None?
    → qs.filter(workspace=tenant)
  → returns all (personal mode)
```

### 3.2 Components

| Component | File | Role |
|---|---|---|
| `TenantManager` | `core/tenant.py:35` | Custom `models.Manager` — overrides `get_queryset()` to auto-filter by workspace |
| `get/set/clear_current_tenant` | `core/tenant.py:9-19` | Thread-local (`threading.local()`) tenant storage |
| `tenant_context()` | `core/tenant.py:22` | Context manager to temporarily override tenant (used for `get_or_create` bypass) |
| `TenantMiddleware` | `core/middleware.py:10` | Reads `session[active_workspace_id]`, validates membership, sets thread-local |
| `filter_by_context()` | `apps/workspaces/query_helpers.py:5` | Explicit scoping safety net (also handles personal mode) |

### 3.3 Tenant-Scoped Models (13 models with `objects = TenantManager()`)

| App | Models |
|---|---|
| `campaigns` | `Campaign`, `EmailTemplate` |
| `senders` | `Sender` |
| `inbox` | `EmailInbox` |
| `contacts` | `ContactList`, `ContactTag`, `ContactCustomField`, `ContactSegment` |
| `social_accounts` | `SocialPost` |
| `content_studio` | `ContentItem` |
| `media_assets` | `MediaFolder`, `MediaAsset` |
| `automations` | `Workflow` |

### 3.4 Critical Pattern: Bypassing TenantManager

`get_or_create` with `TenantManager` fails because the auto-filter hides existing records from other workspaces. Pattern:

```python
from core.tenant import tenant_context

with tenant_context(None):
    obj, created = MyModel.objects.get_or_create(
        user=request.user, name=name,
        defaults={...}
    )
```

### 3.5 Access Control

**Roles** (`WorkspaceMembership`): Owner → Admin → Member

**Permissions** (`WorkspacePermission`): Per-module CRUD toggles per role. 13 modules: `campaigns`, `contacts`, `social`, `media`, `workflows`, `inbox`, `content_studio`, `workspace`, `billing`, `audit_log`, `storage`, `members`, `export`.

**Template tags** (`workspace_tags.py`):
```django
{% can_read "campaigns" %}    {% can_create "contacts" %}
{% can_edit "social" %}       {% can_delete "media" %}
{% can_manage_workspace %}
```

**API permissions** (`core/api/permissions.py`):
- `TenantPermission` — global check: user must be workspace member
- `TenantModelPermission` — per-object check based on workspace membership
- `IsWorkspaceAdminOrReadOnly` — admins can write, others read-only

---

## 4. Django Apps

### 4.1 `accounts` — Authentication & User Management

**Models**: `User` (email-as-username, company, avatar, email_verified), `PasswordResetCode` (6-digit code)
**Views**: login, register, logout, verify email, password reset (code-based + link-based)
**Templates**: 9 auth templates
**URLs**: `login/`, `register/`, `logout/`, `verify-email/`, `password-reset/`

### 4.2 `api_keys` — API Key Management

**Models**: `WorkspaceAPIKey` (workspace, prefix, SHA-256 hash, scopes, expiry, last-used)
**Notes**: Admin-only, no views. Used by `APIKeyAuthentication`.

### 4.3 `audit` — Audit Trail

**Files**: `signals.py` (post_save/post_delete handlers for 13 sensitive models), `middleware.py` (captures user+IP into thread-local)
**Integration**: Connected via `AuditContextMiddleware` and signal registration in `AppConfig.ready()`

### 4.4 `automations` — Visual Workflow Builder

**Models**: `Workflow` (TenantManager), `WorkflowNode` (6 types), `WorkflowEdge`, `WorkflowEnrollment`
**Engine** (`engine.py`): Handles all node types — triggers, delays, actions, wait conditions, branches, goals
**Tasks** (`tasks.py`): `process_workflows_task` (Celery Beat, 5 min)
**Views**: list, create, edit, delete, toggle, analytics, API save nodes
**Templates**: `workflow_list.html`, `workflow_form.html`, `workflow_analytics.html`

### 4.5 `billing` — Subscription & Billing

**Models**: `Plan` (free/pro/enterprise with Stripe price IDs), `Subscription` (workspace, plan, interval, status), `StoragePlan`, `WorkspaceBilling`
**Views**: `billing_dashboard` (quota progress, plan cards), `create_subscription_checkout`, `billing_portal`, `stripe_webhook`
**Template**: `dashboard.html`
**Stripe Integration** (`stripe_utils.py`): customer creation, checkout sessions, portal sessions, webhook handlers (checkout completed, subscription deleted, invoice paid/failed)
**Management Command**: `seed_plans` (creates Free/Pro/Enterprise)

### 4.6 `campaigns` — Email Campaign Engine

**Models**: `Campaign` (TenantManager), `CampaignAttachment`, `CampaignVariant` (A/B), `EmailEngagement`, `EmailClickEvent`, `EmailUnsubscribe`, `EmailTemplate` (TenantManager), `TemplateImage`
**Views** (split into `views/` package):
- `campaign.py` — list, create, edit, delete, duplicate, preview, set A/B winner
- `send.py` — send, retry failed
- `analytics.py` — campaign analytics, CSV export
- `tracking.py` — open/click tracking pixels, unsubscribe
- `templates.py` — template CRUD, use, duplicate
**Tasks** (`tasks.py`): `run_scheduled_campaigns_task` (Beat, 1 min), `async_send_campaign`, `evaluate_ab_test_winner`
**Services** (`services/`): `delivery.py` (SMTP send + HTML render), `scheduler.py`, `content.py`
**Default Templates**: 8 built-in templates (Welcome, Newsletter, Promo, Event, etc.)

### 4.7 `contacts` — Contact Management

**Models**: `ContactList` (TenantManager), `ContactTag` (TenantManager), `ContactCustomField` (TenantManager), `ContactSegment` (TenantManager), `Contact` (email, tags M2M, GDPR fields), `ContactCustomFieldValue`
**Views**: home, tags, import CSV, create/delete/list, custom fields CRUD, segments, export, GDPR tools (export, anonymize)
**Templates**: 15 templates
**URLs**: 23 routes

### 4.8 `content_studio` — Unified Content Studio

**Models**: `ContentItem` (TenantManager), `ContentVersion`, `ContentApproval`
**Views**: dashboard, content hub, calendar, generate, detail, edit, refine, approve, delete, history
**Templates**: 9 templates
**Tasks**: `auto_generate_variations`
**Services**: `services.py` (generate, refine, approve)

### 4.9 `dashboard` — Main Command Center

**Views** (largest view file, ~1500 lines): `dashboard_view` (multi-module KPIs, charts, activity feed), `platform_analytics`, `settings_view` (SMTP management), `profile_view`, `social_content_hub`, `clear_notifications_view`
**Templates**: `home.html`, `profile.html`, `settings.html`, `platform_analytics.html`, `social_content_hub.html`

### 4.10 `inbox` — Unified Email Inbox

**Models**: `EmailInbox` (TenantManager), `EmailThread`, `EmailMessage`, `EmailDraft`
**Views**: inbox dashboard, connect/disconnect/sync, message detail, draft review/approve/send, generate draft (AI), summarize, soft-delete/restore
**Templates**: 6 templates
**Services** (`services/`): `sync.py` (IMAP inbox sync)
**Tasks**: `sync_inbox_task`, `sync_all_inboxes_task` (Beat, 10 min), `process_auto_replies_for_inbox`, `process_auto_reply_for_message`

### 4.11 `intelligence` — AI/ML Services

**Views**: `analyze_spam` (POST API), `generate_copilot_content` (POST API — Gemini/OpenRouter)
**Services**: `copilot.py` (AI copy generation), `spam_analysis.py`, `inbox_ai.py` (summarize, draft reply), `auto_reply.py`
**Note**: All AI APIs. No database models.

### 4.12 `locks` — Edit Locking

**Models**: `EditLock` (GenericForeignKey, locked_by, expires_at)
**Utils**: `acquire_lock()`, `release_lock()`, `get_lock()`
**Tasks**: `release_expired_locks` (Beat, 5 min)

### 4.13 `media_assets` — Media Library

**Models**: `MediaFolder` (TenantManager), `MediaTag`, `MediaAsset` (TenantManager, supports S3/local/Google Drive)
**Views**: library, upload, detail, delete, folders, folder detail, API assets
**Templates**: 5 templates + `_folder_tree.html`
**Tasks**: `process_asset`, `bulk_tag_assets`

### 4.14 `mfa` — Multi-Factor Authentication

**Views**: settings, enable (QR code provisioning), disable, required
**Templates**: 3 templates
**Integration**: `django-otp` + `otp_totp`, gated to owner/admin on enterprise plan via `MfaEnforcementMiddleware`

### 4.15 `senders` — SMTP Sender Management

**Models**: `Sender` (TenantManager, encrypted SMTP password via Fernet)
**Views**: `verify_sender` (SMTP connection test), `audit_sender_dns_view` (SPF/DKIM/DMARC check)
**Services** (`services/`): `dns_audit.py`

### 4.16 `social_accounts` — Social Media Publishing

**Models**: `SocialAccount`, `SocialAnalytics`, `SocialPost` (TenantManager)
**Views**: social hub, connect platform (OAuth2), post CRUD, publish, analytics, calendar
**Platform Adapters** (`platforms/`): Facebook, Instagram, LinkedIn, Twitter, TikTok, YouTube
**Tasks**: `publish_scheduled_posts` (Beat, 1 min), `sync_post_analytics`
**Services**: `services.py`

### 4.17 `webhooks` — Outbound Webhooks

**Models**: `WebhookEndpoint`, `WebhookDelivery` (with retry logic, exponential backoff)
**Views**: list, create, toggle, test
**Templates**: `list.html`, `form.html`
**Tasks**: `deliver_webhook` (Celery with retry), `retry_failed_deliveries`

### 4.18 `workspaces` — Multi-Tenant Engine

**Models**: `Workspace`, `WorkspaceMembership`, `TeamInvitation`, `AuditLog`, `WorkspaceSocialAccount`, `WorkspacePermission`, `WorkspaceStorageConfig`, `WorkspaceQuota`
**Views** (largest views file): workspace CRUD, members, invitations, permissions matrix, audit log, onboarding, storage settings
**Templates**: 12 templates
**URLs**: 46 routes (workspaces, members, invitations, permissions, storage)
**Helpers**: `query_helpers.py` (filter_by_context), `decorators.py` (require_workspace_permission), `onboarding.py`

---

## 5. REST API Layer

### 5.1 Endpoints (`/api/v1/`)

| Endpoint | ViewSet | Auth |
|---|---|---|
| `auth/token/` | — (JWT obtain) | Public |
| `auth/token/refresh/` | — | Public |
| `auth/token/verify/` | — | Public |
| `me/` | `SelfUserViewSet` | Session/JWT/APIKey |
| `campaigns/` | `CampaignViewSet` | Session/JWT/APIKey |
| `email-templates/` | `EmailTemplateViewSet` | Session/JWT/APIKey |
| `senders/` | `SenderViewSet` | Session/JWT/APIKey |
| `inboxes/` | `EmailInboxViewSet` (+sync action) | Session/JWT/APIKey |
| `contact-lists/` | `ContactListViewSet` | Session/JWT/APIKey |
| `contacts/` | `ContactViewSet` | Session/JWT/APIKey |
| `contact-tags/` | `ContactTagViewSet` | Session/JWT/APIKey |
| `contact-fields/` | `ContactCustomFieldViewSet` | Session/JWT/APIKey |
| `contact-segments/` | `ContactSegmentViewSet` | Session/JWT/APIKey |
| `social-posts/` | `SocialPostViewSet` | Session/JWT/APIKey |
| `content-items/` | `ContentItemViewSet` (+approve/publish) | Session/JWT/APIKey |
| `media-folders/` | `MediaFolderViewSet` | Session/JWT/APIKey |
| `media-assets/` | `MediaAssetViewSet` | Session/JWT/APIKey |
| `workflows/` | `WorkflowViewSet` | Session/JWT/APIKey |
| `members/` | `WorkspaceMembershipViewSet` | Session/JWT/APIKey |
| `quota/` | `WorkspaceQuotaViewSet` | Session/JWT/APIKey |

### 5.2 Authentication

Three modes via DRF's `DEFAULT_AUTHENTICATION_CLASSES`:

| Mode | Mechanism | Use Case |
|---|---|---|
| Session | Django session cookie | Browser (Django templates) |
| JWT | `Authorization: Bearer <token>` | First-party SPA/mobile |
| API Key | `Authorization: ApiKey <key>` | Third-party / machine-to-machine |

### 5.3 Schema & Docs

- OpenAPI schema: `/api/schema/`
- Swagger UI: `/api/schema/swagger-ui/`
- ReDoc: `/api/schema/redoc/`

---

## 6. Template & Component Library

### 6.1 Base Templates

| Template | Purpose |
|---|---|
| `base.html` | Root HTML shell (head, meta, analytics) |
| `base_dashboard.html` | Dashboard shell: sidebar nav, top bar, mobile bottom tabs, AI copilot, onboarding checklist include |

### 6.2 Reusable Components (`templates/components/`)

| Component | Usage |
|---|---|
| `button.html` | Styled `<button>` or `<a>` with variants (primary, secondary, danger, ghost) |
| `badge.html` | Status/label badge with color variants |
| `modal.html` | Full-screen overlay modal with backdrop blur, open/close JS |
| `form_field.html` | Label + input + error rendering with consistent styling |
| `skeleton.html` | Loading placeholder (card, table_row, text_block, chip variants) |
| `empty_state.html` | Empty state with illustration, icon, title, description, CTA |

### 6.3 Onboarding (`templates/onboarding/checklist.html`)

4-step onboarding checklist (connect sender, import contacts, create campaign, connect social). Included via `base_dashboard.html`, dismissed via AJAX POST. Progress tracked via `WorkspaceOnboarding` model.

### 6.4 Design System (`static/css/style.css`)

Purple/cyan color palette via CSS custom properties:
- Primary: `#6D28D9` (purple)
- Cyan accent: `#06B6D4`
- Fonts: Raleway (headings) + Inter (body)

---

## 7. Celery Task Layout

### 7.1 Queues

| Queue | Priority | Workers |
|---|---|---|
| `critical` | Highest | Campaign sends |
| `default` | Normal | Social publishing, automation, inbox sync |
| `low` | Lowest | Analytics, cleanup |

### 7.2 Beat Schedule

| Task | Interval | Queue |
|---|---|---|
| `run_scheduled_campaigns_task` | Every 1 min | `critical` |
| `publish_scheduled_posts` | Every 1 min | `default` |
| `process_workflows_task` | Every 5 min | `default` |
| `release_expired_locks` | Every 5 min | `default` |
| `sync_all_inboxes_task` | Every 10 min | `default` |

---

## 8. Authentication & Security

### 8.1 Authentication Flow

1. **Registration**: Email + password → verification email (6-digit code or link)
2. **Login**: Email + password → session created
3. **Workspace Activation**: User selects workspace → `session[active_workspace_id]` set
4. **JWT**: `/api/v1/auth/token/` returns access + refresh tokens
5. **API Key**: Admin-generated, stored as SHA-256 hash, sent as `Authorization: ApiKey <key>`

### 8.2 Encryption

Fernet symmetric encryption (AES-256-CBC + HMAC-SHA256) for:
- Sender SMTP passwords
- EmailInbox OAuth tokens
- WorkspaceStorageConfig credentials

Key rotation supported via `PREVIOUS_FERNET_KEYS` env variable.

### 8.3 MFA

- TOTP-based via `django-otp` + `otp_totp`
- QR code provisioning (Google Authenticator compatible)
- Enforced for owner/admin roles on Enterprise plans

### 8.4 Rate Limiting

- `django-ratelimit` for auth endpoints
- Per-platform rate limiting in social_accounts adapters

---

## 9. Billing & Subscriptions

### 9.1 Plans

| Plan | Price (monthly) | Price (yearly) |
|---|---|---|
| Free | $0 | $0 |
| Pro | $29 | $290 |
| Enterprise | $99 | $990 |

### 9.2 Stripe Integration

- Customers: `stripe_customer_id` on Workspace
- Checkout: `create_checkout_session()` → redirects to Stripe
- Portal: `create_portal_session()` → redirects to Stripe customer portal
- Webhooks: handled in `billing/views.py:stripe_webhook`:
  - `checkout.session.completed` → create Subscription record
  - `customer.subscription.deleted` → downgrade to free
  - `invoice.paid` → update Subscription status
  - `invoice.payment_failed` → flag for attention

### 9.3 Quotas

`WorkspaceQuota` model tracks: `emails_sent_this_month`, `ai_credits_used`, `storage_bytes_used`. Limits defined in `settings.PLAN_LIMITS`. Reset monthly.

---

## 10. Key Architectural Patterns

### 10.1 Dual-App Migration

Some domains have a legacy app and a newer workspace-aware version:

| Domain | Legacy | Current |
|---|---|---|
| Content | `content` | `content_studio` |
| Media | `media` | `media_assets` |
| Social | `social` | `social_accounts` |

Current apps use `TenantManager` and follow the workspace isolation pattern.

### 10.2 Audit Trail

Signal-based (not view-based):
- `audit/signals.py` connects `post_save`/`post_delete` for 13 sensitive models
- `AuditContextMiddleware` captures user + IP in thread-local for signal use
- Written to `AuditLog` model in `workspaces`

### 10.3 Edit Locking

`EditLock` uses Django's `GenericForeignKey` — locks any model instance for collaborative editing. Expired locks auto-released by Celery Beat task every 5 minutes.

### 10.4 Email Tracking

- **Open tracking**: 1x1 transparent GIF pixel with unique tracking token
- **Click tracking**: All links wrapped via redirect endpoint (`/campaign/track/click/<token>/`)
- **Unsubscribe**: Unique per-campaign token, one-click unsubscribe

---

## 11. Testing & Linting

### 11.1 Test Configuration

```ini
DJANGO_SETTINGS_MODULE = core.settings
python_files = tests.py, test_*.py, *_tests.py
testpaths = apps, core
```

### 11.2 Fixtures (`conftest.py`)

Shared pytest fixtures: `user`, `user2`, `workspace`, `workspace2`, `api_client`, `admin_api_client`, `fernet_key` (deterministic test key), `mock_smtp` (monkeypatches SMTP_SSL/SMTP).

### 11.3 Test Coverage

| Test File | Tests | Notes |
|---|---|---|
| `campaigns/tests/test_encryption.py` | 5 | Fernet round-trip, wrong key, dev fallback |
| `campaigns/tests/test_workspace_isolation.py` | 6 | TenantManager filters, cross-workspace isolation |
| `campaigns/tests/test_delivery.py` | 3 | Pre-existing failures |
| `campaigns/tests/test_permissions.py` | 6 | Role-based permission matrix |
| `campaigns/tests/test_social_adapters.py` | 5 | Facebook publish/analytics mocked with `responses` |
| `inbox/tests.py` | — | Uses deprecated `ENCRYPTION_KEY` (needs update to FERNET_KEY) |

### 11.4 Linting (Ruff)

- Line length: 120
- Target: Python 3.12
- Rules: E, F, W, I, N, UP, S, B, C4, SIM
- Coverage: source = `apps`, `core`

### 11.5 CI (`./github/workflows/ci.yml`)

- Run ruff lint
- Run pytest with coverage
- Docker build on main branch
