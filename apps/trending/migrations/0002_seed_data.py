from django.db import migrations


TOPICS = [
    {'name': 'Artificial Intelligence', 'slug': 'artificial-intelligence', 'description': 'AI, machine learning, deep learning, GPT, neural networks, and LLMs', 'icon': '🤖', 'color': '#8B5CF6', 'keywords': ['AI', 'artificial intelligence', 'machine learning', 'deep learning', 'GPT', 'neural network', 'LLM', 'transformer', 'diffusion', 'GAN', 'NLP', 'computer vision', 'RL', 'reinforcement learning', 'ChatGPT', 'OpenAI', 'Gemini', 'Claude']},
    {'name': 'Web Development', 'slug': 'web-development', 'description': 'React, Next.js, Django, APIs, frontend, and backend frameworks', 'icon': '🌐', 'color': '#3B82F6', 'keywords': ['React', 'Next.js', 'Django', 'Flask', 'FastAPI', 'Node.js', 'TypeScript', 'JavaScript', 'CSS', 'HTML', 'API', 'REST', 'GraphQL', 'full-stack', 'frontend', 'backend', 'Tailwind']},
    {'name': 'Cybersecurity', 'slug': 'cybersecurity', 'description': 'Security, vulnerabilities, malware, encryption, and zero-day threats', 'icon': '🔒', 'color': '#DC2626', 'keywords': ['security', 'cybersecurity', 'vulnerability', 'malware', 'ransomware', 'encryption', 'zero-day', 'CVE', 'penetration', 'firewall', 'authentication', 'breach', 'exploit']},
    {'name': 'Cloud & DevOps', 'slug': 'cloud-devops', 'description': 'AWS, Docker, Kubernetes, CI/CD, Terraform, and cloud infrastructure', 'icon': '☁️', 'color': '#F59E0B', 'keywords': ['AWS', 'Docker', 'Kubernetes', 'K8s', 'CI/CD', 'Terraform', 'cloud', 'devops', 'microservices', 'Jenkins', 'GitHub Actions', 'deployment', 'infrastructure']},
    {'name': 'Data Science', 'slug': 'data-science', 'description': 'Data analysis, visualization, pandas, SQL, and statistical modeling', 'icon': '📊', 'color': '#10B981', 'keywords': ['data', 'analytics', 'data science', 'visualization', 'pandas', 'NumPy', 'SQL', 'statistics', 'regression', 'classification', 'Tableau', 'Power BI', 'ETL']},
    {'name': 'Mobile Development', 'slug': 'mobile-development', 'description': 'iOS, Android, Swift, Kotlin, React Native, and Flutter', 'icon': '📱', 'color': '#EC4899', 'keywords': ['iOS', 'Android', 'Swift', 'Kotlin', 'React Native', 'Flutter', 'mobile', 'app development', 'App Store', 'Play Store', 'Xcode']},
    {'name': 'Startup & Business', 'slug': 'startup-business', 'description': 'Startups, funding, VC, growth, SaaS, and entrepreneurship', 'icon': '🚀', 'color': '#F97316', 'keywords': ['startup', 'SaaS', 'funding', 'venture capital', 'VC', 'growth', 'entrepreneurship', 'IPO', 'valuation', 'revenue', 'ARR', 'MRR', 'pitch', 'accelerator']},
    {'name': 'Blockchain & Web3', 'slug': 'blockchain-web3', 'description': 'Blockchain, crypto, NFTs, DeFi, smart contracts, and dApps', 'icon': '⛓️', 'color': '#6366F1', 'keywords': ['blockchain', 'crypto', 'cryptocurrency', 'NFT', 'DeFi', 'smart contract', 'Ethereum', 'Solana', 'Bitcoin', 'Web3', 'dApp', 'wallet', 'token']},
    {'name': 'Design & UX', 'slug': 'design-ux', 'description': 'UI/UX design, Figma, accessibility, design systems, and prototyping', 'icon': '🎨', 'color': '#A855F7', 'keywords': ['design', 'UX', 'UI', 'Figma', 'Sketch', 'accessibility', 'a11y', 'design system', 'prototype', 'user research', 'wireframe', 'typography']},
    {'name': 'Open Source', 'slug': 'open-source', 'description': 'Open source projects, contributions, licenses, and community', 'icon': '📖', 'color': '#14B8A6', 'keywords': ['open source', 'GitHub', 'GitLab', 'contribution', 'license', 'MIT', 'GPL', 'Apache', 'community', 'maintainer', 'pull request', 'repository']},
]

SOURCES = [
    {'name': 'Hacker News', 'source_type': 'rss', 'url': 'https://hnrss.org/frontpage', 'poll_interval_hours': 6},
    {'name': 'Dev.to', 'source_type': 'rss', 'url': 'https://dev.to/feed', 'poll_interval_hours': 6},
    {'name': 'GitHub Trending', 'source_type': 'api', 'url': 'https://api.github.com/search/repositories', 'poll_interval_hours': 6, 'config_json': {'query': 'stars:>100', 'sort': 'stars', 'order': 'desc', 'per_page': 30}},
    {'name': 'TechCrunch', 'source_type': 'rss', 'url': 'https://techcrunch.com/feed/', 'poll_interval_hours': 6},
]


def seed_data(apps, schema_editor):
    Topic = apps.get_model('trending', 'Topic')
    ContentSource = apps.get_model('trending', 'ContentSource')

    for t in TOPICS:
        Topic.objects.get_or_create(
            slug=t['slug'],
            defaults=t,
        )

    for s in SOURCES:
        ContentSource.objects.get_or_create(
            name=s['name'],
            defaults=s,
        )


def reverse_seed(apps, schema_editor):
    Topic = apps.get_model('trending', 'Topic')
    ContentSource = apps.get_model('trending', 'ContentSource')
    Topic.objects.filter(slug__in=[t['slug'] for t in TOPICS]).delete()
    ContentSource.objects.filter(name__in=[s['name'] for s in SOURCES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('trending', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_data, reverse_seed),
    ]
