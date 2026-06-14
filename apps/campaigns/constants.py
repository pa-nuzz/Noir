"""Email module constants for maintainability and consistency."""

# ──────────────────────────────────────────────
#  Email Rendering Constants
# ──────────────────────────────────────────────

# Email dimensions (pixels)
EMAIL_WIDTH = 600
EMAIL_MAX_WIDTH = 600
HEADER_LOGO_MAX_HEIGHT = 60
FOOTER_LOGO_MAX_HEIGHT = 40

# Email colors (hex)
EMAIL_BACKGROUND_COLOR = '#f4f4f5'
EMAIL_CONTAINER_BACKGROUND = '#ffffff'
EMAIL_TEXT_COLOR = '#1e293b'
EMAIL_TEXT_MUTED = '#6b7280'
EMAIL_TEXT_LIGHT = '#9ca3af'
EMAIL_BORDER_COLOR = '#e2e8f0'

# Email spacing (pixels)
EMAIL_PADDING_OUTER = 16
EMAIL_PADDING_INNER = 24
EMAIL_PADDING_HEADER = 20
EMAIL_PADDING_FOOTER = 20

# Email typography
EMAIL_FONT_FAMILY = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
EMAIL_FONT_SIZE_BODY = '15px'
EMAIL_FONT_SIZE_HEADER = '18px'
EMAIL_FONT_SIZE_FOOTER = '12px'
EMAIL_LINE_HEIGHT = '1.6'

# ──────────────────────────────────────────────
#  Email Deliverability Constants
# ──────────────────────────────────────────────

# Email headers for inbox placement
EMAIL_PRIORITY = '1 (Highest)'
EMAIL_IMPORTANCE = 'High'
EMAIL_MAILER = 'Digital Intelligence Automation'

# Rate limiting
DEFAULT_SEND_DELAY_SECONDS = 3.0
DEFAULT_DAILY_LIMIT = 500

# Spam prevention
MAX_SUBJECT_LENGTH = 998
MAX_RECIPIENTS_PER_SEND = 100

# ──────────────────────────────────────────────
#  Tracking Constants
# ──────────────────────────────────────────────

TRACKING_PIXEL_WIDTH = 1
TRACKING_PIXEL_HEIGHT = 1
TRACKING_TOKEN_LENGTH = 32  # uuid4().hex produces 32 characters

# ──────────────────────────────────────────────
#  Attachment Constants
# ──────────────────────────────────────────────

MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_ATTACHMENT_TYPES = {
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/gif',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/plain',
    'text/csv',
}

# ──────────────────────────────────────────────
#  A/B Testing Constants
# ──────────────────────────────────────────────

AB_TEST_DEFAULT_DURATION_HOURS = 2
AB_TEST_MINIMUM_PERCENTAGE = 10