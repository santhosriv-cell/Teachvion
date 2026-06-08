from django.urls import path
from . import views

urlpatterns = [
    path('live-classes/',                                views.my_live_classes_view,      name='my_live_classes'),
    path('live-class/<int:class_id>/join/',              views.join_live_class_view,      name='join_live_class'),
    path('live-class/<int:class_id>/status/',            views.class_status_view,         name='class_status'),
    path('live-class/<int:class_id>/attend/',            views.mark_attendance_view,      name='mark_attendance'),
    path('live-class/<int:class_id>/leave/',             views.mark_leave_view,           name='mark_leave'),
    path('live-class/<int:class_id>/live-attendance/',   views.live_attendance_view,      name='live_attendance'),
    path('live-class/<int:class_id>/attendance/',        views.attendance_detail_view,    name='attendance_detail'),
    path('live-class/<int:class_id>/save-recording/',    views.save_recording_view,       name='save_recording'),
    path('live-class/<int:class_id>/delete-recording/',  views.delete_recording_view,     name='delete_recording'),
    path('trainer/course/<int:course_id>/schedule/',     views.schedule_live_class_view,  name='schedule_live_class'),
]