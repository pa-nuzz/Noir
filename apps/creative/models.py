from django.conf import settings
from django.db import models

from core.tenant import TenantManager


class CreativeContext(models.Model):
    objects = TenantManager()
    COUNTRY_CHOICES = [
        ('nepal', 'Nepal'),
        ('india', 'India'),
        ('usa', 'United States'),
        ('uk', 'United Kingdom'),
        ('australia', 'Australia'),
        ('other', 'Other'),
    ]
    INDUSTRY_CHOICES = [
        ('', 'None selected'),
        ('technology', 'Technology & IT'),
        ('finance', 'Finance & Banking'),
        ('healthcare', 'Healthcare & Wellness'),
        ('education', 'Education & E-Learning'),
        ('ecommerce', 'E-Commerce & Retail'),
        ('hospitality', 'Hospitality & Tourism'),
        ('real_estate', 'Real Estate & Construction'),
        ('manufacturing', 'Manufacturing & Production'),
        ('media', 'Media & Entertainment'),
        ('telecom', 'Telecommunications'),
        ('agriculture', 'Agriculture & Agribusiness'),
        ('nonprofit', 'Non-Profit & NGO'),
        ('consulting', 'Consulting & Professional Services'),
        ('other', 'Other'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='creative_contexts'
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='+'
    )
    company_name = models.CharField(max_length=255, blank=True)
    mission_statement = models.TextField(blank=True)
    goals = models.TextField(blank=True, help_text='Company goals and objectives')
    brand_voice = models.TextField(blank=True, help_text='Brand voice and personality guidelines')
    target_audience = models.TextField(blank=True, help_text='Primary target audience description')
    country = models.CharField(max_length=30, choices=COUNTRY_CHOICES, default='nepal')
    industry = models.CharField(max_length=100, blank=True, help_text='Industry sector')
    cultural_context = models.TextField(blank=True, help_text='Cultural nuances, local festivals, regional preferences')
    brand_theme = models.TextField(blank=True, help_text='Brand theme, color palette, visual style, and design direction')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Creative Context'
        verbose_name_plural = 'Creative Contexts'

    def __str__(self):
        return self.company_name or f"Context for {self.user.email}"

    def to_prompt_context(self):
        parts = []
        if self.company_name:
            parts.append(f"Company: {self.company_name}")
        if self.mission_statement:
            parts.append(f"Mission: {self.mission_statement}")
        if self.goals:
            parts.append(f"Goals & Objectives: {self.goals}")
        if self.brand_voice:
            parts.append(f"Brand Voice & Personality: {self.brand_voice}")
        if self.target_audience:
            parts.append(f"Target Audience: {self.target_audience}")
        if self.country:
            parts.append(f"Market/Country: {self.get_country_display()}")
        if self.industry:
            parts.append(f"Industry: {self.industry}")
        if self.brand_theme:
            parts.append(f"Brand Theme & Visual Style: {self.brand_theme}")
        return "\n".join(parts)


class CreativeStrategy(models.Model):
    objects = TenantManager()
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]
    STRATEGY_TYPES = [
        ('full_campaign', 'Full Campaign Strategy'),
        ('image_prompt', 'Image Generation Prompt'),
        ('logo_design', 'Logo Design Brief'),
        ('post_content', 'Social Media Post'),
        ('brand_identity', 'Brand Identity Guide'),
        ('content_calendar', 'Content Calendar'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='creative_strategies'
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='+'
    )
    strategy_type = models.CharField(max_length=30, choices=STRATEGY_TYPES, default='full_campaign')
    title = models.CharField(max_length=255, blank=True)
    campaign_goal = models.TextField()
    target_audience = models.TextField(blank=True)
    tone_of_voice = models.CharField(max_length=50, default='professional')
    generated_output = models.TextField(blank=True)
    llm_mode = models.CharField(max_length=50, blank=True, help_text='Which LLM provider was used')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    rejection_reason = models.TextField(blank=True, help_text='Reason for rejection')
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_strategies'
    )
    scheduled_platforms = models.JSONField(default=list, blank=True, help_text='Platforms to publish on')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Creative Strategy'
        verbose_name_plural = 'Creative Strategies'

    def __str__(self):
        return self.title or f"Strategy {self.id} — {self.campaign_goal[:60]}"


class CreativeStrategyAsset(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved for Use'),
        ('rejected', 'Rejected'),
    ]
    strategy = models.ForeignKey(CreativeStrategy, on_delete=models.CASCADE, related_name='linked_assets')
    asset = models.ForeignKey('media_assets.MediaAsset', on_delete=models.CASCADE, related_name='creative_strategies')
    context_notes = models.TextField(blank=True, help_text='User notes about this asset in relation to the strategy')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    platform = models.CharField(max_length=50, blank=True, help_text='Target platform for this asset (e.g. instagram, facebook)')
    scheduled_at = models.DateTimeField(null=True, blank=True, help_text='When to publish this asset')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ('strategy', 'asset')
        verbose_name = 'Strategy Asset Link'
        verbose_name_plural = 'Strategy Asset Links'

    def __str__(self):
        return f"{self.strategy} → {self.asset.original_filename}"
