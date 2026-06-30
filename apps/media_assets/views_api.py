import logging
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import MediaAsset, MediaFolder, MediaTag
from .services import MediaService, StorageService
from apps.workspaces.models import get_or_create_personal_workspace

logger = logging.getLogger(__name__)


def _attach_urls(assets, service):
    asset_list = list(assets)
    urls = {a.id: service.get_asset_url(a) for a in asset_list}
    thumbs = {a.id: service.get_thumbnail_url(a) for a in asset_list}
    for a in asset_list:
        a.display_url = urls.get(a.id) or ''
        a.display_thumbnail_url = thumbs.get(a.id) or a.display_url
    return asset_list


@login_required
def library(request):
    service = MediaService(request.user)
    folders = service.get_folder_tree()
    assets = MediaAsset.objects.filter(user=request.user).select_related('folder').order_by('-created_at')
    file_type = request.GET.get('type', '')
    folder_id = request.GET.get('folder', '')
    query = request.GET.get('q', '').strip()

    if query:
        assets = service.search_assets(query)
    if file_type:
        assets = assets.filter(file_type=file_type)
    if folder_id and folder_id.isdigit():
        assets = assets.filter(folder_id=int(folder_id))

    assets = _attach_urls(assets, service)
    tags = MediaTag.objects.filter(user=request.user)
    return render(request, 'media_assets/library.html', {
        'assets': assets,
        'folders': folders,
        'tags': tags,
        'current_type': file_type,
        'current_folder': folder_id,
        'query': query,
    })


@login_required
def upload(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')
        folder_id = request.POST.get('folder_id')
        title = request.POST.get('title', '').strip()
        is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if not uploaded_file:
            if is_xhr:
                return JsonResponse({'success': False, 'error': 'No file selected.'}, status=400)
            messages.error(request, 'Please select a file to upload.')
            return redirect('media_assets:library')

        try:
            ws_id = request.session.get('active_workspace_id')
            if ws_id:
                from apps.workspaces.models import Workspace
                try:
                    workspace = Workspace.objects.get(id=ws_id)
                except Workspace.DoesNotExist:
                    workspace = get_or_create_personal_workspace(request.user)
            else:
                workspace = get_or_create_personal_workspace(request.user)

            service = MediaService(request.user)
            service.storage = StorageService.for_workspace(workspace, user=request.user)

            asset = service.upload(uploaded_file, folder_id=folder_id, title=title or None)
        except Exception as e:
            logger.exception("Upload failed")
            if is_xhr:
                return JsonResponse({'success': False, 'error': f'Upload failed: {e}'}, status=500)
            messages.error(request, f'Upload failed: {e}')
            return redirect('media_assets:library')

        if is_xhr:
            return JsonResponse({
                'success': True,
                'asset_id': asset.id,
                'title': asset.title or asset.original_filename,
                'file_type': asset.file_type,
                'url': service.get_asset_url(asset),
                'thumbnail_url': service.get_thumbnail_url(asset),
            })

        messages.success(request, f'"{asset.original_filename}" uploaded.')
        return redirect('media_assets:detail', asset_id=asset.id)

    return redirect('media_assets:library')


@login_required
def detail(request, asset_id):
    asset = get_object_or_404(MediaAsset, id=asset_id, user=request.user)
    service = MediaService(request.user)
    asset.display_url = service.get_asset_url(asset)
    asset.display_thumbnail_url = service.get_thumbnail_url(asset)
    return render(request, 'media_assets/detail.html', {
        'asset': asset,
    })


@login_required
def delete_asset(request, asset_id):
    asset = get_object_or_404(MediaAsset, id=asset_id, user=request.user)
    if request.method == 'POST':
        service = MediaService(request.user)
        service.delete_asset(asset_id)
        messages.success(request, 'Asset deleted.')
    return redirect('media_assets:library')


@login_required
def folders(request):
    service = MediaService(request.user)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        parent_id = request.POST.get('parent_id')
        if name:
            service.create_folder(name, parent_id=parent_id)
            messages.success(request, f'Folder "{name}" created.')
        return redirect('media_assets:folders')

    if request.GET.get('format') == 'json':
        all_folders = MediaFolder.objects.filter(user=request.user)
        return JsonResponse({
            'folders': [{'id': f.id, 'name': f.name, 'parent_id': f.parent_id} for f in all_folders]
        })

    folder_tree = service.get_folder_tree()
    all_folders = MediaFolder.objects.filter(user=request.user)
    return render(request, 'media_assets/folders.html', {
        'folder_tree': folder_tree,
        'all_folders': all_folders,
    })


@login_required
def folder_detail(request, folder_id):
    folder = get_object_or_404(MediaFolder, id=folder_id, user=request.user)
    service = MediaService(request.user)
    assets = MediaAsset.objects.filter(user=request.user, folder=folder).order_by('-created_at')
    assets = _attach_urls(assets, service)
    subfolders = MediaFolder.objects.filter(parent=folder, user=request.user)
    return render(request, 'media_assets/folder_detail.html', {
        'folder': folder,
        'assets': assets,
        'subfolders': subfolders,
    })


@login_required
def delete_folder(request, folder_id):
    folder = get_object_or_404(MediaFolder, id=folder_id, user=request.user)
    if request.method == 'POST':
        folder.delete()
        messages.success(request, 'Folder deleted.')
    return redirect('media_assets:folders')


@login_required
def api_assets(request):
    assets = MediaAsset.objects.filter(user=request.user).select_related('folder').order_by('-created_at')[:100]
    service = MediaService(request.user)
    data = []
    for a in assets:
        asset_url = service.get_asset_url(a)
        thumbnail_url = service.get_thumbnail_url(a)
        data.append({
            'id': a.id,
            'title': a.title or a.original_filename,
            'original_filename': a.original_filename,
            'file_type': a.file_type,
            'url': asset_url,
            'thumbnail_url': thumbnail_url,
            'file_size': a.file_size,
            'folder': a.folder.name if a.folder else None,
            'folder_id': a.folder_id,
            'created_at': a.created_at.isoformat(),
        })
    return JsonResponse({'assets': data})


@login_required
def serve_asset(request, asset_id, file_type='original'):
    asset = get_object_or_404(MediaAsset, id=asset_id, user=request.user)

    workspace = get_or_create_personal_workspace(request.user)
    storage = StorageService.for_workspace(workspace, user=request.user)

    path = asset.thumbnail_path if file_type == 'thumbnail' else asset.storage_path
    if not path:
        return HttpResponse(status=404)

    try:
        buffer = storage.open(path)
        content = buffer.read()
        if file_type == 'thumbnail':
            content_type = 'image/webp'
        else:
            content_type, _ = mimetypes.guess_type(asset.original_filename)
        return HttpResponse(content, content_type=content_type or 'application/octet-stream')
    except FileNotFoundError:
        return HttpResponse(status=404)
    except Exception:
        logger.exception('Failed to serve asset %s (%s)', asset_id, file_type)
        return HttpResponse(status=404)
