from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import LiveClass, Attendance
from courses.models import Course, Enrollment


# ─── Student / Trainer: join a live class ────────────────────────
@login_required
def join_live_class_view(request, class_id):
    live_class = get_object_or_404(LiveClass, id=class_id, is_active=True)

    if request.user.role == 'student':
        enrolled = Enrollment.objects.filter(
            student=request.user, course=live_class.course, payment_status='paid'
        ).exists()
        if not enrolled:
            messages.error(request, "You must be enrolled to join this class.")
            return redirect('index')

    if request.user.role == 'trainer' and live_class.trainer != request.user:
        messages.error(request, "This is not your class.")
        return redirect('trainer_dashboard')

    is_moderator = request.user.role in ('trainer', 'admin')
    return render(request, 'live_class_room.html', {
        'live_class':   live_class,
        'is_moderator': is_moderator,
        'user':         request.user,
    })


# ─── AJAX: mark attendance when student joins ────────────────────
@login_required
@require_POST
def mark_attendance_view(request, class_id):
    if request.user.role != 'student':
        return JsonResponse({'status': 'skip'})
    live_class = get_object_or_404(LiveClass, id=class_id)
    att, created = Attendance.objects.get_or_create(
        live_class=live_class, student=request.user,
        defaults={'is_present': True}
    )
    if not created:
        att.joined_at  = timezone.now()
        att.is_present = True
        att.save()
    return JsonResponse({'status': 'marked', 'created': created})


# ─── AJAX: mark student left ─────────────────────────────────────
@login_required
@require_POST
def mark_leave_view(request, class_id):
    if request.user.role != 'student':
        return JsonResponse({'status': 'skip'})
    try:
        att = Attendance.objects.get(live_class_id=class_id, student=request.user)
        att.mark_left()
        return JsonResponse({'status': 'left', 'duration': att.duration_mins_attended})
    except Attendance.DoesNotExist:
        return JsonResponse({'status': 'not_found'})


# ─── AJAX: live attendance list ──────────────────────────────────
@login_required
def live_attendance_view(request, class_id):
    live_class = get_object_or_404(LiveClass, id=class_id)
    if request.user.role == 'student':
        return JsonResponse({'error': 'Forbidden'}, status=403)
    if request.user.role == 'trainer' and live_class.trainer != request.user:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    attendees = Attendance.objects.filter(
        live_class=live_class, is_present=True
    ).select_related('student').order_by('joined_at')

    data = [{
        'id':       a.student.id,
        'name':     a.student.get_full_name(),
        'email':    a.student.email,
        'joined_at': a.joined_at.strftime('%H:%M:%S'),
        'left_at':  a.left_at.strftime('%H:%M:%S') if a.left_at else None,
        'duration': a.duration_mins_attended,
    } for a in attendees]

    return JsonResponse({'count': len(data), 'attendees': data, 'is_live': live_class.is_live_now()})


# ─── Trainer: schedule a live class ──────────────────────────────
@login_required
def schedule_live_class_view(request, course_id):
    if request.user.role not in ('trainer', 'admin'):
        messages.error(request, "Access denied.")
        return redirect('index')

    course = get_object_or_404(Course, id=course_id)

    if request.user.role == 'trainer' and course.trainer != request.user:
        messages.error(request, "This is not your course.")
        return redirect('trainer_dashboard')

    if request.method == 'POST':
        title        = request.POST.get('title', '').strip()
        description  = request.POST.get('description', '').strip()
        scheduled_at = request.POST.get('scheduled_at', '').strip()
        duration     = int(request.POST.get('duration_mins', 60))

        if not title or not scheduled_at:
            messages.error(request, "Title and scheduled time are required.")
        else:
            lc = LiveClass.objects.create(
                course=course, trainer=request.user,
                title=title, description=description,
                scheduled_at=scheduled_at, duration_mins=duration,
            )
            messages.success(request, f"Live class '{lc.title}' scheduled!")
            return redirect('my_live_classes')

    upcoming = LiveClass.objects.filter(
        course=course, is_active=True,
        scheduled_at__gte=timezone.now()
    ).order_by('scheduled_at')

    return render(request, 'schedule.html', {
        'course': course, 'upcoming': upcoming
    })


# ─── Student: list all live classes ──────────────────────────────
@login_required
def my_live_classes_view(request):
    now = timezone.now()
    if request.user.role == 'student':
        enrolled_ids = Enrollment.objects.filter(
            student=request.user, payment_status='paid'
        ).values_list('course_id', flat=True)
        classes = LiveClass.objects.filter(
            course_id__in=enrolled_ids, is_active=True,
            scheduled_at__gte=now - timezone.timedelta(hours=2)
        ).order_by('scheduled_at').select_related('course', 'trainer')
    else:
        classes = LiveClass.objects.filter(
            trainer=request.user, is_active=True,
        ).order_by('scheduled_at').select_related('course')

    classes_data = []
    for lc in classes:
        att_count = Attendance.objects.filter(live_class=lc, is_present=True).count()
        classes_data.append({'class': lc, 'att_count': att_count})

    return render(request, 'my_classes.html', {
        'classes_data': classes_data,
        'now':          now,
    })


# ─── Attendance detail page ───────────────────────────────────────
@login_required
def attendance_detail_view(request, class_id):
    live_class = get_object_or_404(LiveClass, id=class_id)

    if request.user.role == 'student':
        return redirect('my_live_classes')
    if request.user.role == 'trainer' and live_class.trainer != request.user:
        messages.error(request, "Access denied.")
        return redirect('trainer_dashboard')

    attendance = Attendance.objects.filter(
        live_class=live_class
    ).select_related('student').order_by('joined_at')

    present_count  = attendance.filter(is_present=True).count()
    enrolled_count = Enrollment.objects.filter(
        course=live_class.course, payment_status='paid'
    ).count()

    return render(request, 'attendance_detail.html', {
        'live_class':     live_class,
        'attendance':     attendance,
        'present_count':  present_count,
        'enrolled_count': enrolled_count,
        'attendance_pct': int((present_count / enrolled_count * 100) if enrolled_count else 0),
    })


# ─── AJAX: class status check ────────────────────────────────────
@login_required
def class_status_view(request, class_id):
    live_class = get_object_or_404(LiveClass, id=class_id)
    return JsonResponse({
        'is_live':   live_class.is_live_now(),
        'has_ended': live_class.has_ended(),
        'room_name': live_class.room_name,
    })


# ─── Save recording → auto-create lesson ─────────────────────────
@login_required
@require_POST
def save_recording_view(request, class_id):
    live_class = get_object_or_404(LiveClass, id=class_id)

    if request.user.role == 'student':
        return JsonResponse({'error': 'Access denied.'}, status=403)
    if request.user.role == 'trainer' and live_class.trainer != request.user:
        return JsonResponse({'error': 'Access denied.'}, status=403)

    recording_url  = request.POST.get('recording_url', '').strip()
    recording_file = request.FILES.get('recording_file')
    custom_title   = request.POST.get('title', '').strip()

    if not recording_url and not recording_file:
        messages.error(request, "Please provide a recording URL or upload a file.")
        return redirect('attendance_detail', class_id=class_id)

    # Save recording details on live class
    if recording_url:
        live_class.recording_url = recording_url
    if recording_file:
        live_class.recording_file = recording_file
    live_class.recording_status = 'ready'
    live_class.save()

    # Auto-create a Lesson in the course
    from courses.models import Lesson
    lesson_title = custom_title or f"[Live Recording] {live_class.title}"

    last_order = live_class.course.lessons.order_by('-order').values_list('order', flat=True).first()
    next_order = (last_order or 0) + 1

    lesson = Lesson.objects.create(
        course=live_class.course,
        title=lesson_title,
        video_url=recording_url or '',
        video_file=recording_file if recording_file else None,
        notes=(
            f"Recording of live class on "
            f"{live_class.scheduled_at.strftime('%d %b %Y at %H:%M')}.\n"
            f"Trainer: {live_class.trainer.get_full_name()}"
            + (f"\n\n{live_class.description}" if live_class.description else "")
        ),
        order=next_order,
        duration_mins=live_class.duration_mins,
    )

    live_class.lesson_created   = lesson
    live_class.recording_status = 'added'
    live_class.save()

    messages.success(
        request,
        f"✅ Recording saved! Lesson '{lesson.title}' added to "
        f"'{live_class.course.title}' — visible in course player."
    )
    return redirect('attendance_detail', class_id=class_id)


# ─── Delete recording + auto-created lesson ───────────────────────
@login_required
@require_POST
def delete_recording_view(request, class_id):
    live_class = get_object_or_404(LiveClass, id=class_id)

    if request.user.role == 'student':
        return JsonResponse({'error': 'Access denied.'}, status=403)
    if request.user.role == 'trainer' and live_class.trainer != request.user:
        return JsonResponse({'error': 'Access denied.'}, status=403)

    if live_class.lesson_created:
        live_class.lesson_created.delete()
        live_class.lesson_created = None

    live_class.recording_url    = ''
    live_class.recording_file   = None
    live_class.recording_status = 'none'
    live_class.save()

    messages.success(request, "Recording and its course lesson deleted.")
    return redirect('attendance_detail', class_id=class_id)