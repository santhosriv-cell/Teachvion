from django.urls import path
from . import views

urlpatterns = [
    path('jobs/',views.job_board_view,name='job_board'),
    path('jobs/<int:job_id>/',views.job_detail_view,name='job_detail'),
    path('jobs/<int:job_id>/apply/',views.apply_job_view,name='apply_job'),
    path('jobs/my-applications/',views.my_applications_view,name='my_applications'),
    path('jobs/post/',views.post_job_view,name='post_job'),
    path('jobs/company-portal/',views.company_portal_view,name='company_portal'),
    path('jobs/application/<int:app_id>/status/',views.update_application_status_view,name='update_app_status'),
    path('admin-panel/jobs/',views.admin_jobs_view,name='admin_jobs'),
    path('admin-panel/jobs/post/', views.admin_post_job_view, name='admin_post_job'),
]