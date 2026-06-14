import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ContentGenerateForm, ContentReviewForm
from .models import ContentGeneration, ContentVersion

logger = logging.getLogger(__name__)


@login_required
def content_dashboard(request):
    generations = ContentGeneration.objects.filter(user=request.user)
    total = generations.count()
    drafts = generations.filter(status='draft').count()
    approved = generations.filter(status='approved').count()
    favorites = generations.filter(is_favorite=True).count()

    recent = generations.order_by('-created_at')[:5]

    return render(request, 'content/dashboard.html', {
        'total': total,
        'drafts': drafts,
        'approved': approved,
        'favorites': favorites,
        'recent': recent,
    })


@login_required
def content_generate(request):
    if request.method == 'POST':
        form = ContentGenerateForm(request.POST)
        if form.is_valid():
            gen_type = form.cleaned_data['generation_type']
            platform = form.cleaned_data['platform']
            topic = form.cleaned_data['topic']
            keywords = form.cleaned_data['keywords']
            tone = form.cleaned_data['tone']
            length = form.cleaned_data['length']
            include_h = form.cleaned_data['include_hashtags']

            prompt = _build_prompt(gen_type, platform, topic, keywords, tone, length, include_h)

            generation = ContentGeneration.objects.create(
                user=request.user,
                generation_type=gen_type.split('_')[0] if '_' in gen_type else gen_type.split('—')[0].strip(),
                platform=platform,
                input_context=topic,
                raw_prompt=prompt,
                generated_content=_mock_generate(gen_type, topic, platform, tone),
            )

            ContentVersion.objects.create(
                generation=generation,
                content=generation.generated_content,
                notes='Initial AI generation',
            )

            messages.success(request, 'Content generated! Review and approve below.')
            return redirect('content:edit', pk=generation.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ContentGenerateForm()

    return render(request, 'content/generate.html', {
        'form': form,
    })


@login_required
def content_history(request):
    gen_type = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')

    items = ContentGeneration.objects.filter(user=request.user)
    if gen_type:
        items = items.filter(generation_type=gen_type)
    if status_filter:
        items = items.filter(status=status_filter)

    filter_types = ContentGeneration.GENERATION_TYPES

    return render(request, 'content/history.html', {
        'items': items,
        'current_type': gen_type,
        'current_status': status_filter,
        'filter_types': filter_types,
    })


@login_required
def content_detail(request, pk):
    item = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    versions = item.versions.all()
    return render(request, 'content/detail.html', {
        'item': item,
        'versions': versions,
    })


@login_required
def content_edit(request, pk):
    item = get_object_or_404(ContentGeneration, pk=pk, user=request.user)

    if request.method == 'POST':
        form = ContentReviewForm(request.POST, instance=item)
        if form.is_valid():
            edited = form.save()
            # Save a version snapshot on edit
            ContentVersion.objects.create(
                generation=edited,
                content=edited.generated_content,
                notes='Manual edit',
            )
            messages.success(request, 'Content updated.')
            return redirect('content:detail', pk=item.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ContentReviewForm(instance=item)

    return render(request, 'content/edit.html', {
        'form': form,
        'item': item,
    })


@login_required
def content_approve(request, pk):
    item = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    item.status = 'approved'
    item.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Content approved.')
    return redirect('content:detail', pk=item.pk)


@login_required
def content_delete(request, pk):
    item = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    item.delete()
    messages.success(request, 'Content deleted.')
    return redirect('content:history')


@login_required
def content_favorite(request, pk):
    item = get_object_or_404(ContentGeneration, pk=pk, user=request.user)
    item.is_favorite = not item.is_favorite
    item.save(update_fields=['is_favorite', 'updated_at'])
    return redirect('content:detail', pk=item.pk)


# ---- Helpers ----

def _build_prompt(gen_type, platform, topic, keywords, tone, length, include_hashtags):
    parts = [f"Write a {tone} {length} {gen_type.split('—')[0].strip()} for {platform} about: {topic}"]
    if keywords:
        parts.append(f"Include these keywords: {keywords}")
    if include_hashtags:
        parts.append("Include relevant hashtags at the end.")
    parts.append(f"\n\nFormat the output cleanly without extra explanation.")
    return '\n'.join(parts)


def _mock_generate(gen_type, topic, platform, tone):
    """Placeholder generation — replace with actual AI API call."""
    platform_label = dict(ContentGeneration.PLATFORM_CHOICES).get(platform, platform)
    type_label = gen_type.split('—')[0].strip() if '—' in gen_type else gen_type.replace('_', ' ').title()

    preview_map = {
        'caption': f"Exciting news! 🚀\n\n{topic.title()} is here and we couldn't be more thrilled. This is going to change everything you thought you knew.\n\nTag someone who needs to see this! 👇\n\n#gamechanger #innovation #{platform_label.lower().replace(' ', '')}",
        'hashtags': f"#{topic.replace(' ', '').title()} #{platform_label}Tips #TrendingNow #MustRead #GoViral #ContentCreator #DigitalMarketing #GrowthHacks #ViralContent #Explore #FYP",
        'carousel': f"**Slide 1:** Hook title about {topic}\n**Slide 2:** The problem statement\n**Slide 3:** Key insight #1\n**Slide 4:** Key insight #2\n**Slide 5:** Key insight #3\n**Slide 6:** CTA — Save this post for later!",
        'video_script': f"[0:00-0:05] Hook: \"Stop scrolling! This one tip about {topic} will save you hours.\"\n[0:05-0:20] The problem most people face\n[0:20-0:45] Step-by-step solution\n[0:45-0:55] Real results example\n[0:55-1:00] CTA: Follow for more!",
        'image_prompt': f"A visually stunning {tone} scene depicting {topic}, digital art style, vibrant colors, 4K, dramatic lighting, --ar 16:9 --v 6",
        'cta': f"Ready to level up your {topic} game?\n\n👉 Click the link in bio\n💬 Comment 'YES' for more tips\n🔔 Turn on notifications\n\nDon't miss out on this game-changing opportunity!",
    }

    return preview_map.get(gen_type.split('_')[0], f"Generated {type_label} about {topic} for {platform_label}.")
