import logging

logger = logging.getLogger(__name__)


class AutoTaggingService:
    def __init__(self):
        self._mock_tags = {
            'image': ['photo', 'visual', 'graphic', 'design', 'creative'],
            'video': ['video', 'motion', 'animation', 'footage', 'clip'],
            'audio': ['audio', 'sound', 'music', 'podcast', 'recording'],
            'document': ['document', 'text', 'report', 'file', 'pdf'],
        }

    def suggest_tags(self, file_type, filename=None, content=None):
        base_tags = list(self._mock_tags.get(file_type, ['asset']))
        if filename:
            name_tags = [w.lower() for w in filename.replace('_', ' ').replace('-', ' ').split()
                         if len(w) > 3 and w.lower() not in ('the', 'and', 'for', 'with')]
            base_tags.extend(name_tags[:3])
        return list(set(base_tags))

    def auto_tag(self, asset):
        tags = self.suggest_tags(asset.file_type, asset.original_filename)
        asset.auto_tags = tags
        asset.save(update_fields=['auto_tags'])

        from .models import MediaTag
        for tag_name in tags:
            tag, _ = MediaTag.objects.get_or_create(name=tag_name, user=asset.user)
            asset.tags.add(tag)

        return tags

    def analyze_image_content(self, image_path):
        logger.info(f"AI image analysis for {image_path} (placeholder)")
        return {
            'labels': ['object', 'scene', 'text'],
            'colors': ['#000000', '#ffffff'],
            'safe_search': 'likely',
        }
