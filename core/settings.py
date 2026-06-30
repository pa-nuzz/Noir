import ssl
import os
import sys
import base64
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from decouple import config
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-test-key')
DEBUG = config('DEBUG', default=True, cast=bool)
def parse_csv_env(var, default=''):
    val = config(var, default=default)
    return [v.strip() for v in val.split(',') if v.strip()]

ALLOWED_HOSTS = parse_csv_env('ALLOWED_HOSTS', 'localhost,127.0.0.1')

# --- Explicit CSRF_TRUSTED_ORIGINS logic for ngrok/dev ---
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='').split(',')
CSRF_TRUSTED_ORIGINS = [x.strip() for x in CSRF_TRUSTED_ORIGINS if x.strip()]
if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        'https://*.ngrok-free.app',
        'https://*.ngrok.io',
        'http://127.0.0.1:51239',  # Browser preview proxy
        'http://localhost:51239',
    ]
    ALLOWED_HOSTS += ['*.ngrok-free.app', '*.ngrok.io', '127.0.0.1', 'localhost']
NGROK_DOMAIN = config('NGROK_DOMAIN', default='').strip()
PUBLIC_BASE_URL = config('PUBLIC_BASE_URL', default='http://127.0.0.1:8000').strip().rstrip('/')

def _normalize_host(value: str) -> str:
    if not value:
        return ''
    parsed = urlparse(value if '://' in value else f'https://{value}')
    return parsed.netloc or parsed.path

ngrok_host = _normalize_host(NGROK_DOMAIN)
if ngrok_host and ngrok_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(ngrok_host)

if PUBLIC_BASE_URL:
    public_host = urlparse(PUBLIC_BASE_URL).netloc
    if public_host and public_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(public_host)

# Add wildcard ngrok domains for dev convenience
for wildcard_host in ['.ngrok-free.dev', '.ngrok.io']:
    if wildcard_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(wildcard_host)

# CSRF trusted origins
if ngrok_host:
    ngrok_origin = f'https://{ngrok_host}'
    if ngrok_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(ngrok_origin)

if PUBLIC_BASE_URL and PUBLIC_BASE_URL.startswith('https://'):
    if PUBLIC_BASE_URL not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(PUBLIC_BASE_URL)

for default_origin in [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://*.ngrok-free.dev',
    'https://*.ngrok.io',
]:
    if default_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(default_origin)

# Remove duplicates and empty strings
ALLOWED_HOSTS = list({h for h in ALLOWED_HOSTS if h})
CSRF_TRUSTED_ORIGINS = list({o for o in CSRF_TRUSTED_ORIGINS if o})
STATIC_VERSION = config('STATIC_VERSION', default='2')

if not DEBUG and SECRET_KEY == 'django-insecure-test-key':
    raise ValueError('SECRET_KEY must be set from environment in production')

# Fix AutoField warnings
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Security
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_NAME = config('SESSION_COOKIE_NAME', default='dia_session_v2')
SESSION_EXPIRE_AT_BROWSER_CLOSE = config('SESSION_EXPIRE_AT_BROWSER_CLOSE', default=True, cast=bool)
SESSION_COOKIE_AGE = config('SESSION_COOKIE_AGE', default=60 * 60 * 8, cast=int)
SESSION_SAVE_EVERY_REQUEST = config('SESSION_SAVE_EVERY_REQUEST', default=False, cast=bool)
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

IS_RUNSERVER = 'runserver' in sys.argv

# Never force HTTPS for local development server execution.
# This prevents accidental browser HTTPS/HSTS loops on localhost.
if DEBUG or IS_RUNSERVER:
    FORCE_HTTPS = False
else:
    FORCE_HTTPS = config('FORCE_HTTPS', default=True, cast=bool)

SECURE_SSL_REDIRECT = False if (DEBUG or IS_RUNSERVER) else FORCE_HTTPS
SESSION_COOKIE_SECURE = False if (DEBUG or IS_RUNSERVER) else config('SESSION_COOKIE_SECURE', default=FORCE_HTTPS, cast=bool)
CSRF_COOKIE_SECURE = False if (DEBUG or IS_RUNSERVER) else config('CSRF_COOKIE_SECURE', default=FORCE_HTTPS, cast=bool)

# Trust reverse proxy protocol headers (ngrok / load balancers)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# In HTTPS-enforced environments only:
if FORCE_HTTPS:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',


    # Third Party
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'drf_spectacular_sidecar',
    'compressor',
    'django_ratelimit',
    'widget_tweaks',
    'django.contrib.humanize',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    'debug_toolbar',
    'django_celery_beat',

    # Local Apps
    'apps.accounts',
    'apps.senders',
    'apps.campaigns',
    'apps.intelligence',
    'apps.dashboard',
    'apps.contacts',
    'apps.automations',
    'apps.social',
    'apps.content',
    'apps.inbox',
    'apps.media',
    'apps.workspaces',
    'apps.social_accounts',
    'apps.content_studio',
    'apps.media_assets',
    'apps.billing',
    'apps.webhooks',
    'apps.api_keys',
    'apps.locks',
    'apps.mfa',
    'apps.audit',
    'apps.creative',
    'apps.trending',
]

MIDDLEWARE = [
    'core.middleware.DevHTTPMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',

    'core.middleware.TenantMiddleware',
    'apps.audit.middleware.AuditContextMiddleware',
    'apps.mfa.middleware.MfaEnforcementMiddleware',

    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.CSPMiddleware',

    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', BASE_DIR / 'apps' / 'contacts' / 'templates'],
          # root templates folder
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
                'core.context_processors.static_version',
                'core.context_processors.active_workspace',
                'apps.dashboard.context_processors.dashboard_notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / "db.sqlite3",
#     }
# }

CACHE_BACKEND = config('CACHE_BACKEND', default='locmem')

if CACHE_BACKEND == 'redis':
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': config('REDIS_CACHE_URL', default='redis://localhost:6379/0'),
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'IDA-local-cache',
        }
    }

USE_TZ = True
TIME_ZONE = 'Asia/Kathmandu'

# Ratelimit settings
RATELIMIT_ENABLE = True
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_FAIL_OPEN = False

# Database (PostgreSQL)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    }
}

# Celery Configuration
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True

# "connect to Redis over TLS but don't validate the SSL certificate"
# (CERT_NONE = don't verify certificate chain or hostname)
# Only apply SSL params when URL scheme is rediss:// (Upstash/production)
if CELERY_BROKER_URL.startswith('rediss://'):
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE}
if CELERY_RESULT_BACKEND.startswith('rediss://'):
    CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE}

# Queue separation — prevents slow tasks from blocking critical ones
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_QUEUE_HA_POLICY = 'all'
CELERY_WORKER_CONCURRENCY = 4

# Resilience — prevent crashes on Redis connection loss (Upstash SaaS drops idle connections)
CELERY_BROKER_HEARTBEAT = 30
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_POOL_LIMIT = 20
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = 50

CELERY_TASK_ROUTES = {
    # queue_critical — campaign sends, OAuth token refresh
    'apps.campaigns.tasks.async_send_campaign': {'queue': 'critical'},
    'apps.campaigns.tasks.run_scheduled_campaigns_task': {'queue': 'critical'},
    'apps.campaigns.tasks.evaluate_ab_test_winner': {'queue': 'critical'},
    'apps.social_accounts.tasks.refresh_oauth_tokens': {'queue': 'critical'},

    # queue_default — inbox sync, analytics aggregation
    'apps.inbox.tasks.sync_inbox_task': {'queue': 'default'},
    'apps.inbox.tasks.sync_all_inboxes_task': {'queue': 'default'},
    'apps.inbox.tasks.process_auto_replies_for_inbox': {'queue': 'default'},
    'apps.inbox.tasks.process_auto_reply_for_message': {'queue': 'default'},
    'apps.automations.tasks.process_workflows_task': {'queue': 'default'},
    'apps.automations.tasks.evaluate_workflow_triggers': {'queue': 'default'},
    'apps.social_accounts.tasks.publish_scheduled_posts': {'queue': 'default'},
    'apps.webhooks.tasks.deliver_webhook': {'queue': 'default'},
    'apps.webhooks.tasks.retry_failed_deliveries': {'queue': 'default'},
    'apps.locks.tasks.release_expired_locks': {'queue': 'default'},

    # queue_low — thumbnail generation, auto-tagging, AI content
    'apps.intelligence.tasks.async_generate_content': {'queue': 'low'},
    'apps.media_assets.tasks.generate_thumbnail': {'queue': 'low'},
    'apps.media_assets.tasks.cleanup_unused_media': {'queue': 'low'},
    'apps.content_studio.tasks.generate_ai_content_task': {'queue': 'low'},
}

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Tailwind/Compressor
STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
)

# Email Configuration
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    _auto_email_backend = 'django.core.mail.backends.smtp.EmailBackend'
elif DEBUG:
    _auto_email_backend = 'django.core.mail.backends.console.EmailBackend'
else:
    raise ValueError("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be set in production")

EMAIL_BACKEND = config('EMAIL_BACKEND', default=_auto_email_backend)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)
SERVER_EMAIL = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=20, cast=int)

# Public base URL used for email tracking links (opens/clicks). Example: https://your-domain.com
TRACKING_BASE_URL = config('TRACKING_BASE_URL', default=PUBLIC_BASE_URL).strip().rstrip('/')

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Logging
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
        'file': {
            'class': 'logging.FileHandler',
            'filename': str(LOG_DIR / 'django.log'),
            'level': 'WARNING',
        },
    },
    'root': {'handlers': ['console', 'file'], 'level': 'WARNING'},
    'loggers': {
        'django': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'apps': {'handlers': ['console', 'file'], 'level': 'DEBUG', 'propagate': False},
    },
}

# Custom user
AUTH_USER_MODEL = 'accounts.User'

# Auth URLs
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# Fernet encryption key (single source of truth)
FERNET_KEY = config('FERNET_KEY', default=os.environ.get('FERNET_KEY', ''))

# Generate deterministic development key if not set
if not FERNET_KEY:
    if DEBUG:
        # Deterministic development key so encrypted secrets survive restarts
        FERNET_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode('utf-8')).digest()).decode('utf-8')
    else:
        raise ValueError("FERNET_KEY must be set in production environment")

# Clean the key
FERNET_KEY = FERNET_KEY.strip()

# Machine Learning
ML_MODEL_PATH = Path(config('ML_MODEL_PATH', default=str(BASE_DIR / 'models_ml' / 'spam_model.pkl')))
ML_VECTORIZER_PATH = Path(config('ML_VECTORIZER_PATH', default=str(BASE_DIR / 'models_ml' / 'tfidf_vectorizer.pkl')))

# Email/intelligence LLM provider.
LLM_API_KEY = config('LLM_API_KEY', default=config('GEMINI_API_KEY', default=''))
LLM_BASE_URL = config('LLM_BASE_URL', default='https://api.openai.com/v1')
LLM_MODEL = config('LLM_MODEL', default='gpt-4o')

# Backward compatibility for older code paths.
GEMINI_API_KEY = config('GEMINI_API_KEY', default=LLM_API_KEY)

# DeepSeek AI
DEEPSEEK_API_KEY = config('DEEPSEEK_API_KEY', default='')

# NVIDIA NIM — image & video generation
NVIDIA_API_KEY = config('NVIDIA_API_KEY', default='')
NVIDIA_INTEGRATE_URL = 'https://integrate.api.nvidia.com/v1'

# Pollinations AI — image generation
POLLINATIONS_API_KEY = config('POLLINATIONS_API_KEY', default='')

# OpenRouter — text generation
OPENROUTER_API_KEY = config('OPENROUTER_API_KEY', default='')

# Google Gemini — text generation
GEMINI_API_KEY = config('GEMINI_API_KEY', default=LLM_API_KEY)

NVIDIA_MODELS = {
    # ── Image Generation ──────────────────────────────────────────────
    'ida-vision-lite': {
        'label': 'IDA Vision Lite',
        'modality': 'image',
        'provider': 'nvidia',
        'endpoint': '/genai/black-forest-labs/flux.2-klein-4b',
        'available': True,
        'params': {'steps': 4, 'cfg_scale': 1.0},
        'description': 'Lightning fast — 4B model, great quality',
    },
    'ida-vision-dev': {
        'label': 'IDA Vision Pro',
        'modality': 'image',
        'provider': 'nvidia',
        'endpoint': '/genai/black-forest-labs/flux.1-dev',
        'available': True,
        'params': {'steps': 30, 'cfg_scale': 7.0},
        'description': 'Premium quality — photorealistic, best detail',
    },
    'ida-pollinations': {
        'label': 'IDA Image',
        'modality': 'image',
        'provider': 'pollinations',
        'model_name': 'flux',
        'available': True,
        'params': {},
        'description': 'Fast and reliable — free Flux generation',
    },
    # ── Text / LLM Models ─────────────────────────────────────────────
    'ida-chat': {
        'label': 'IDA Chat',
        'modality': 'text',
        'provider': 'nvidia',
        'model_name': 'meta/llama-3.1-8b-instruct',
        'endpoint': '/chat/completions',
        'api_type': 'openai_compat',
        'available': True,
        'params': {'max_tokens': 2048, 'temperature': 0.6},
        'description': 'Fast and capable — great for general tasks',
    },
    'ida-router': {
        'label': 'IDA Router',
        'modality': 'text',
        'provider': 'openrouter',
        'model_name': 'google/gemini-2.5-flash',
        'available': True,
        'params': {'max_tokens': 4096, 'temperature': 0.7},
        'description': 'Gemini 2.5 Flash via OpenRouter',
    },
    'ida-gemini': {
        'label': 'IDA Gemini',
        'modality': 'text',
        'provider': 'gemini',
        'model_name': 'gemini-2.5-flash',
        'available': True,
        'params': {'max_tokens': 8192, 'temperature': 0.7},
        'description': 'Gemini 2.5 Flash — fast multimodal',
    },
}

IDA_MODELS = NVIDIA_MODELS

# Silencing django-ratelimit strict cache checks for development
SILENCED_SYSTEM_CHECKS = ['django_ratelimit.E003']

# Social Media OAuth — set in .env for each platform
SOCIAL_OAUTH_CLIENT_IDS = {
    'facebook': config('FACEBOOK_CLIENT_ID', default=''),
    'instagram': config('INSTAGRAM_CLIENT_ID', default=''),
    'twitter': config('TWITTER_CLIENT_ID', default=''),
    'linkedin': config('LINKEDIN_CLIENT_ID', default=''),
    'tiktok': config('TIKTOK_CLIENT_ID', default=''),
    'youtube': config('YOUTUBE_CLIENT_ID', default=''),
}
SOCIAL_OAUTH_CLIENT_SECRETS = {
    'facebook': config('FACEBOOK_CLIENT_SECRET', default=''),
    'instagram': config('INSTAGRAM_CLIENT_SECRET', default=''),
    'twitter': config('TWITTER_CLIENT_SECRET', default=''),
    'linkedin': config('LINKEDIN_CLIENT_SECRET', default=''),
    'tiktok': config('TIKTOK_CLIENT_SECRET', default=''),
    'youtube': config('YOUTUBE_CLIENT_SECRET', default=''),
}
FACEBOOK_CLIENT_ID = config('FACEBOOK_CLIENT_ID', default='')
INSTAGRAM_CLIENT_ID = config('INSTAGRAM_CLIENT_ID', default='')
TWITTER_CLIENT_ID = config('TWITTER_CLIENT_ID', default='')
LINKEDIN_CLIENT_ID = config('LINKEDIN_CLIENT_ID', default='')
TIKTOK_CLIENT_ID = config('TIKTOK_CLIENT_ID', default='')
YOUTUBE_CLIENT_ID = config('YOUTUBE_CLIENT_ID', default='')
FACEBOOK_CLIENT_SECRET = config('FACEBOOK_CLIENT_SECRET', default='')
INSTAGRAM_CLIENT_SECRET = config('INSTAGRAM_CLIENT_SECRET', default='')
TWITTER_CLIENT_SECRET = config('TWITTER_CLIENT_SECRET', default='')
LINKEDIN_CLIENT_SECRET = config('LINKEDIN_CLIENT_SECRET', default='')
TIKTOK_CLIENT_SECRET = config('TIKTOK_CLIENT_SECRET', default='')
YOUTUBE_CLIENT_SECRET = config('YOUTUBE_CLIENT_SECRET', default='')

# Per-platform OAuth redirect URI overrides (optional).
# When set, overrides PUBLIC_BASE_URL for that platform's callback.
# Useful when a platform (e.g. X/Twitter) requires HTTPS for callbacks
# while other platforms can use the default PUBLIC_BASE_URL.
FACEBOOK_REDIRECT_URI = config('FACEBOOK_REDIRECT_URI', default='')
INSTAGRAM_REDIRECT_URI = config('INSTAGRAM_REDIRECT_URI', default='')
TWITTER_REDIRECT_URI = config('TWITTER_REDIRECT_URI', default='')
LINKEDIN_REDIRECT_URI = config('LINKEDIN_REDIRECT_URI', default='')
TIKTOK_REDIRECT_URI = config('TIKTOK_REDIRECT_URI', default='')
YOUTUBE_REDIRECT_URI = config('YOUTUBE_REDIRECT_URI', default='')

STORAGES = {
    "default": {
        "BACKEND": "apps.media_assets.minio_storage.MinIODjangoStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media files are now stored in MinIO only - no local filesystem storage
# All uploaded files use MinIODjangoStorage which:
# - Stores files in MinIO bucket
# - Generates public URLs via MINIO_PUBLIC_BASE_URL or presigned URLs
# - Works in both DEBUG=True and DEBUG=False
# - No fallback to local filesystem under any circumstance

# --- Storage backends ---

# --- Google Sheets (workspace-level OAuth, same pattern as Drive) ---
# Credentials are per-workspace (encrypted in WorkspaceStorageConfig).
# The redirect URI must match what users register in their GCP project.
GOOGLE_SHEETS_REDIRECT_URI = config('GOOGLE_SHEETS_REDIRECT_URI', default=f"{PUBLIC_BASE_URL}/content-studio/sheets/oauth/callback/")
GOOGLE_SHEETS_SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]

S3_ENDPOINT_URL = config('S3_ENDPOINT_URL', default='')
S3_REGION = config('S3_REGION', default='us-east-1')
S3_BUCKET = config('S3_BUCKET', default='')
S3_ACCESS_KEY = config('S3_ACCESS_KEY', default='')
S3_SECRET_KEY = config('S3_SECRET_KEY', default='')

DIA_S3_ENDPOINT_URL = config('DIA_S3_ENDPOINT_URL', default='')
DIA_S3_REGION = config('DIA_S3_REGION', default='us-east-1')
DIA_S3_BUCKET = config('DIA_S3_BUCKET', default='')
DIA_S3_ACCESS_KEY = config('DIA_S3_ACCESS_KEY', default='')
DIA_S3_SECRET_KEY = config('DIA_S3_SECRET_KEY', default='')
DIA_S3_PATH_PREFIX = config('DIA_S3_PATH_PREFIX', default='')
DIA_S3_PUBLIC_BASE_URL = config('DIA_S3_PUBLIC_BASE_URL', default='')
DIA_S3_USE_PATH_STYLE = config('DIA_S3_USE_PATH_STYLE', default='True')

# MinIO Configuration
MINIO_ENDPOINT_URL = config('MINIO_ENDPOINT_URL', default='')
MINIO_REGION = config('MINIO_REGION', default='us-east-1')
MINIO_BUCKET = config('MINIO_BUCKET', default='')
MINIO_ACCESS_KEY = config('MINIO_ACCESS_KEY', default='')
MINIO_SECRET_KEY = config('MINIO_SECRET_KEY', default='')
MINIO_PATH_PREFIX = config('MINIO_PATH_PREFIX', default='')
MINIO_PUBLIC_BASE_URL = config('MINIO_PUBLIC_BASE_URL', default='')
MINIO_USE_PATH_STYLE = config('MINIO_USE_PATH_STYLE', default='True')

# DRF
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'core.api.authentication.APIKeyAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'core.api.permissions.TenantPermission',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Intelligent Digital Automation API',
    'DESCRIPTION': 'Enterprise email campaign & social media management platform.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_DIST': 'SIDECAR',
    'SWAGGER_UI_FAVICON_HREF': 'SIDECAR',
    'REDOC_DIST': 'SIDECAR',
    'COMPONENT_SPLIT_REQUEST': True,
    'TAGS': [
        {'name': 'Campaigns', 'description': 'Email campaigns'},
        {'name': 'Senders', 'description': 'Email sender profiles'},
        {'name': 'Inboxes', 'description': 'Email inbox connections'},
        {'name': 'Contacts', 'description': 'Contact lists and segments'},
        {'name': 'Social', 'description': 'Social media posts'},
        {'name': 'Content', 'description': 'Content studio items'},
        {'name': 'Media', 'description': 'Media assets and folders'},
        {'name': 'Workflows', 'description': 'Automation workflows'},
        {'name': 'Account', 'description': 'User account and workspace'},
    ],
}

# Stripe
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')

# Plan limits (emails/month, social accounts, AI credits, storage GB, team seats)
PLAN_LIMITS = {
    'free': {
        'emails_per_month': 500,
        'social_accounts': 1,
        'ai_credits': 100,
        'storage_gb': 1,
        'team_seats': 2,
    },
    'pro': {
        'emails_per_month': 10000,
        'social_accounts': 10,
        'ai_credits': 1000,
        'storage_gb': 50,
        'team_seats': 10,
    },
    'enterprise': {
        'emails_per_month': None,
        'social_accounts': None,
        'ai_credits': None,
        'storage_gb': None,
        'team_seats': None,
    },
}
