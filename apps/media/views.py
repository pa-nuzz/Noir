import logging
import mimetypes
import os

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.utils import timezone

from .forms import MediaFolderForm, MediaUploadForm
from .models import MediaAsset, MediaFolder
from apps.workspaces.query_helpers import filter_by_context
from apps.workspaces.decorators import require_workspace_permission

logger = logging.getLogger(__name__)


@login_required
def media_library(request):
    folder_id = request.GET.get('folder', '')
    file_type = request.GET.get('type', '')

    assets = filter_by_context(request, MediaAsset.objects.all()).select_related('folder')
    if folder_id:
        assets = assets.filter(folder_id=folder_id)
    if file_type:
        assets = assets.filter(file_type=file_type)

    folders = filter_by_context(request, MediaFolder.objects.all())
    root_assets = MediaAsset.objects.filter(user=request.user, folder__isnull=True)

    return render(request, 'media/library.html', {
        'assets': assets,
        'folders': folders,
        'root_assets': root_assets,
        'current_folder': folder_id,
        'current_type': file_type,
    })


@login_required
@require_workspace_permission('media', 'create')
def media_upload(request):
    if request.method == 'POST':
        form = MediaUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            asset = form.save(commit=False)
            asset.user = request.user
            uploaded = request.FILES['file']
            asset.filename = uploaded.name
            asset.file_size = uploaded.size
            asset.mime_type = uploaded.content_type or mimetypes.guess_type(uploaded.name)[0] or 'application/octet-stream'
            asset.file_type = _detect_file_type(asset.mime_type, asset.filename)
            asset.save()

            messages.success(request, f'"{asset.filename}" uploaded successfully.')
            return redirect('media:library')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = MediaUploadForm(user=request.user)

    return render(request, 'media/upload.html', {'form': form})


@login_required
def media_detail(request, pk):
    asset = get_object_or_404(filter_by_context(request, MediaAsset.objects.all()), pk=pk)
    return render(request, 'media/detail.html', {'asset': asset})


@login_required
@require_workspace_permission('media', 'delete')
def media_delete(request, pk):
    asset = get_object_or_404(filter_by_context(request, MediaAsset.objects.all()), pk=pk)
    filename = asset.filename
    if asset.file:
        asset.file.delete(save=False)
    if asset.thumbnail:
        asset.thumbnail.delete(save=False)
    asset.delete()
    messages.success(request, f'"{filename}" deleted.')
    return redirect('media:library')


@login_required
@require_workspace_permission('media', 'edit')
def media_optimize(request, pk):
    """Placeholder: trigger image optimization (resize, compress, WebP)."""
    asset = get_object_or_404(filter_by_context(request, MediaAsset.objects.all()), pk=pk)
    if asset.file_type != 'image':
        messages.warning(request, 'Optimization is only available for images.')
        return redirect('media:detail', pk=asset.pk)
    # TODO: integrate Pillow / cloud image processing
    asset.is_optimized = True
    asset.save(update_fields=['is_optimized', 'updated_at'])
    messages.success(request, f'"{asset.filename}" optimized (placeholder).')
    return redirect('media:detail', pk=asset.pk)


@login_required
@require_workspace_permission('media', 'edit')
def media_auto_tag(request, pk):
    """Placeholder: run AI auto-tagging on the asset."""
    asset = get_object_or_404(filter_by_context(request, MediaAsset.objects.all()), pk=pk)
    # TODO: integrate AI vision API (OpenAI Vision, AWS Rekognition, etc.)
    asset.ai_tags = _mock_auto_tags(asset.filename)
    asset.ai_description = _mock_description(asset.filename)
    asset.save(update_fields=['ai_tags', 'ai_description', 'updated_at'])
    messages.success(request, f'Auto-tagging complete for "{asset.filename}".')
    return redirect('media:detail', pk=asset.pk)


@login_required
def folder_list(request):
    folders = filter_by_context(request, MediaFolder.objects.all()).select_related('parent')
    return render(request, 'media/folder_list.html', {'folders': folders})


@login_required
@require_workspace_permission('media', 'create')
def folder_create(request):
    if request.method == 'POST':
        form = MediaFolderForm(request.POST, user=request.user)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.user = request.user
            folder.name_slug = slugify(folder.name)
            folder.save()
            messages.success(request, f'Folder "{folder.name}" created.')
            return redirect('media:folder_list')
        else:
            messages.error(request, 'Please correct the errors.')
    else:
        form = MediaFolderForm(user=request.user)

    return render(request, 'media/folder_form.html', {'form': form})


@login_required
def folder_detail(request, pk):
    folder = get_object_or_404(filter_by_context(request, MediaFolder.objects.all()), pk=pk)
    assets = MediaAsset.objects.filter(user=request.user, folder=folder)
    subfolders = MediaFolder.objects.filter(user=request.user, parent=folder)
    return render(request, 'media/folder_detail.html', {
        'folder': folder,
        'assets': assets,
        'subfolders': subfolders,
    })


@login_required
@require_workspace_permission('media', 'delete')
def folder_delete(request, pk):
    folder = get_object_or_404(filter_by_context(request, MediaFolder.objects.all()), pk=pk)
    name = folder.name
    folder.delete()
    messages.success(request, f'Folder "{name}" deleted.')
    return redirect('media:folder_list')


@login_required
def media_search(request):
    q = request.GET.get('q', '')
    results = MediaAsset.objects.none()
    if q:
        results = filter_by_context(request, MediaAsset.objects.all()).filter(
            Q(filename__icontains=q) |
            Q(ai_tags__icontains=q) |
            Q(ai_description__icontains=q) |
            Q(alt_text__icontains=q),
        ).select_related('folder')

    return render(request, 'media/search.html', {
        'query': q,
        'results': results,
    })


# ---- Helpers ----

def _detect_file_type(mime, filename):
    ext = os.path.splitext(filename)[1].lower()
    image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.tiff', '.ico'}
    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.wmv', '.flv'}
    doc_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.md'}
    audio_exts = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a'}

    if ext in image_exts or (mime or '').startswith('image/'):
        return 'image'
    if ext in video_exts or (mime or '').startswith('video/'):
        return 'video'
    if ext in doc_exts:
        return 'document'
    if ext in audio_exts or (mime or '').startswith('audio/'):
        return 'audio'
    return 'other'


def _mock_auto_tags(filename):
    ext = os.path.splitext(filename)[1].lower()
    name = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').title()
    return [name, 'asset', ext.lstrip('.'), 'uploaded']


def _mock_description(filename):
    return f"AI-generated description for '{filename}'. This asset appears to contain visual media."
