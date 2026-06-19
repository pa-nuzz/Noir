import json
import logging
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.media_assets.models import MediaAsset, MediaFolder
from apps.media_assets.services import MediaService

from .services.creative_service import CreativeServiceError, generate_creative_content
from .services.schemas import get_strategy_schema, get_all_strategy_schemas

from .models import CreativeContext, CreativeStrategy, CreativeStrategyAsset

logger = logging.getLogger(__name__)


def _strategies_qs(user, ws_id, status=None):
    qs = CreativeStrategy.objects.filter(user=user)
    if ws_id:
        qs = qs.filter(workspace_id=ws_id)
    else:
        qs = qs.filter(workspace__isnull=True)
    if status:
        qs = qs.filter(status=status)
    return qs


def _attach_asset_urls(assets, request):
    service = MediaService(request.user)
    for a in assets:
        a.display_url = service.get_asset_url(a)
        a.display_thumbnail_url = service.get_thumbnail_url(a) or a.display_url
    return list(assets)


def _get_workspace_context(request):
    context = CreativeContext.objects.filter(
        user=request.user,
        workspace=request.session.get('active_workspace_id'),
    ).first()
    if not context:
        context = CreativeContext.objects.filter(
            user=request.user,
            workspace__isnull=True,
        ).first()
    return context


def _build_folder_tree(user, parent=None, _connectors=None):
    if _connectors is None:
        _connectors = []
    folders = list(MediaFolder.objects.filter(parent=parent, user=user).order_by('name'))
    tree = []
    for idx, f in enumerate(folders):
        is_last = idx == len(folders) - 1
        children_count = MediaAsset.objects.filter(folder=f, user=user).count()
        child_connectors = _connectors + [not is_last]
        tree.append({
            'id': f.id,
            'name': f.name,
            'asset_count': children_count,
            'children': _build_folder_tree(user, f, child_connectors),
            'has_children': False,
            'is_last': is_last,
            'connectors': _connectors,
        })
    for item in tree:
        item['has_children'] = len(item['children']) > 0
    return tree


# ---------------------------------------------------------------------------
# Media Library — File Explorer with Folder Tree + Asset Grid + Drag Preview
# ---------------------------------------------------------------------------

@login_required
def media_library(request):
    user = request.user
    file_type = request.GET.get('type', '')
    folder_id = request.GET.get('folder', '')
    query = request.GET.get('q', '').strip()

    # Handle folder CRUD via POST
    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'create_folder':
            name = request.POST.get('name', '').strip()
            parent_id = request.POST.get('parent_id', '')
            if name:
                parent = None
                if parent_id and parent_id.isdigit():
                    parent = get_object_or_404(MediaFolder, id=int(parent_id), user=user)
                MediaFolder.objects.get_or_create(
                    name=name, parent=parent, user=user,
                    defaults={'workspace_id': request.session.get('active_workspace_id')},
                )
                messages.success(request, f'Folder "{name}" created.')
            return redirect('creative:media_library')

        if action == 'delete_folder':
            fid = request.POST.get('folder_id', '')
            if fid and fid.isdigit():
                folder = get_object_or_404(MediaFolder, id=int(fid), user=user)
                folder.delete()
                messages.success(request, 'Folder deleted.')
            return redirect('creative:media_library')

        if action == 'rename_folder':
            fid = request.POST.get('folder_id', '')
            name = request.POST.get('name', '').strip()
            if fid and fid.isdigit() and name:
                folder = get_object_or_404(MediaFolder, id=int(fid), user=user)
                folder.name = name
                folder.save()
                messages.success(request, 'Folder renamed.')
            return redirect('creative:media_library')

        if action == 'save_context_notes':
            asset_id = request.POST.get('asset_id', '')
            notes = request.POST.get('context_notes', '').strip()
            if asset_id and asset_id.isdigit():
                asset = get_object_or_404(MediaAsset, id=int(asset_id), user=user)
                asset.description = notes
                asset.save(update_fields=['description'])
                messages.success(request, 'Notes saved.')
            return redirect(request.path + '?selected=' + asset_id)

        if action == 'delete_asset':
            asset_id = request.POST.get('asset_id', '')
            if asset_id and asset_id.isdigit():
                svc = MediaService(user)
                svc.delete_asset(int(asset_id))
                messages.success(request, 'Asset deleted.')
            return redirect('creative:media_library')

        if action == 'schedule_asset':
            asset_id = request.POST.get('asset_id', '')
            platform = request.POST.get('platform', '').strip()
            scheduled_raw = request.POST.get('scheduled_at', '').strip()
            strategy_id = request.POST.get('strategy_id', '')
            if asset_id and asset_id.isdigit() and platform and scheduled_raw:
                try:
                    parsed = datetime.fromisoformat(scheduled_raw)
                    if timezone.is_naive(parsed):
                        parsed = timezone.make_aware(parsed)
                    asset = MediaAsset.objects.get(id=int(asset_id), user=user)
                    link = CreativeStrategyAsset.objects.filter(asset=asset).first()
                    if link:
                        link.platform = platform
                        link.scheduled_at = parsed
                        link.save()
                    if strategy_id and strategy_id.isdigit():
                        strategy = CreativeStrategy.objects.get(id=int(strategy_id), user=user)
                        CreativeStrategyAsset.objects.get_or_create(
                            strategy=strategy, asset=asset,
                            defaults={'platform': platform, 'scheduled_at': parsed},
                        )
                    messages.success(request, f'Asset scheduled on {platform}.')
                except (ValueError, TypeError):
                    messages.error(request, 'Invalid date format.')
            return redirect('creative:media_library')

    # GET — build folder tree + assets
    folder_tree = _build_folder_tree(user)
    all_folders = MediaFolder.objects.filter(user=user)
    assets = MediaAsset.objects.filter(user=user).select_related('folder').order_by('-created_at')

    if query:
        service = MediaService(user)
        assets = service.search_assets(query)
    if file_type:
        assets = assets.filter(file_type=file_type)
    if folder_id and folder_id.isdigit():
        assets = assets.filter(folder_id=int(folder_id))

    assets_total_count = assets.count()
    page_obj = None
    assets_is_limited = False
    if not query and not file_type and not folder_id:
        assets = assets.filter(file_type='image')
        assets_total_count = assets.count()
        assets = assets[:20]
        assets_is_limited = True
    elif folder_id and folder_id.isdigit():
        paginator = Paginator(assets, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        assets = page_obj.object_list

    selected_asset = None
    selected_id = request.GET.get('selected', '')
    if selected_id and selected_id.isdigit():
        from contextlib import suppress
        with suppress(MediaAsset.DoesNotExist):
            selected_asset = MediaAsset.objects.get(id=int(selected_id), user=user)

    assets = _attach_asset_urls(assets, request)

    if selected_asset:
        svc = MediaService(user)
        selected_asset.display_url = svc.get_asset_url(selected_asset)
        selected_asset.display_thumbnail_url = svc.get_thumbnail_url(selected_asset)

    return render(request, 'creative/media_library.html', {
        'assets': assets,
        'assets_total_count': assets_total_count,
        'assets_is_limited': assets_is_limited,
        'page_obj': page_obj,
        'folders': all_folders,
        'folder_tree': folder_tree,
        'selected_asset': selected_asset,
        'current_type': file_type,
        'current_folder': folder_id,
        'query': query,
        'strategies': CreativeStrategy.objects.filter(
            user=user, status__in=['approved', 'active'],
        ).order_by('-created_at')[:20],
    })


# ---------------------------------------------------------------------------
# Strategy Studio — Generate + Approve/Reject/Draft workflow
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATES = {
    'full_campaign': (
        "Generate a comprehensive marketing campaign strategy. "
        "Include:\n"
        "1. Campaign Overview & SMART Objectives\n"
        "2. Key Messaging & Value Proposition\n"
        "3. Channel Mix: Email, Social Media (Facebook, Instagram, LinkedIn, TikTok), Content Marketing\n"
        "4. Content Pillars & Theme Ideas\n"
        "5. Creative Concepts (visual direction, taglines, hooks)\n"
        "6. Success Metrics & KPIs\n"
        "7. 30-60-90 Day Timeline & Milestones\n"
        "8. Budget Allocation Recommendations\n"
        "9. Risk Mitigation & Contingency Plans\n\n"
        "Make it actionable, specific, and tailored to the Nepal/South Asian market where relevant."
    ),
    'image_prompt': (
        "Generate a detailed, production-ready AI image generation prompt. "
        "The prompt must include:\n"
        "1. Subject description (pose, expression, styling)\n"
        "2. Environment & Background\n"
        "3. Lighting, Color Palette, Mood\n"
        "4. Camera angle, lens, composition style\n"
        "5. Art style (photorealistic, minimalist, cinematic, illustration, 3D render)\n"
        "6. Aspect ratio and technical specifications\n\n"
        "Format as a single cohesive prompt string that can be copy-pasted into Midjourney, DALL-E, or Stable Diffusion. "
        "Also include 3 alternative style variations."
    ),
    'logo_design': (
        "Generate a comprehensive logo design brief. Include:\n"
        "1. Logo Style Recommendation (wordmark, lettermark, emblem, abstract, mascot)\n"
        "2. Color Palette with hex codes (primary, secondary, accent)\n"
        "3. Typography recommendations (font families, weights)\n"
        "4. Visual metaphors and symbolic elements\n"
        "5. Application variations (horizontal, vertical, icon-only, monochrome)\n"
        "6. Mood board description\n"
        "7. 3 distinct logo concepts with detailed descriptions\n\n"
        "Focus on modern, scalable designs suitable for digital and print."
    ),
    'post_content': (
        "Write platform-native social media posts for the target platforms listed above. "
        "Each platform gets its own post with platform-appropriate hook, body, CTA, hashtags, "
        "visual description, best posting time, and engagement tactic."
    ),
    'social_post': (
        "Write platform-native social media posts for the target platforms listed above. "
        "Each platform gets its own post with platform-appropriate hook, body, CTA, hashtags, "
        "visual description, best posting time, and engagement tactic."
    ),
    'brand_identity': (
        "Create a complete brand identity guide. Include:\n"
        "1. Brand Essence & Core Values\n"
        "2. Brand Personality (5-7 traits)\n"
        "3. Visual Identity Guidelines (logo usage, color system, typography, imagery style)\n"
        "4. Tone of Voice Guidelines (with examples for different contexts)\n"
        "5. Brand Story & Narrative\n"
        "6. Customer Touchpoints & Experience Principles\n"
        "7. Competitor Positioning & Differentiation\n\n"
        "Make it comprehensive enough for a design agency to execute."
    ),
    'content_calendar': (
        "Create a 30-day content calendar strategy. Include:\n"
        "1. Weekly themes (4 weeks)\n"
        "2. Daily content breakdown (post type, topic, platform)\n"
        "3. Special days / festivals to leverage (including Nepali festivals)\n"
        "4. Content format mix (video, image, carousel, text, story)\n"
        "5. Engagement tactics per post\n"
        "6. Cross-platform repurposing suggestions\n"
        "7. Key dates & deadlines for production\n\n"
        "Structure as a table/calendar format."
    ),
}


@login_required
def strategy_detail(request, strategy_id):
    strategy = get_object_or_404(CreativeStrategy, id=strategy_id, user=request.user)
    return render(request, 'creative/strategy_detail.html', {
        'strategy': strategy,
    })


@login_required
def strategy_studio(request):
    user = request.user
    ws_id = request.session.get('active_workspace_id')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'update_status':
            sid = request.POST.get('strategy_id', '')
            new_status = request.POST.get('status', '')
            reason = request.POST.get('rejection_reason', '').strip()
            if sid and sid.isdigit() and new_status:
                strategy = get_object_or_404(CreativeStrategy, id=int(sid), user=user)
                valid_statuses = [s[0] for s in CreativeStrategy.STATUS_CHOICES]
                if new_status not in valid_statuses:
                    messages.error(request, f'Invalid status: {new_status}')
                    return redirect('creative:strategy_studio')
                strategy.status = new_status
                if new_status == 'rejected':
                    strategy.rejection_reason = reason
                if new_status == 'approved':
                    strategy.approved_by = user
                if new_status == 'published':
                    strategy.published_at = timezone.now()
                strategy.save()
                messages.success(request, f'Status updated to {strategy.get_status_display()}.')
            return redirect(f'{request.path}?strategy={sid}')

        if action == 'delete_strategy':
            sid = request.POST.get('strategy_id', '')
            if sid and sid.isdigit():
                get_object_or_404(CreativeStrategy, id=int(sid), user=user).delete()
                messages.success(request, 'Strategy deleted.')
            return redirect('creative:strategy_studio')

    # GET
    selected_strategy = None
    strategy_id = request.GET.get('strategy', '')
    current_status = request.GET.get('status', '')
    strategies = _strategies_qs(user, ws_id)
    if current_status:
        strategies = strategies.filter(status=current_status)
    strategies = strategies.order_by('-created_at')

    paginator = Paginator(strategies, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    if strategy_id and strategy_id.isdigit():
        selected_strategy = get_object_or_404(CreativeStrategy, id=int(strategy_id), user=user)

    status_keys = ['draft', 'pending_review', 'approved', 'rejected', 'published', 'archived']
    strategy_counts = {s: _strategies_qs(user, ws_id, s).count() for s in status_keys}
    strategy_counts['all'] = _strategies_qs(user, ws_id).count()

    context_obj = _get_workspace_context(request)

    return render(request, 'creative/strategy_studio.html', {
        'strategies': page_obj.object_list,
        'page_obj': page_obj,
        'selected_strategy': selected_strategy,
        'strategy_counts': strategy_counts,
        'current_status': current_status,
        'has_context': context_obj is not None,
        'company_name': context_obj.company_name if context_obj else '',
        'strategy_types': CreativeStrategy.STRATEGY_TYPES,
        'strategy_types_json': json.dumps(list(CreativeStrategy.STRATEGY_TYPES)),
        'status_choices': CreativeStrategy.STATUS_CHOICES,
        'platforms': ['facebook', 'instagram', 'linkedin', 'twitter', 'tiktok', 'youtube'],
    })


# ---------------------------------------------------------------------------
# Company Context
# ---------------------------------------------------------------------------

@login_required
def company_context(request):
    ws_id = request.session.get('active_workspace_id')
    kwargs = {'user': request.user}
    if ws_id:
        kwargs['workspace_id'] = ws_id
    else:
        kwargs['workspace__isnull'] = True

    context_obj = CreativeContext.objects.filter(**kwargs).first()

    if request.method == 'POST':
        company_name = request.POST.get('company_name', '').strip()
        mission_statement = request.POST.get('mission_statement', '').strip()
        goals = request.POST.get('goals', '').strip()
        brand_voice = request.POST.get('brand_voice', '').strip()
        target_audience = request.POST.get('target_audience', '').strip()
        country = request.POST.get('country', 'nepal').strip()
        industry = request.POST.get('industry', '').strip()
        cultural_context = request.POST.get('cultural_context', '').strip()
        brand_theme = request.POST.get('brand_theme', '').strip()

        data = {
            'company_name': company_name,
            'mission_statement': mission_statement,
            'goals': goals,
            'brand_voice': brand_voice,
            'target_audience': target_audience,
            'country': country,
            'industry': industry,
            'cultural_context': cultural_context,
            'brand_theme': brand_theme,
        }

        if context_obj:
            for k, v in data.items():
                setattr(context_obj, k, v)
            context_obj.save()
            messages.success(request, 'Company context updated.')
        else:
            CreativeContext.objects.create(user=request.user, workspace_id=ws_id, **data)
            messages.success(request, 'Company context saved.')

        return redirect('creative:company_context')

    return render(request, 'creative/company_context.html', {
        'context': context_obj,
        'countries': CreativeContext.COUNTRY_CHOICES,
        'industries': CreativeContext.INDUSTRY_CHOICES,
    })


# ---------------------------------------------------------------------------
# AJAX API Endpoints
# ---------------------------------------------------------------------------

@login_required
def api_assets_json(request):
    assets = MediaAsset.objects.filter(user=request.user).select_related('folder').order_by('-created_at')[:100]
    data = []
    for a in assets:
        data.append({
            'id': a.id,
            'title': a.title or a.original_filename,
            'original_filename': a.original_filename,
            'file_type': a.file_type,
            'file_size': a.file_size,
            'folder': a.folder.name if a.folder else None,
            'folder_id': a.folder_id,
            'created_at': a.created_at.isoformat(),
        })
    return JsonResponse({'assets': data})


@login_required
def api_folder_tree(request):
    tree = _build_folder_tree(request.user)
    return JsonResponse({'tree': tree})


@login_required
def api_update_asset_status(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    asset_id = data.get('asset_id')
    platform = data.get('platform', '')
    scheduled_at = data.get('scheduled_at')
    notes = data.get('context_notes', '')

    if not asset_id:
        return JsonResponse({'error': 'asset_id required'}, status=400)

    from contextlib import suppress
    with suppress(MediaAsset.DoesNotExist):
        asset = MediaAsset.objects.get(id=int(asset_id), user=request.user)
        link, _ = CreativeStrategyAsset.objects.get_or_create(
            asset=asset,
            defaults={'user': request.user, 'strategy': None},
        )
        if platform:
            link.platform = platform
        if scheduled_at:
            try:
                link.scheduled_at = datetime.fromisoformat(scheduled_at)
            except (ValueError, TypeError):
                pass
        if notes:
            link.context_notes = notes
        link.save()
        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Asset not found'}, status=404)


@login_required
def api_strategy_status(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    strategy_id = data.get('strategy_id')
    new_status = data.get('status', '')
    reason = data.get('rejection_reason', '')

    if not strategy_id or not new_status:
        return JsonResponse({'error': 'strategy_id and status required'}, status=400)

    strategy = get_object_or_404(CreativeStrategy, id=int(strategy_id), user=request.user)
    valid_statuses = [s[0] for s in CreativeStrategy.STATUS_CHOICES]
    if new_status not in valid_statuses:
        return JsonResponse({'error': f'Invalid status: {new_status}'}, status=400)

    strategy.status = new_status
    if new_status == 'rejected':
        strategy.rejection_reason = reason
    if new_status == 'approved':
        strategy.approved_by = request.user
    if new_status == 'published':
        strategy.published_at = timezone.now()
    strategy.save()
    return JsonResponse({
        'success': True,
        'status': new_status,
        'status_label': dict(CreativeStrategy.STATUS_CHOICES).get(new_status),
    })


# ---------------------------------------------------------------------------
# Chatbot Strategy Generation API
# ---------------------------------------------------------------------------

@csrf_exempt
@login_required
def api_chat_generate(request):
    """Accepts collected chat data, generates strategy via LLM, saves as draft.
    
    Handles dynamic input fields based on the strategy type's schema.
    Maps known fields to model columns; stores extras in metadata JSONField.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user = request.user
    ws_id = request.session.get('active_workspace_id')
    strategy_type = data.get('strategy_type', 'full_campaign')
    title = data.get('title', '').strip()
    scheduled_raw = data.get('scheduled_at', '').strip()

    if not title:
        return JsonResponse({'error': 'Title is required'}, status=400)

    context_obj = _get_workspace_context(request)

    # ── Load schema for this strategy type ─────────────────────────────────
    schema = get_strategy_schema(strategy_type)

    # ── Extract common fields from dynamic payload ──────────────────────────
    # Map known field keys to model/context fields
    FIELD_MAP = {
        'title': 'title',
        'goals': 'campaign_goal',
        'description': 'campaign_goal',
        'target_audience': 'target_audience',
        'audience': 'target_audience',
        'tone': 'tone_of_voice',
        'platforms': 'scheduled_platforms',
    }

    # Extract mapped fields
    mapped = {}
    for data_key, model_field in FIELD_MAP.items():
        if data_key in data:
            mapped[model_field] = data[data_key]

    campaign_goal = mapped.get('campaign_goal', title)
    target_audience = mapped.get('target_audience', '')
    tone = mapped.get('tone_of_voice', 'professional')
    platforms = mapped.get('scheduled_platforms', [])

    if isinstance(tone, list):
        tone = tone[0] if tone else 'professional'
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.split(',') if p.strip()]

    # ── Build company_context ──────────────────────────────────────────────
    company_context = {
        "name": context_obj.company_name if context_obj else title,
        "industry": context_obj.industry if context_obj else "",
        "product": context_obj.company_name if context_obj else title,
        "audience": target_audience or (context_obj.target_audience if context_obj else ""),
        "tone": tone or (context_obj.brand_voice if context_obj else "professional"),
        "mission": context_obj.mission_statement if context_obj else "",
        "uvp": context_obj.goals if context_obj else "",
        "platforms": platforms,
    }

    # Include extra strategy-specific fields in company context
    if schema:
        schema_keys = {step['key'] for step in schema.get('steps', [])}
        STANDARD_CTX_KEYS = {'title', 'goals', 'description', 'target_audience',
                             'audience', 'tone', 'platforms', 'scheduled_at',
                             'strategy_type'}
        extra_keys = schema_keys - STANDARD_CTX_KEYS
        for key in extra_keys:
            val = data.get(key)
            if val:
                company_context[key] = val

    # ── Build user_input dynamically from schema ──────────────────────────
    prompt_lines = [
        f"STRATEGY TYPE: {dict(CreativeStrategy.STRATEGY_TYPES).get(strategy_type, 'Full Campaign')}",
        f"Title: {title}",
    ]

    if schema:
        for step in schema.get('steps', []):
            key = step['key']
            if key in ('title', 'scheduled_at', 'strategy_type'):
                continue
            val = data.get(key, '')
            if isinstance(val, list):
                val = ', '.join(v for v in val if v)
            if val:
                prompt_lines.append(f"{step['label']}: {val}")
    else:
        # Fallback for unknown types
        for k, v in data.items():
            if k not in ('strategy_type', 'title', 'csrfmiddlewaretoken', 'scheduled_at'):
                if isinstance(v, list):
                    v = ', '.join(str(x) for x in v if x)
                if v:
                    prompt_lines.append(f"{k.replace('_', ' ').title()}: {v}")

    # Add the static prompt template section
    template_key = strategy_type if strategy_type in _PROMPT_TEMPLATES else 'full_campaign'
    strategy_prompt_section = _PROMPT_TEMPLATES[template_key]
    prompt_lines.append("")
    prompt_lines.append("BRIEF:")
    prompt_lines.append(strategy_prompt_section)

    user_input = "\n".join(prompt_lines)

    # For platform-specific categories, emphasize which platforms to target
    if strategy_type in ('post_content', 'social_post') and platforms:
        platform_labels = {
            'facebook': 'Facebook', 'instagram': 'Instagram', 'linkedin': 'LinkedIn',
            'twitter': 'X (Twitter)', 'tiktok': 'TikTok', 'youtube': 'YouTube',
        }
        label_list = ', '.join(platform_labels.get(p, p.title()) for p in platforms)
        user_input += (
            f"\n\nCRITICAL: Generate posts ONLY for these platforms: {label_list}.\n"
            f"Do NOT generate posts for any other platforms."
        )

    try:
        result = generate_creative_content(user_input, company_context, category=strategy_type)
        generated = json.dumps(result)
        full_title = result.get('title', title)
        llm_mode = 'creative_service'
    except CreativeServiceError as e:
        logger.exception("Creative service strategy generation failed")
        return JsonResponse({'error': str(e)}, status=502)
    except Exception as e:
        logger.exception("Strategy generation failed")
        return JsonResponse({'error': f'Generation failed: {e}'}, status=500)

    if not generated:
        return JsonResponse({'error': 'Creative generation returned empty output. Check API keys.'}, status=502)

    # ── Parse scheduled_at ─────────────────────────────────────────────────
    scheduled_at = None
    if scheduled_raw:
        try:
            parsed = datetime.fromisoformat(scheduled_raw)
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            scheduled_at = parsed
        except (ValueError, TypeError):
            pass

    # ── Build metadata from fields not mapped to model columns ─────────────
    mapped_data_keys = set(FIELD_MAP.keys()) | {'strategy_type', 'scheduled_at', 'csrfmiddlewaretoken'}
    metadata = {}
    for k, v in data.items():
        if k not in mapped_data_keys:
            if isinstance(v, list):
                v = [x for x in v if x]
            if v:
                metadata[k] = v

    strategy = CreativeStrategy.objects.create(
        user=user,
        workspace_id=ws_id,
        strategy_type=strategy_type,
        title=full_title,
        campaign_goal=campaign_goal if isinstance(campaign_goal, str) else full_title,
        target_audience=target_audience if isinstance(target_audience, str) else '',
        tone_of_voice=tone if isinstance(tone, str) else 'professional',
        generated_output=generated,
        scheduled_platforms=platforms if isinstance(platforms, list) else [],
        scheduled_at=scheduled_at,
        metadata=metadata,
        llm_mode=llm_mode,
        status='draft',
    )

    return JsonResponse({
        'success': True,
        'strategy_id': strategy.id,
        'title': strategy.title,
        'status': strategy.status,
        'strategy_type': strategy.get_strategy_type_display(),
        'generated_output': strategy.generated_output,
        'created_at': strategy.created_at.isoformat(),
        'message': f'{strategy.get_strategy_type_display()} generated as draft!',
    })


# ---------------------------------------------------------------------------
# API: Update strategy (edit title / description)
# ---------------------------------------------------------------------------

@csrf_exempt
@login_required
def api_strategy_update(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    sid = data.get('strategy_id')
    if not sid:
        return JsonResponse({'error': 'strategy_id required'}, status=400)

    strategy = get_object_or_404(CreativeStrategy, id=int(sid), user=request.user)

    if 'title' in data:
        strategy.title = data['title'].strip()
    if 'campaign_goal' in data:
        strategy.campaign_goal = data['campaign_goal'].strip()
    if 'target_audience' in data:
        strategy.target_audience = data['target_audience'].strip()
    strategy.save()

    return JsonResponse({'success': True, 'title': strategy.title})


@login_required
def api_strategy_inputs(request, strategy_type=None):
    """Return the input schema for a strategy type, or all schemas if no type given."""
    if strategy_type:
        schema = get_strategy_schema(strategy_type)
        if not schema:
            return JsonResponse({'error': f'Unknown strategy type: {strategy_type}'}, status=404)
        return JsonResponse({'schema': schema, 'strategy_type': strategy_type})
    schemas = get_all_strategy_schemas()
    return JsonResponse({'schemas': schemas})
