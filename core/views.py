from django.shortcuts import render

def landing_view(request):

    feature_categories = [
    {
        "category": "Email Campaigns",
        "subtitle": "High-performance campaign engine with AI-driven deliverability",
        "features": [
            {
                "title": "AI-Powered Sending",
                "description": "Optimize send times, subject lines, and content automatically with machine learning for every segment.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>
                </svg>
                """
            },
            {
                "title": "Real-Time Tracking",
                "description": "Track opens, clicks, bounces, and conversions across every campaign in a unified dashboard.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 3v18h18M9 17V9m4 8V5m4 12v-6"/>
                </svg>
                """
            },
            {
                "title": "A/B Testing",
                "description": "Test subject lines, content, and send times to find what resonates before full deployment.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                </svg>
                """
            },
            {
                "title": "Visual Automation Builder",
                "description": "Design multi-step drip campaigns, onboarding sequences, and triggered flows with a drag-and-drop canvas.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4h6v6H4V4zm10 0h6v6h-6V4zM4 14h6v6H4v-6zm10 0h6v6h-6v-6z"/>
                </svg>
                """
            }
        ]
    },
    {
        "category": "AI & Intelligence",
        "subtitle": "Machine learning tools that improve every send",
        "features": [
            {
                "title": "Smart Spam Analysis",
                "description": "Pre-scan every campaign against spam filters, blacklists, and content rules before it hits inboxes.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3l7 4v5c0 5-3.5 9-7 9s-7-4-7-9V7l7-4z"/>
                </svg>
                """
            },
            {
                "title": "AI Copywriter",
                "description": "Generate subject lines, email body copy, and social posts from prompts with brand voice controls.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                </svg>
                """
            },
            {
                "title": "AI Copilot",
                "description": "Get real-time recommendations for sending windows, audience segments, and content improvements.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
                </svg>
                """
            },
            {
                "title": "Content Studio",
                "description": "Create and version email content, social posts, and landing pages with AI-assisted drafting and team review.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/>
                </svg>
                """
            }
        ]
    },
    {
        "category": "Contacts & Senders",
        "subtitle": "Reputation management and audience intelligence",
        "features": [
            {
                "title": "Sender Reputation",
                "description": "Monitor domain reputation, track warm-up progress, and manage dedicated IP pools from one console.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2v16z"/>
                </svg>
                """
            },
            {
                "title": "DNS Audit",
                "description": "Automatic SPF, DKIM, and DMARC checks with remediation guides for better inbox placement.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
                </svg>
                """
            },
            {
                "title": "Contact Segmentation",
                "description": "Build dynamic segments based on behavior, engagement, custom fields, and list membership.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"/>
                </svg>
                """
            },
            {
                "title": "SMTP & API Senders",
                "description": "Connect Gmail, Outlook, custom SMTP, or transactional APIs — manage all senders from one place.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H3a1 1 0 01-1-1V5a1 1 0 011-1h12a1 1 0 011 1v2m-4 8h6a1 1 0 001-1V9a1 1 0 00-1-1h-6a1 1 0 00-1 1v6a1 1 0 001 1z"/>
                </svg>
                """
            }
        ]
    },
    {
        "category": "Social Media",
        "subtitle": "Publish, schedule, and analyze across every major platform",
        "features": [
            {
                "title": "Multi-Platform Publishing",
                "description": "Schedule and publish content to Facebook, Instagram, X (Twitter), LinkedIn, TikTok, and YouTube.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/>
                </svg>
                """
            },
            {
                "title": "Social Analytics",
                "description": "Track engagement, follower growth, post performance, and ROI across all connected accounts.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z"/>
                </svg>
                """
            },
            {
                "title": "Content Calendar",
                "description": "Visual calendar for planning, drafting, and approving posts across teams and platforms.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                </svg>
                """
            },
            {
                "title": "Media Assets Library",
                "description": "Centralized storage for images, videos, and documents with auto-tagging and version history.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                </svg>
                """
            }
        ]
    },
    {
        "category": "Workspace & Control",
        "subtitle": "Team collaboration with enterprise-grade security",
        "features": [
            {
                "title": "Team Workspaces",
                "description": "Multi-tenant workspaces with isolated data, custom branding, and per-workspace settings.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>
                </svg>
                """
            },
            {
                "title": "Role-Based Access",
                "description": "Granular permissions for admin, manager, and editor roles across every module.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
                </svg>
                """
            },
            {
                "title": "Audit & Compliance",
                "description": "Full activity logs, GDPR compliance tools, and export controls for regulatory requirements.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/>
                </svg>
                """
            },
            {
                "title": "Inbox Management",
                "description": "Connect Gmail/Outlook, manage threaded conversations, smart drafts, and auto-replies.",
                "icon_svg": """
                <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
                </svg>
                """
            }
        ]
    }
]
    
    # Keep testimonial entries realistic and specific so social-proof sections feel trustworthy.
    testimonials = [
    {
        "quote": "We switched from Mailchimp and our inbox delivery rate jumped from 71% to 98.4% in the first two weeks. The AI optimization alone paid for itself in the first campaign.",
        "author": "Aakriti Maharjan",
        "role": "Head of Growth",
        "company": "Forma Labs",
        "initials": "AM",
        "color": "bg-indigo-100 text-indigo-600"
    },
    {
        "quote": "Intelligent Digital Automation (IDA)'s automation builder is the cleanest I've used. We set up a 12-step onboarding sequence in an afternoon — something that took us weeks with our old provider.",
        "author": "Anuj Paudel",
        "role": "CTO",
        "company": "Stackpath",
        "initials": "AP",
        "color": "bg-green-100 text-green-600"
    },
    {
        "quote": "The analytics dashboard gives us exactly what we need — no clutter, no guesswork. Our team finally agreed on one source of truth for email performance.",
        "author": "Narayan Prasad Ghimire",
        "role": "Marketing Director",
        "company": "Neon Digital",
        "initials": "NG",
        "color": "bg-slate-200 text-slate-600"
    },
    {
        "quote": "We run seasonal campaigns for multiple retail brands. Intelligent Digital Automation (IDA) helped us stabilize sender reputation and cut bounce complaints by more than half.",
        "author": "Sujan Khadka",
        "role": "CRM Lead",
        "company": "Orbit Commerce",
        "initials": "SK",
        "color": "bg-violet-100 text-violet-700"
    },
    {
        "quote": "Before this, our team spent hours cleaning lists and checking spam triggers manually. Now pre-send checks are automatic and launches are much faster.",
        "author": "Ritika Basnet",
        "role": "Lifecycle Manager",
        "company": "Northfield SaaS",
        "initials": "RB",
        "color": "bg-emerald-100 text-emerald-700"
    },
    {
        "quote": "The platform made it easy to onboard regional teams with separate sender identities while still keeping central control over standards and limits.",
        "author": "Prabin Adhikari",
        "role": "Operations Director",
        "company": "Aster Mobility",
        "initials": "PA",
        "color": "bg-amber-100 text-amber-700"
    },
    {
        "quote": "We migrated in under a week and saw immediate gains in open reliability. The UI is clean enough that non-technical marketers can ship confidently.",
        "author": "Mina Shrestha",
        "role": "Digital Marketing Manager",
        "company": "Summit Finserve",
        "initials": "MS",
        "color": "bg-rose-100 text-rose-700"
    }
]
    stats = [
    {
        "value": "4.2B+",
        "label": "Emails Delivered",
        "description": "Across all campaigns this year",
        "icon_svg": """
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l9 6 9-6M4 6h16a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V8a2 2 0 012-2z"/>
        </svg>
        """
    },
    {
        "value": "98.7%",
        "label": "Inbox Delivery Rate",
        "description": "Industry-leading placement",
        "icon_svg": """
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 17l6-6 4 4 8-8"/>
        </svg>
        """
    },
    {
        "value": "12,000+",
        "label": "Businesses Onboarded",
        "description": "From startups to enterprises",
        "icon_svg": """
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6M7 4h10a2 2 0 012 2v14l-5-3-5 3V6a2 2 0 012-2z"/>
        </svg>
        """
    },
    {
        "value": "94%",
        "label": "Spam Reduction",
        "description": "vs. previous email providers",
        "icon_svg": """
        <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3l7 4v5c0 5-3.5 9-7 9s-7-4-7-9V7l7-4z"/>
        </svg>
        """
    }
]
    plans = [
    {
        "name": "Free",
        "price": "रु 0",
        "yearly_price": "रु 0",
        "period": "forever",
        "description": "Perfect for individuals and small experiments.",
        "badge": None,
        "highlighted": False,
        "features": [
            "500 emails / month",
            "1 sender domain",
            "Basic analytics",
            "Drag-and-drop editor",
            "Community support"
        ],
        "cta": "Get started free"
    },
    {
        "name": "Pro",
        "price": "रु 499",
        "yearly_price": "रु 399/mo",
        "period": "month",
        "description": "For growing teams that need power and deliverability.",
        "badge": "Most popular",
        "highlighted": True,
        "features": [
            "50,000 emails / month",
            "5 sender domains",
            "Advanced analytics & reporting",
            "AI subject line optimization",
            "Visual automation builder",
            "Priority inbox routing",
            "Email & chat support"
        ],
        "cta": "Start Pro trial"
    },
    {
        "name": "Business",
        "price": "रु 1,499",
        "yearly_price": "रु 1,199/mo",
        "period": "month",
        "description": "Enterprise-grade sending for high-volume operations.",
        "badge": None,
        "highlighted": False,
        "features": [
            "500,000 emails / month",
            "Unlimited sender domains",
            "Full analytics suite",
            "AI optimization suite",
            "Advanced automations & flows",
            "Dedicated IP address",
            "Priority SLA support",
            "Custom contracts & billing"
        ],
        "cta": "Contact sales"
    }
]

    product_modules = [
    {
        "id": "email",
        "label": "Email",
        "title": "Email campaigns that actually land",
        "description": "AI-optimized subject lines, pre-send spam scoring, and real-time inbox tracking — so every send reaches the inbox, not the spam folder.",
        "features": [
            "AI subject line optimization",
            "Pre-send spam scoring",
            "A/B testing & send-time AI",
            "Visual drip automations",
            "Real-time deliverability dashboard"
        ],
        "cta": "Explore email"
    },
    {
        "id": "social",
        "label": "Social",
        "title": "Social media, on every platform",
        "description": "Schedule, publish, and analyze posts across Facebook, Instagram, X, LinkedIn, TikTok, and YouTube from one unified calendar.",
        "features": [
            "Multi-platform publishing",
            "Visual content calendar",
            "AI post suggestions",
            "Cross-channel analytics",
            "Auto RSS-to-social"
        ],
        "cta": "Explore social"
    },
    {
        "id": "content",
        "label": "Content Studio",
        "title": "AI content that matches your brand",
        "description": "Generate blog posts, social copy, email sequences, and landing pages with AI trained on your brand voice and audience.",
        "features": [
            "Brand voice training",
            "Multi-format generation",
            "Version history & approvals",
            "Content templates",
            "Tone & length controls"
        ],
        "cta": "Explore content"
    },
    {
        "id": "automations",
        "label": "Automations",
        "title": "Workflows that run while you sleep",
        "description": "Build complex multi-channel automations on a visual drag-and-drop canvas — connecting email, social, contacts, and any HTTP endpoint.",
        "features": [
            "Visual workflow builder",
            "Multi-step triggers",
            "Conditional branching",
            "Webhook integrations",
            "Real-time activity log"
        ],
        "cta": "Explore automations"
    },
    {
        "id": "inbox",
        "label": "Inbox",
        "title": "A unified inbox for every conversation",
        "description": "Connect Gmail, Outlook, and any IMAP inbox. Get AI-drafted replies, smart labels, and team collaboration built right in.",
        "features": [
            "Multi-account support",
            "AI reply suggestions",
            "Smart labels & filters",
            "Team assignments",
            "Threaded conversations"
        ],
        "cta": "Explore inbox"
    }
]

    workflow_steps = [
    {
        "number": "01",
        "title": "Connect your channels",
        "description": "Bring email, social, contacts, and content tools together in minutes — no code, no migration headaches.",
        "icon_svg": """
        <svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
          <path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 015.656 0l1.415 1.415a4 4 0 010 5.656l-3 3a4 4 0 01-5.656 0M10.172 13.828a4 4 0 01-5.656 0l-1.415-1.415a4 4 0 010-5.656l3-3a4 4 0 015.656 0"/>
        </svg>
        """
    },
    {
        "number": "02",
        "title": "Build with AI",
        "description": "Generate copy, design flows, and optimize sends with AI trained on millions of high-performing campaigns.",
        "icon_svg": """
        <svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
        </svg>
        """
    },
    {
        "number": "03",
        "title": "Launch & measure",
        "description": "Send across every channel and watch real-time analytics tell you exactly what's working — and what to improve next.",
        "icon_svg": """
        <svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
          <path stroke-linecap="round" stroke-linejoin="round" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/>
        </svg>
        """
    }
]

    integrations = [
        {"name": "Gmail", "color": "from-red-500 to-orange-500"},
        {"name": "Outlook", "color": "from-blue-500 to-cyan-500"},
        {"name": "SMTP", "color": "from-slate-500 to-slate-700"},
        {"name": "Facebook", "color": "from-blue-600 to-blue-800"},
        {"name": "Instagram", "color": "from-pink-500 to-purple-600"},
        {"name": "X / Twitter", "color": "from-slate-700 to-slate-900"},
        {"name": "LinkedIn", "color": "from-blue-700 to-sky-600"},
        {"name": "TikTok", "color": "from-pink-500 to-slate-900"},
        {"name": "YouTube", "color": "from-red-600 to-red-800"},
        {"name": "Slack", "color": "from-purple-500 to-pink-500"},
        {"name": "Zapier", "color": "from-orange-500 to-red-500"},
        {"name": "Webhooks", "color": "from-indigo-500 to-purple-500"}
    ]

    faqs = [
    {
        "question": "What channels does DIA support?",
        "answer": "DIA supports email (any SMTP, plus Gmail and Outlook), six social platforms (Facebook, Instagram, X, LinkedIn, TikTok, YouTube), a built-in content studio, and a unified inbox. You can also wire in any tool via webhooks or Zapier."
    },
    {
        "question": "How does the AI optimization work?",
        "answer": "DIA's AI analyzes your historical send data, audience behavior, and industry benchmarks to recommend subject lines, send times, content variations, and audience segments. It also runs a pre-send spam score so you know how an email will perform before it goes out."
    },
    {
        "question": "Can I import my existing contacts and campaigns?",
        "answer": "Yes. You can import contacts from CSV, sync from your CRM, or migrate directly from Mailchimp, SendGrid, or any SMTP-based provider. Templates and campaigns import as well — most teams are live in under an hour."
    },
    {
        "question": "Is my data secure?",
        "answer": "All data is encrypted in transit (TLS 1.3) and at rest (AES-256). Workspaces are isolated, role-based access is enforced, and full audit logs are available on every plan. We're GDPR, CCPA, and SOC 2 ready."
    },
    {
        "question": "Do you have a free plan?",
        "answer": "Yes — our Free plan includes 500 emails per month, 1 sender domain, basic analytics, and the drag-and-drop editor. No credit card required to start."
    },
    {
        "question": "Can I cancel or change plans anytime?",
        "answer": "Absolutely. Plans are month-to-month with no long-term contracts. You can upgrade, downgrade, or cancel from your billing settings at any time."
    }
]



    return render(request, "landing/index.html", {
        "feature_categories": feature_categories,
        "testimonials": testimonials,
        "stats": stats,
        "plans": plans,
        "product_modules": product_modules,
        "workflow_steps": workflow_steps,
        "integrations": integrations,
        "faqs": faqs,
    })