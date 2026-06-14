"""Premium email templates shipped with the app."""

WELCOME_TEMPLATE = {
    'name': 'Luxury Welcome',
    'subject': 'Welcome to {{ company_name }}',
    'body_html': '''<div style="background-color:#0a0a0f;padding:40px 20px;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;">
<tr><td style="text-align:center;padding:0 0 30px;">
<div style="width:48px;height:48px;margin:0 auto 16px;background:linear-gradient(135deg,#d4af37,#f7e8a0);border-radius:12px;display:flex;align-items:center;justify-content:center;">
<span style="color:#0a0a0f;font-size:24px;font-weight:bold;">W</span>
</div>
<h1 style="color:#f7e8a0;font-size:26px;font-weight:400;letter-spacing:0.08em;margin:0;text-transform:uppercase;">Welcome</h1>
<p style="color:#8b8b96;font-size:13px;letter-spacing:0.15em;margin:8px 0 0;text-transform:uppercase;">{{ company_name }} <span style="color:#d4af37;">·</span> Member</p>
</td></tr>
<tr><td style="background:#12121a;border-radius:16px;padding:40px;border:1px solid rgba(212,175,55,0.15);">
<p style="color:#e8e8ed;font-size:16px;line-height:1.8;margin:0 0 20px;">Dear {{ first_name }},</p>
<p style="color:#a0a0ab;font-size:15px;line-height:1.8;margin:0 0 20px;">It is our distinct pleasure to welcome you to <strong style="color:#e8e8ed;">{{ company_name }}</strong> — a community built on excellence, crafted for those who seek more.</p>
<div style="border-left:3px solid #d4af37;padding:20px 24px;margin:24px 0;background:rgba(212,175,55,0.04);border-radius:0 12px 12px 0;">
<p style="color:#f7e8a0;font-size:13px;letter-spacing:0.12em;margin:0 0 12px;text-transform:uppercase;font-family:-apple-system,sans-serif;">Your Journey Begins</p>
<table cellpadding="0" cellspacing="0" style="color:#a0a0ab;font-size:14px;line-height:2;">
<tr><td style="padding:2px 12px 2px 0;color:#d4af37;font-size:18px;vertical-align:middle;">—</td><td style="vertical-align:middle;">Complete your profile</td></tr>
<tr><td style="padding:2px 12px 2px 0;color:#d4af37;font-size:18px;vertical-align:middle;">—</td><td style="vertical-align:middle;">Explore exclusive features</td></tr>
<tr><td style="padding:2px 12px 2px 0;color:#d4af37;font-size:18px;vertical-align:middle;">—</td><td style="vertical-align:middle;">Connect with the community</td></tr>
</table>
</div>
<p style="color:#a0a0ab;font-size:15px;line-height:1.8;margin:0 0 8px;">Should you require any assistance, simply reply to this note. We are at your service.</p>
<p style="color:#e8e8ed;font-size:15px;line-height:1.8;margin:0;">With warm regards,<br><span style="color:#f7e8a0;">The {{ company_name }} Team</span></p>
</td></tr>
<tr><td style="text-align:center;padding:30px 0 0;">
<p style="color:#5a5a65;font-size:11px;letter-spacing:0.1em;margin:0;">{{ company_name }} · Excellence in every detail</p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

It is our distinct pleasure to welcome you to {{ company_name }} — a community built on excellence, crafted for those who seek more.

Your Journey Begins:
- Complete your profile
- Explore exclusive features
- Connect with the community

Should you require any assistance, simply reply to this note.

With warm regards,
The {{ company_name }} Team''',
}

NEWSLETTER_TEMPLATE = {
    'name': 'Premium Monthly',
    'subject': '{{ company_name }} · {{ month }}',
    'body_html': '''<div style="background-color:#ffffff;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;">
<tr><td style="background:linear-gradient(135deg,#1e1b4b,#312e81);padding:40px 40px 32px;text-align:center;">
<p style="color:#a5b4fc;font-size:11px;letter-spacing:0.2em;text-transform:uppercase;margin:0 0 8px;">Monthly Edition</p>
<h1 style="color:#ffffff;font-size:28px;font-weight:700;margin:0;letter-spacing:-0.02em;">{{ month }}</h1>
<div style="width:40px;height:2px;background:#6366f1;margin:16px auto 0;"></div>
</td></tr>
<tr><td style="padding:36px 40px 20px;">
<p style="color:#1e293b;font-size:16px;line-height:1.7;margin:0 0 24px;">Dear {{ first_name }},</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 24px;">Welcome to the <strong style="color:#1e293b;">{{ company_name }}</strong> monthly briefing — your curated selection of insights, updates, and stories from our world.</p>
<div style="background:#f8fafc;border-radius:14px;padding:28px;margin:24px 0;border:1px solid #e2e8f0;">
<div style="width:36px;height:36px;background:#eef2ff;border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;">
<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="2"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
</div>
<h2 style="color:#1e293b;font-size:17px;font-weight:600;margin:0 0 8px;">Feature Spotlight</h2>
<p style="color:#475569;font-size:14px;line-height:1.6;margin:0;">Discover our latest tools designed to elevate your experience — smarter, faster, and more intuitive than ever.</p>
</div>
<div style="background:#f8fafc;border-radius:14px;padding:28px;margin:24px 0;border:1px solid #e2e8f0;">
<div style="width:36px;height:36px;background:#fff7ed;border-radius:10px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;">
<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ea580c" stroke-width="2"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
</div>
<h2 style="color:#1e293b;font-size:17px;font-weight:600;margin:0 0 8px;">Pro Tip</h2>
<p style="color:#475569;font-size:14px;line-height:1.6;margin:0;">Save hours each week by automating your email campaigns with our intelligent builder. Set it once, and let it work.</p>
</div>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 4px;">Thank you for being part of our journey.</p>
<p style="color:#1e293b;font-size:15px;line-height:1.7;margin:0;">Warmly,<br><span style="color:#4f46e5;font-weight:600;">The {{ company_name }} Team</span></p>
</td></tr>
<tr><td style="background:#f8fafc;padding:24px 40px;text-align:center;border-top:1px solid #e2e8f0;">
<p style="color:#94a3b8;font-size:11px;margin:0;">{{ company_name }} · Crafted with care</p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

Welcome to the {{ month }} edition of the {{ company_name }} monthly briefing.

FEATURE SPOTLIGHT
Discover our latest tools designed to elevate your experience.

PRO TIP
Save hours each week by automating your email campaigns.

Thank you for being part of our journey.

Warmly,
The {{ company_name }} Team''',
}

PROMO_TEMPLATE = {
    'name': 'VIP Promo',
    'subject': 'An exclusive offer for you, {{ first_name }}',
    'body_html': '''<div style="background-color:#fafafa;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
<tr><td style="background:linear-gradient(135deg,#0f0f13,#1a1a24);padding:48px 40px 36px;text-align:center;">
<div style="width:56px;height:56px;margin:0 auto 20px;background:linear-gradient(135deg,#d4af37,#f7e8a0);border-radius:50%;display:flex;align-items:center;justify-content:center;">
<span style="color:#0f0f13;font-size:22px;font-weight:700;">&#10003;</span>
</div>
<p style="color:#a0a0ab;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;margin:0 0 8px;">Exclusive · For You</p>
<h1 style="color:#ffffff;font-size:24px;font-weight:600;margin:0;letter-spacing:-0.01em;">A Special Offer Awaits</h1>
</td></tr>
<tr><td style="padding:36px 40px;background:#ffffff;">
<p style="color:#1e293b;font-size:16px;line-height:1.7;margin:0 0 16px;">Dear {{ first_name }},</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 24px;">As a valued member of <strong style="color:#1e293b;">{{ company_name }}</strong>, we invite you to enjoy an exclusive <strong style="color:#059669;">20% savings</strong> on your next experience.</p>
<div style="background:linear-gradient(135deg,#f0fdf4,#ecfdf5);border-radius:16px;padding:28px;text-align:center;margin:24px 0;border:1px solid #a7f3d0;">
<p style="font-size:32px;font-weight:800;color:#065f46;letter-spacing:4px;margin:0 0 4px;font-family:Georgia,serif;">SAVE20</p>
<p style="color:#047857;font-size:13px;margin:0;font-weight:500;">Your exclusive code · Valid this month</p>
</div>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 8px;">Questions? Our team is always here to help.</p>
<p style="color:#1e293b;font-size:15px;line-height:1.7;margin:0;">With appreciation,<br><span style="color:#059669;font-weight:600;">The {{ company_name }} Team</span></p>
</td></tr>
<tr><td style="background:#fafafa;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0;">
<p style="color:#94a3b8;font-size:11px;margin:0;">{{ company_name }} · Elevated experiences</p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

As a valued member of {{ company_name }}, we invite you to enjoy an exclusive 20% savings on your next experience.

Use code: SAVE20

Valid this month.

Questions? Our team is always here to help.

With appreciation,
The {{ company_name }} Team''',
}

EVENT_TEMPLATE = {
    'name': 'Exclusive Event',
    'subject': 'You are cordially invited, {{ first_name }}',
    'body_html': '''<div style="background-color:#0b0b12;padding:40px 20px;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
<tr><td style="text-align:center;padding:0 0 24px;">
<div style="border:1px solid rgba(212,175,55,0.3);border-radius:50%;width:80px;height:80px;margin:0 auto 24px;display:flex;align-items:center;justify-content:center;">
<div style="width:64px;height:64px;border-radius:50%;background:linear-gradient(135deg,#d4af37,#f7e8a0);display:flex;align-items:center;justify-content:center;">
<span style="color:#0b0b12;font-size:28px;">&#10087;</span>
</div>
</div>
<p style="color:#d4af37;font-size:11px;letter-spacing:0.22em;text-transform:uppercase;margin:0 0 6px;">You are cordially invited</p>
<h1 style="color:#f7e8a0;font-size:30px;font-weight:400;margin:0;letter-spacing:0.04em;">An Evening With</h1>
<h2 style="color:#ffffff;font-size:20px;font-weight:300;margin:8px 0 0;letter-spacing:0.15em;text-transform:uppercase;">{{ company_name }}</h2>
</td></tr>
<tr><td style="background:rgba(18,18,26,0.95);border-radius:16px;padding:40px;border:1px solid rgba(212,175,55,0.12);">
<p style="color:#e8e8ed;font-size:16px;line-height:1.8;margin:0 0 20px;">Dear {{ first_name }},</p>
<p style="color:#a0a0ab;font-size:15px;line-height:1.8;margin:0 0 24px;">We would be honored by your presence at an exclusive gathering hosted by <strong style="color:#e8e8ed;">{{ company_name }}</strong> — an evening of insight, connection, and inspiration.</p>
<div style="border:1px solid rgba(212,175,55,0.2);border-radius:12px;padding:24px;margin:24px 0;background:rgba(212,175,55,0.03);">
<p style="color:#f7e8a0;font-size:13px;letter-spacing:0.12em;text-transform:uppercase;margin:0 0 12px;font-family:-apple-system,sans-serif;">Event Details</p>
<p style="color:#a0a0ab;font-size:14px;line-height:1.6;margin:0;">An intimate gathering featuring curated conversations, exclusive previews, and connections that matter. Space is limited to ensure an exceptional experience.</p>
</div>
<p style="color:#a0a0ab;font-size:15px;line-height:1.8;margin:0 0 8px;">Kindly confirm your attendance at your earliest convenience.</p>
<p style="color:#e8e8ed;font-size:15px;line-height:1.8;margin:0;">Yours sincerely,<br><span style="color:#d4af37;">The {{ company_name }} Team</span></p>
</td></tr>
<tr><td style="text-align:center;padding:24px 0 0;">
<p style="color:#5a5a65;font-size:10px;letter-spacing:0.12em;margin:0;">{{ company_name }} · By invitation only</p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

You are cordially invited.

We would be honored by your presence at an exclusive gathering hosted by {{ company_name }} — an evening of insight, connection, and inspiration.

Event Details: An intimate gathering featuring curated conversations and exclusive previews. Space is limited.

Kindly confirm your attendance at your earliest convenience.

Yours sincerely,
The {{ company_name }} Team''',
}

THANK_YOU_TEMPLATE = {
    'name': 'Gracious Thank You',
    'subject': 'Gratitude, {{ first_name }}',
    'body_html': '''<div style="background:linear-gradient(135deg,#fefce8,#fef9e7);padding:40px 20px;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
<tr><td style="text-align:center;padding:0 0 28px;">
<div style="width:64px;height:64px;margin:0 auto 20px;background:linear-gradient(135deg,#d97706,#f59e0b);border-radius:16px;display:flex;align-items:center;justify-content:center;">
<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2"><path d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>
</div>
<h1 style="color:#78350f;font-size:28px;font-weight:500;margin:0;letter-spacing:0.02em;">Thank You</h1>
</td></tr>
<tr><td style="background:#ffffff;border-radius:16px;padding:40px;box-shadow:0 1px 3px rgba(0,0,0,0.04);border:1px solid #fef3c7;">
<p style="color:#78350f;font-size:16px;line-height:1.8;margin:0 0 20px;">Dear {{ first_name }},</p>
<p style="color:#92400e;font-size:15px;line-height:1.8;margin:0 0 20px;">On behalf of everyone at <strong style="color:#78350f;">{{ company_name }}</strong>, we extend our deepest gratitude for your continued trust and partnership.</p>
<div style="background:linear-gradient(135deg,#fffbeb,#fef3c7);border-radius:12px;padding:24px;margin:24px 0;border:1px solid #fde68a;">
<p style="color:#92400e;font-size:14px;line-height:1.7;margin:0;font-family:-apple-system,sans-serif;">Your support inspires us to push boundaries, refine our craft, and deliver nothing less than exceptional. It is a privilege to serve you.</p>
</div>
<p style="color:#92400e;font-size:15px;line-height:1.8;margin:0 0 8px;">As a token of our appreciation, stay tuned for exclusive previews and experiences crafted with you in mind.</p>
<p style="color:#78350f;font-size:15px;line-height:1.8;margin:0;">With heartfelt gratitude,<br><span style="color:#d97706;">The {{ company_name }} Team</span></p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

On behalf of everyone at {{ company_name }}, we extend our deepest gratitude for your continued trust and partnership.

Your support inspires us to push boundaries, refine our craft, and deliver nothing less than exceptional.

With heartfelt gratitude,
The {{ company_name }} Team''',
}

FEEDBACK_TEMPLATE = {
    'name': 'Premier Feedback',
    'subject': 'Your perspective matters, {{ first_name }}',
    'body_html': '''<div style="background-color:#ffffff;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
<tr><td style="background:#f8fafc;padding:40px 40px 32px;text-align:center;border-bottom:3px solid #6366f1;">
<div style="width:56px;height:56px;margin:0 auto 16px;background:#eef2ff;border-radius:14px;display:flex;align-items:center;justify-content:center;">
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="2"><path d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"/></svg>
</div>
<h1 style="color:#1e293b;font-size:24px;font-weight:700;margin:0;letter-spacing:-0.02em;">We Value Your Voice</h1>
<p style="color:#6366f1;font-size:13px;margin:8px 0 0;font-weight:500;">Your perspective shapes what we build</p>
</td></tr>
<tr><td style="padding:36px 40px;">
<p style="color:#1e293b;font-size:16px;line-height:1.7;margin:0 0 16px;">Dear {{ first_name }},</p>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 24px;">At <strong style="color:#1e293b;">{{ company_name }}</strong>, we believe the finest experiences are shaped by those who use them. Your insights are the cornerstone of our growth.</p>
<div style="border-radius:14px;padding:28px;text-align:center;margin:24px 0;">
<p style="color:#1e293b;font-size:16px;font-weight:600;margin:0 0 16px;letter-spacing:-0.01em;">How would you rate your experience?</p>
<div style="font-size:32px;letter-spacing:10px;color:#f59e0b;margin-bottom:20px;">&#9733; &#9733; &#9733; &#9733; &#9733;</div>
<p style="color:#94a3b8;font-size:13px;margin:0;">It takes less than two minutes and makes a world of difference.</p>
</div>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 4px;">Thank you for helping us raise the bar.</p>
<p style="color:#1e293b;font-size:15px;line-height:1.7;margin:0;">With appreciation,<br><span style="color:#4f46e5;font-weight:600;">The {{ company_name }} Team</span></p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

At {{ company_name }}, we believe the finest experiences are shaped by those who use them. Your insights are the cornerstone of our growth.

How would you rate your experience? It takes less than two minutes and makes a world of difference.

Thank you for helping us raise the bar.

With appreciation,
The {{ company_name }} Team''',
}

REACTIVATION_TEMPLATE = {
    'name': 'Elite Re-engagement',
    'subject': '{{ first_name }}, we would love to welcome you back',
    'body_html': '''<div style="background:linear-gradient(135deg,#0f172a,#1e293b);padding:40px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
<tr><td style="text-align:center;padding:0 0 28px;">
<div style="width:72px;height:72px;margin:0 auto 20px;background:linear-gradient(135deg,#38bdf8,#818cf8);border-radius:50%;display:flex;align-items:center;justify-content:center;">
<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
</div>
<h1 style="color:#f8fafc;font-size:26px;font-weight:600;margin:0;letter-spacing:-0.02em;">We Miss You</h1>
<p style="color:#94a3b8;font-size:14px;margin:8px 0 0;">It has been too long, {{ first_name }}</p>
</td></tr>
<tr><td style="background:rgba(30,41,59,0.8);border-radius:16px;padding:36px;border:1px solid rgba(148,163,184,0.1);">
<p style="color:#f1f5f9;font-size:16px;line-height:1.7;margin:0 0 16px;">Dear {{ first_name }},</p>
<p style="color:#94a3b8;font-size:15px;line-height:1.7;margin:0 0 20px;">It has been a while since we last connected at <strong style="color:#f1f5f9;">{{ company_name }}</strong>, and we would be honored to welcome you back.</p>
<div style="background:linear-gradient(135deg,rgba(56,189,248,0.08),rgba(129,140,248,0.08));border-radius:12px;padding:24px;margin:20px 0;border:1px solid rgba(56,189,248,0.15);">
<p style="color:#bae6fd;font-size:14px;line-height:1.6;margin:0;">We have been busy crafting something extraordinary. Come explore what is new — you may find yourself pleasantly surprised.</p>
</div>
<p style="color:#94a3b8;font-size:15px;line-height:1.7;margin:0 0 8px;">Your journey with us is far from over. Let us begin anew.</p>
<p style="color:#f1f5f9;font-size:15px;line-height:1.7;margin:0;">Warmly,<br><span style="background:linear-gradient(135deg,#38bdf8,#818cf8);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;font-weight:600;">The {{ company_name }} Team</span></p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

It has been a while since we last connected at {{ company_name }}, and we would be honored to welcome you back.

We have been busy crafting something extraordinary. Come explore what is new.

Your journey with us is far from over. Let us begin anew.

Warmly,
The {{ company_name }} Team''',
}

PRODUCT_UPDATE_TEMPLATE = {
    'name': 'Executive Update',
    'subject': 'What is new at {{ company_name }}',
    'body_html': '''<div style="background-color:#ffffff;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
<tr><td style="padding:32px 40px;border-bottom:1px solid #e2e8f0;">
<div style="display:flex;align-items:center;justify-content:space-between;">
<span style="color:#6366f1;font-size:13px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">Product Update</span>
<span style="color:#94a3b8;font-size:12px;">{{ month }}</span>
</div>
</td></tr>
<tr><td style="padding:36px 40px 20px;">
<h1 style="color:#0f172a;font-size:26px;font-weight:700;margin:0 0 8px;letter-spacing:-0.03em;">New & Notable</h1>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 24px;">Dear {{ first_name }}, we have been hard at work refining every detail of the <strong style="color:#0f172a;">{{ company_name }}</strong> experience.</p>
<div style="display:grid;gap:16px;margin:24px 0;">
<div style="background:#f8fafc;border-radius:12px;padding:20px;border:1px solid #e2e8f0;">
<div style="width:32px;height:32px;background:#eef2ff;border-radius:8px;display:flex;align-items:center;justify-content:center;margin-bottom:10px;">
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#4f46e5" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/></svg>
</div>
<h3 style="color:#0f172a;font-size:15px;font-weight:600;margin:0 0 4px;">Redesigned Dashboard</h3>
<p style="color:#64748b;font-size:13px;line-height:1.5;margin:0;">Cleaner, faster, and more intuitive — built for clarity at a glance.</p>
</div>
<div style="background:#f8fafc;border-radius:12px;padding:20px;border:1px solid #e2e8f0;">
<div style="width:32px;height:32px;background:#f0fdf4;border-radius:8px;display:flex;align-items:center;justify-content:center;margin-bottom:10px;">
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
</div>
<h3 style="color:#0f172a;font-size:15px;font-weight:600;margin:0 0 4px;">AI-Powered Insights</h3>
<p style="color:#64748b;font-size:13px;line-height:1.5;margin:0;">Intelligent analytics that surface opportunities you might have missed.</p>
</div>
<div style="background:#f8fafc;border-radius:12px;padding:20px;border:1px solid #e2e8f0;">
<div style="width:32px;height:32px;background:#fff7ed;border-radius:8px;display:flex;align-items:center;justify-content:center;margin-bottom:10px;">
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ea580c" stroke-width="2"><path d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
</div>
<h3 style="color:#0f172a;font-size:15px;font-weight:600;margin:0 0 4px;">Performance Boost</h3>
<p style="color:#64748b;font-size:13px;line-height:1.5;margin:0;">Up to 2x faster load times. Speed meets sophistication.</p>
</div>
</div>
<p style="color:#475569;font-size:15px;line-height:1.7;margin:0 0 4px;">Explore the latest and see what is possible.</p>
<p style="color:#0f172a;font-size:15px;line-height:1.7;margin:0;">Best regards,<br><span style="color:#6366f1;font-weight:600;">The {{ company_name }} Team</span></p>
</td></tr>
</table>
</div>''',
    'body_text': '''Dear {{ first_name }},

We have been hard at work refining every detail of the {{ company_name }} experience.

NEW & NOTABLE:

Redesigned Dashboard - Cleaner, faster, and more intuitive.
AI-Powered Insights - Intelligent analytics that surface opportunities.
Performance Boost - Up to 2x faster load times.

Explore the latest and see what is possible.

Best regards,
The {{ company_name }} Team''',
}
