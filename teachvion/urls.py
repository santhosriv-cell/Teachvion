from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Page routes
    path('', include('courses.urls')),
    path('', include('accounts.urls')),
    path('', include('exams.urls')),
    path('', include('certificates.urls')),
    path('', include('dashboard.urls')),
    path('', include('liveclasses.urls')),
    path('', include('jobs.urls')),

    # REST API
    path('api/', include('accounts.api_urls')),
    path('api/', include('courses.api_urls')),
    path('api/', include('exams.api_urls')),
    path('api/', include('certificates.api_urls')),
    path('api/', include('dashboard.api_urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)