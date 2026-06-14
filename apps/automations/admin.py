from django.contrib import admin

from .models import Workflow, WorkflowNode, WorkflowEdge, WorkflowEnrollment


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name']


@admin.register(WorkflowNode)
class WorkflowNodeAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'node_id', 'type', 'created_at']
    list_filter = ['type']


@admin.register(WorkflowEdge)
class WorkflowEdgeAdmin(admin.ModelAdmin):
    list_display = ['workflow', 'from_node_id', 'to_node_id', 'condition']


@admin.register(WorkflowEnrollment)
class WorkflowEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['contact', 'workflow', 'status', 'next_execution_at']
    list_filter = ['status']
