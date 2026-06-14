import base64
import hashlib
import hmac
import logging
import struct
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.workspaces.models import WorkspaceMembership

logger = logging.getLogger(__name__)


def _generate_qr_svg(uri):
    try:
        import qrcode
        import qrcode.image.svg
        factory = qrcode.image.svg.SvgPathImage
        img = qrcode.make(uri, image_factory=factory)
        return img.to_string().decode()
    except ImportError:
        logger.warning('qrcode package not installed — QR code generation disabled')
        return None
    except Exception as exc:
        logger.exception('Failed to generate QR code: %s', exc)
        return None


@login_required
def mfa_settings(request):
    devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
    return render(request, 'mfa/settings.html', {
        'devices': devices,
    })


@login_required
def mfa_enable(request):
    if TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
        messages.info(request, 'MFA is already enabled.')
        return redirect('mfa:settings')

    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    if not device:
        device = TOTPDevice.objects.create(
            user=request.user,
            name='default',
            confirmed=False,
        )

    uri = device.config_url
    svg = _generate_qr_svg(uri)

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        if device.verify_token(code):
            device.confirmed = True
            device.save()
            messages.success(request, 'MFA has been enabled successfully.')
            return redirect('mfa:settings')
        messages.error(request, 'Invalid code. Please try again.')

    return render(request, 'mfa/enable.html', {
        'device': device,
        'provisioning_uri': uri,
        'qr_svg': svg,
    })


@login_required
def mfa_disable(request):
    device_id = request.POST.get('device_id')
    devices = TOTPDevice.objects.filter(user=request.user, id=device_id) if device_id else TOTPDevice.objects.none()
    if not devices.exists():
        messages.error(request, 'Device not found.')
        return redirect('mfa:settings')

    device = devices.first()
    code = request.POST.get('code', '').strip()
    if device.verify_token(code):
        device.delete()
        messages.success(request, 'MFA device removed.')
    else:
        messages.error(request, 'Invalid code. Device not removed.')

    return redirect('mfa:settings')


def mfa_required(request):
    return render(request, 'mfa/required.html')
