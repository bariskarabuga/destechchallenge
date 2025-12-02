from django.contrib import admin
from .models import Provider, AssistanceRequest, ServiceAssignment

@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'lat', 'lon', 'is_available', 'created_at']
    list_filter = ['is_available']
    search_fields = ['name', 'phone']

@admin.register(AssistanceRequest)
class AssistanceRequestAdmin(admin.ModelAdmin):
    list_display = ['customer_name', 'policy_number', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['customer_name', 'policy_number']

@admin.register(ServiceAssignment)
class ServiceAssignmentAdmin(admin.ModelAdmin):
    list_display = ['request', 'provider', 'dispatched_at']