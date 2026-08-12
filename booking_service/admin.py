from django.contrib import admin
from .models import Parent, LSAProfile, BookingRequest

@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'phone', 'created_at')
    search_fields = ('name', 'email')

@admin.register(LSAProfile)
class LSAProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'experience', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'email', 'skills')

@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'parent', 'lsa', 'start_time', 'end_time', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('parent__name', 'lsa__name')
