# Noir Development Agent Brief

## Context
You are working on the **Noir (Noir)** project — a Django-based SaaS platform for email campaigns, social media management, AI content generation, and workflow automation.

## Core Principles
1. **Full authority** over: Email Module, Landing Page, Dashboard, Auth Pages
2. **NO-FLY zones** (DO NOT modify unless explicitly asked): Social, Content, Creative, Trending, Audience, Account sections
3. **Workspace isolation**: Personal mode = personal data only; Workspace mode = that workspace's data; no cross-contamination
4. **Color palette**: Primary `#6D28D9` (violet), Secondary `#06B6D4` (cyan), White backgrounds for dashboard
5. **Before modifying**: Read relevant code thoroughly; understand logic, system design, and data flow before implementing
6. **Code quality**: Clean, scalable, no dead code; proper error handling; sustainable architecture

## Critical System Design Points

### Workspace/Personal Mode
- `require_workspace_permission` (`apps/workspaces/decorators.py`) allows personal mode — no redirect when no `active_workspace_id` in session
- `filter_by_context` (`apps/workspaces/query_helpers.py`): workspace mode filters by workspace; personal mode filters by `user + workspace__isnull`
- `TenantManager` (`core/tenant.py`): auto-filters querysets when tenant active; returns ALL when None

### Email Module Architecture
- **Campaigns**: 5-step wizard form; `body_html` is hidden input populated by JS on template select
- **CampaignForm.clean()** (`apps/campaigns/forms.py`): `is_draft_only = action in ('save_draft', 'send_test')` skips content validation
- **Auto-sync**: `clean()` auto-syncs `body_text` ↔ `body_html` when only one is provided
- **Send flow**: `send_now` action → `async_send_campaign` Celery task → `send_campaign_with_smtp` → redirect to campaign list
- **AI Auto-Reply**: inbox sync → `process_auto_replies_for_inbox` → classify_importance → confidence check → `EmailDraft` only for intents: `question`, `support`, `complaint`, `meeting_request`

### Celery/Redis
- Redis connection: `rediss://default:*@pet-kangaroo-98880.upstash.io:6379`
- SSL: `ssl_cert_reqs=ssl.CERT_NONE` (Upstash requirement)
- All task files: `from django.db import close_old_connections` (Django 6.0 API)

### Key Models
- `EmailInbox`, `Sender`: have `workspace` FK
- `EmailDraft`: has `workspace` FK (scoped via thread.inbox.workspace)
- `EmailMessage`/`EmailThread`: scoped via inbox relation
- `Sender`: `unique_together = ('user', 'from_email')` — multiple accounts per user

## Landing Page Sections
- **Watch Demo modal**: Light theme (white/purple/cyan) animated dashboard preview, NOT dark
- **Platform section**: Real content, social media icons (Twitter/X, Facebook, Instagram), alternating left/right layout
- **Features cards**: 2-column grid, hover effects, group animations
- **How It Works**: 3-step with connecting lines, gradient number badges, CTA button
- **Testimonials**: Marquee infinite scroll with white cards, gradient avatars

## Important URLs & Endpoints
- Campaign send: `campaigns:campaign_list` (POST action in form)
- Campaign analytics: `campaigns:campaign_analytics` campaign ID
- SMTP verify: `senders:verify_sender` (POST)
- DNS audit: `senders:audit_dns` (POST)
- Inbox dashboard: `inbox:dashboard` (HTMX swapped into `#inbox-messages-area`)
- Account switcher: `inbox:dashboard` with `inbox_id` param (hx-get, hx-target `#inbox-messages-area`)
- Auto-reply: `intelligence:bulk_auto_reply` (POST)

## CSP Configuration
`core/middleware.py` CSPMiddleware allows:
- `script-src`: `unpkg.com`, `cdn.jsdelivr.net`
- `connect-src`: `http://127.0.0.1:*`, `ws://127.0.0.1:*`, `api.openai.com`, `cdnjs.cloudflare.com`

## Running the Project
```bash
# Django server
./venv/bin/python manage.py runserver

# Celery worker (requires Redis)
./venv/bin/celery -A core worker -l info

# Celery Beat (for periodic tasks)
./venv/bin/celery -A core beat -l info

# Run migrations
./venv/bin/python manage.py migrate

# Check system
./venv/bin/python manage.py check
```

## Recent Changes (June 27, 2026)

### Landing Page Redesign
- **Demo modal**: Converted to light theme with white backgrounds, violet/cyan accents
- **Platform preview** (`_module_preview_content.html`): White cards, gradient avatars, real social media icons
- **Features section**: 2-column grid, hover animations, gradient checkmarks
- **How It Works**: Gradient number badges, connecting lines, CTA button
- **Testimonials**: Infinite marquee scroll, white cards, gradient avatar backgrounds

### Backend Fixes
- **Campaign send redirect**: Now redirects to `campaigns:campaign_list` after send (was `campaign_view`)
- **Django check**: Passes cleanly (only pre-existing redis cache warning)
- **Migrations**: Merge migrations created for `inbox` and `trending` apps

### Dependencies
- `django-celery-beat==2.9.0` installed (required by develop merge)

## Pre-existing Issues (Known)
- `django_ratelimit.W001`: cache backend django.core.cache.backends.redis.RedisCache not officially supported (harmless warning)
- Inbox credentials: Some accounts show "No password stored" or "Login failed" — requires manual reconnect

## File Structure
```
templates/
  landing/
    index.html          # Landing page (demo modal, platform, features, testimonials)
    includes/
      _module_preview_content.html  # Platform section previews
  base_dashboard.html   # Dashboard layout (navbar, sidebar, content area)
  base.html              # Landing page layout
apps/
  campaigns/             # Campaign CRUD, send logic, templates
  inbox/                  # Email inbox, AI agent, auto-reply
  intelligence/          # AI rules, actions, auto-reply service
  senders/               # SMTP sender management
  dashboard/             # Settings, profile, analytics
  accounts/              # Auth (login, register, password reset)
core/
  middleware.py           # CSP headers
  views.py                # Landing page context
  settings.py             # Django settings, Celery config
```