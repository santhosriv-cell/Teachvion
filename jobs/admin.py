from django.contrib import admin
from .models import JobListing, JobApplication, CompanyProfile

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display  = ['name', 'industry', 'location', 'is_approved', 'created_at']
    list_filter   = ['is_approved', 'industry']
    list_editable = ['is_approved']
    search_fields = ['name']

@admin.register(JobListing)
class JobListingAdmin(admin.ModelAdmin):
    list_display  = ['title', 'company', 'job_type', 'level', 'is_approved', 'is_active', 'posted_at']
    list_filter   = ['is_approved', 'is_active', 'job_type', 'level']
    list_editable = ['is_approved', 'is_active']
    search_fields = ['title', 'company__name']

@admin.register(JobApplication)
class JobApplicationAdmin(admin.ModelAdmin):
    list_display  = ['student', 'job', 'status', 'applied_at']
    list_filter   = ['status']
    search_fields = ['student__email', 'job__title']
    list_editable = ['status']