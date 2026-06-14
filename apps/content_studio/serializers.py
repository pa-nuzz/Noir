from rest_framework import serializers

from .models import ContentApproval, ContentItem, ContentVersion


class ContentItemSerializer(serializers.ModelSerializer):
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ContentItem
        fields = [
            'id', 'title', 'content_type', 'content_type_display', 'body',
            'platform', 'status', 'status_display', 'tags', 'metadata',
            'is_auto_generated', 'source_prompt', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'is_auto_generated', 'created_at', 'updated_at']


class ContentVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentVersion
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class ContentApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentApproval
        fields = '__all__'
        read_only_fields = ['id', 'created_at']
