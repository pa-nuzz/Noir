import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import SocialAccountForm, SocialPostForm
from .models import SocialAccount, SocialMediaAnalytics, SocialPost

logger = logging.getLogger(__name__)


@login_required
def social_dashboard(request):
    accounts = SocialAccount.objects.filter(user=request.user)
    total_accounts = accounts.count()
    active_accounts = accounts.filter(is_active=True).count()

    posts = SocialPost.objects.filter(user=request.user)
    scheduled_count = posts.filter(status='scheduled', scheduled_at__gte=timezone.now()).count()
    published_count = posts.filter(status='published').count()
    drafts_count = posts.filter(status='draft').count()

    upcoming_posts = posts.filter(
        status__in=['draft', 'scheduled'],
    ).select_related('account').order_by('scheduled_at', '-created_at')[:5]

    return render(request, 'social/dashboard.html', {
        'total_accounts': total_accounts,
        'active_accounts': active_accounts,
        'scheduled_count': scheduled_count,
        'published_count': published_count,
        'drafts_count': drafts_count,
        'upcoming_posts': upcoming_posts,
    })


@login_required
def account_list(request):
    accounts = SocialAccount.objects.filter(user=request.user)
    return render(request, 'social/account_list.html', {
        'accounts': accounts,
    })


@login_required
def account_connect(request):
    if request.method == 'POST':
        form = SocialAccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.user = request.user
            account.save()
            messages.success(request, f'{account.get_platform_display()} account connected.')
            return redirect('social:account_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SocialAccountForm()

    return render(request, 'social/account_connect.html', {
        'form': form,
    })


@login_required
def account_disconnect(request, account_id):
    account = get_object_or_404(SocialAccount, id=account_id, user=request.user)
    platform = account.get_platform_display()
    account.delete()
    messages.success(request, f'{platform} account disconnected.')
    return redirect('social:account_list')


@login_required
def post_list(request):
    status_filter = request.GET.get('status', '')
    posts = SocialPost.objects.filter(user=request.user).select_related('account')

    if status_filter in ('draft', 'scheduled', 'publishing', 'published', 'failed'):
        posts = posts.filter(status=status_filter)

    return render(request, 'social/post_list.html', {
        'posts': posts,
        'current_status': status_filter,
    })


@login_required
def post_create(request):
    if request.method == 'POST':
        form = SocialPostForm(request.POST, user=request.user)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.platform = post.account.platform
            if post.scheduled_at:
                post.status = 'scheduled'
                messages.success(request, 'Post scheduled successfully.')
            else:
                messages.success(request, 'Draft saved.')
            post.save()
            return redirect('social:post_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SocialPostForm(user=request.user)

    return render(request, 'social/post_form.html', {
        'form': form,
        'editing': False,
    })


@login_required
def post_detail(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id, user=request.user)
    analytics = post.analytics.order_by('-fetched_at').first()
    return render(request, 'social/post_detail.html', {
        'post': post,
        'analytics': analytics,
    })


@login_required
def post_edit(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id, user=request.user)
    if post.status == 'published':
        messages.warning(request, 'Cannot edit a published post.')
        return redirect('social:post_detail', post_id=post.id)

    if request.method == 'POST':
        form = SocialPostForm(request.POST, instance=post, user=request.user)
        if form.is_valid():
            edited = form.save(commit=False)
            if edited.scheduled_at and edited.status == 'draft':
                edited.status = 'scheduled'
            edited.platform = edited.account.platform
            edited.save()
            messages.success(request, 'Post updated.')
            return redirect('social:post_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = SocialPostForm(instance=post, user=request.user)

    return render(request, 'social/post_form.html', {
        'form': form,
        'editing': True,
    })


@login_required
def post_delete(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id, user=request.user)
    post.delete()
    messages.success(request, 'Post deleted.')
    return redirect('social:post_list')


@login_required
def analytics_overview(request):
    accounts = SocialAccount.objects.filter(user=request.user)
    posts = SocialPost.objects.filter(user=request.user, status='published')

    total_impressions = SocialMediaAnalytics.objects.filter(post__user=request.user).aggregate(
        total=Sum('impressions')
    )['total'] or 0
    total_likes = SocialMediaAnalytics.objects.filter(post__user=request.user).aggregate(
        total=Sum('likes')
    )['total'] or 0
    total_comments = SocialMediaAnalytics.objects.filter(post__user=request.user).aggregate(
        total=Sum('comments')
    )['total'] or 0
    total_shares = SocialMediaAnalytics.objects.filter(post__user=request.user).aggregate(
        total=Sum('shares')
    )['total'] or 0

    platform_breakdown = SocialMediaAnalytics.objects.filter(
        post__user=request.user
    ).values('post__platform').annotate(
        total_impressions=Sum('impressions'),
        total_likes=Sum('likes'),
    )

    return render(request, 'social/analytics.html', {
        'total_impressions': total_impressions,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'total_shares': total_shares,
        'platform_breakdown': platform_breakdown,
        'accounts': accounts,
        'posts': posts,
    })
