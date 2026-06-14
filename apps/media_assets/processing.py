import logging
import os
from io import BytesIO

from django.core.files import File

logger = logging.getLogger(__name__)


class MediaProcessor:
    SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.webp'}

    def create_thumbnail(self, image_path, max_size=300):
        ext = os.path.splitext(image_path)[1].lower()
        if ext not in self.SUPPORTED_IMAGE_FORMATS:
            return None
        try:
            from PIL import Image
            img = Image.open(image_path)
            img.thumbnail((max_size, max_size), Image.Lanczos)
            thumb_io = BytesIO()
            save_format = 'JPEG' if ext in ('.jpg', '.jpeg') else 'PNG'
            img.save(thumb_io, format=save_format, quality=85)
            thumb_io.seek(0)
            return thumb_io
        except Exception as e:
            logger.exception(f"Thumbnail creation failed: {e}")
            return None

    def optimize_image(self, image_path, quality=85):
        ext = os.path.splitext(image_path)[1].lower()
        if ext not in self.SUPPORTED_IMAGE_FORMATS:
            return None
        try:
            from PIL import Image
            img = Image.open(image_path)
            if img.mode in ('RGBA', 'LA'):
                img = img.convert('RGB')
            opt_io = BytesIO()
            img.save(opt_io, format='JPEG' if ext in ('.jpg', '.jpeg') else 'PNG', quality=quality, optimize=True)
            opt_io.seek(0)
            return opt_io
        except Exception as e:
            logger.exception(f"Image optimization failed: {e}")
            return None

    def get_image_dimensions(self, image_path):
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                return img.size
        except Exception:
            return None, None

    def get_dimensions_from_bytes(self, data):
        try:
            from PIL import Image
            with Image.open(BytesIO(data)) as img:
                return img.size
        except Exception:
            return None

    def create_thumbnail_from_bytes(self, data, max_size=300):
        try:
            from PIL import Image
            with Image.open(BytesIO(data)) as img:
                resample = getattr(Image.Resampling, 'LANCZOS', Image.LANCZOS)
                img.thumbnail((max_size, max_size), resample)
                if img.mode in ('RGBA', 'LA'):
                    img = img.convert('RGB')
                thumb_io = BytesIO()
                img.save(thumb_io, format='WEBP', quality=85)
                thumb_io.seek(0)
                return thumb_io
        except Exception:
            logger.exception("Thumbnail creation from bytes failed")
            return None

    def get_video_metadata(self, video_path):
        try:
            import ffmpeg
            probe = ffmpeg.probe(video_path)
            stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            return {
                'width': int(stream.get('width', 0)),
                'height': int(stream.get('height', 0)),
                'duration': float(probe.get('format', {}).get('duration', 0)),
                'codec': stream.get('codec_name', ''),
                'bitrate': int(probe.get('format', {}).get('bit_rate', 0)),
            }
        except Exception as e:
            logger.warning(f"Video metadata extraction failed: {e}")
            return None
