from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count
from accounts.models import CustomUser
from courses.models import Course, Enrollment, VideoProgress, Attendance as CourseAttendance
from certificates.models import Certificate
from exams.models import ExamAttempt


def role_required(*roles):
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.role not in roles:
                messages.error(request, "Access denied.")
                return redirect('index')
            return view_func(request, *args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper
    return decorator


# ─── Student Dashboard ────────────────────────────────────────────
@login_required
@role_required('student')
def student_dashboard_view(request):
    paid_enrollments = Enrollment.objects.filter(
        student=request.user, payment_status='paid'
    ).select_related('course').order_by('-enrolled_at')

    pending_enrollments = Enrollment.objects.filter(
        student=request.user, payment_status='pending'
    ).select_related('course').order_by('-enrolled_at')

    total_spent = paid_enrollments.aggregate(total=Sum('amount_paid'))['total'] or 0
    total_enrolled = paid_enrollments.count()

    courses_data = []
    for e in paid_enrollments:
        total = e.course.lessons.count()
        done = VideoProgress.objects.filter(
            student=request.user, lesson__course=e.course, completed=True
        ).count()
        pct = int((done / total) * 100) if total else 0
        exam_attempt = ExamAttempt.objects.filter(
            student=request.user, course=e.course
        ).order_by('-attempted_at').first()

        courses_data.append({
            'enrollment':      e,
            'course':          e.course,
            'progress':        pct,
            'completed_lessons': done,
            'total_lessons':   total,
            'exam_attempt':    exam_attempt,
            'can_take_exam':   pct == 100,
        })

    certificates = Certificate.objects.filter(
        student=request.user
    ).select_related('course').order_by('-issued_at')

    upcoming_live_classes = []
    try:
        from liveclasses.models import LiveClass
        course_ids = paid_enrollments.values_list('course_id', flat=True)
        upcoming_live_classes = LiveClass.objects.filter(
            course_id__in=course_ids,
            is_active=True,
            scheduled_at__gte=timezone.now()
        ).order_by('scheduled_at')[:5]
    except Exception:
        upcoming_live_classes = []

    return render(request, 'student_dashboard.html', {
        'student':              request.user,
        'courses_data':         courses_data,
        'certificates':         certificates,
        'total_enrolled':       total_enrolled,
        'total_courses':        total_enrolled,
        'total_spent':          total_spent,
        'total_certs':          certificates.count(),
        'pending_enrollments':  pending_enrollments,
        'upcoming_live_classes': upcoming_live_classes,
    })


# ─── Trainer Dashboard ────────────────────────────────────────────
@login_required
@role_required('trainer')
def trainer_dashboard_view(request):
    trainer  = request.user
    courses  = Course.objects.filter(trainer=trainer, is_active=True)

    courses_data = []
    total_students = 0
    for course in courses:
        enrollments = Enrollment.objects.filter(
            course=course, payment_status='paid'
        ).select_related('student')

        students_progress = []
        for e in enrollments:
            total = course.lessons.count()
            done  = VideoProgress.objects.filter(
                student=e.student, lesson__course=course, completed=True
            ).count()
            pct = int((done / total) * 100) if total else 0
            attempt = ExamAttempt.objects.filter(
                student=e.student, course=course
            ).order_by('-attempted_at').first()
            students_progress.append({
                'student':      e.student,
                'progress':     pct,
                'exam_attempt': attempt,
                'enrolled_at':  e.enrolled_at,
            })

        total_students += len(students_progress)

        from courses.models import ClassTiming
        timings = ClassTiming.objects.filter(
            course=course, trainer=trainer
        ).order_by('day_of_week', 'start_time')

        courses_data.append({
            'course':        course,
            'students':      students_progress,
            'student_count': len(students_progress),
            'lesson_count':  course.lessons.count(),
            'timings':       timings,
        })

    # Live class attendance data
    live_attendance_data = []
    try:
        from liveclasses.models import LiveClass, Attendance
        upcoming_classes = LiveClass.objects.filter(
            trainer=trainer, is_active=True,
            scheduled_at__gte=timezone.now() - timezone.timedelta(hours=2)
        ).order_by('scheduled_at').select_related('course')[:5]

        for lc in upcoming_classes:
            att_count = Attendance.objects.filter(live_class=lc, is_present=True).count()
            live_attendance_data.append({'class': lc, 'att_count': att_count})
    except Exception:
        upcoming_classes = []

    return render(request, 'trainer_dashboard.html', {
        'trainer':             trainer,
        'courses_data':        courses_data,
        'total_courses':       courses.count(),
        'total_students':      total_students,
        'live_attendance_data': live_attendance_data,
    })


# ─── Admin Dashboard ─────────────────────────────────────────────
@login_required
@role_required('admin')
def admin_dashboard_view(request):
    from datetime import timedelta, date
    from django.db.models.functions import TruncMonth

    # ── Stats ──
    total_students     = CustomUser.objects.filter(role='student').count()
    total_trainers     = CustomUser.objects.filter(role='trainer').count()
    total_courses      = Course.objects.filter(is_active=True).count()
    total_revenue      = Enrollment.objects.filter(
        payment_status='paid'
    ).aggregate(t=Sum('amount_paid'))['t'] or 0
    total_certificates = Certificate.objects.count()
    total_enrollments  = Enrollment.objects.filter(payment_status='paid').count()

    # ── Recent enrollments (last 30 days) ──
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_enrollments = Enrollment.objects.filter(
        enrolled_at__gte=thirty_days_ago
    ).select_related(
        'student', 'course', 'course__trainer'
    ).order_by('-enrolled_at')[:20]

    total_attendance = CourseAttendance.objects.count()

    # ── Monthly revenue chart (last 6 months) ──
    monthly_revenue = []
    today = date.today()
    for i in range(5, -1, -1):
        # Go back i months from today
        if today.month - i <= 0:
            year  = today.year - 1
            month = today.month - i + 12
        else:
            year  = today.year
            month = today.month - i

        rev = Enrollment.objects.filter(
            payment_status='paid',
            enrolled_at__year=year,
            enrolled_at__month=month,
        ).aggregate(t=Sum('amount_paid'))['t'] or 0

        import calendar
        monthly_revenue.append({
            'month':   calendar.month_abbr[month],
            'revenue': float(rev),
        })

    # ── All students, trainers, courses ──
    students = CustomUser.objects.filter(role='student').order_by('-date_joined')
    trainers = CustomUser.objects.filter(role='trainer').order_by('-date_joined')
    courses  = Course.objects.all().select_related('trainer').prefetch_related('enrollments', 'attendances')
    for c in courses:
        present_count = c.attendances.filter(attended=True).count()
        total_att_records = c.attendances.count()
        c.attendance_count = present_count
        c.attendance_students = c.attendances.filter(attended=True).values('student').distinct().count()
        c.attendance_rate = int((present_count / total_att_records) * 100) if total_att_records else 0

    # ── Per-trainer stats ──
    trainers_data = []
    for t in trainers:
        assigned      = Course.objects.filter(trainer=t, is_active=True)
        student_count = Enrollment.objects.filter(
            course__trainer=t, payment_status='paid'
        ).values('student').distinct().count()
        trainers_data.append({
            'trainer':       t,
            'assigned':      assigned,
            'course_count':  assigned.count(),
            'student_count': student_count,
        })

    # ── Live attendance — only for classes happening TODAY ──
    # FIX: filter by today's date so admin doesn't see all-time attendance
    live_attendance_data = []
    try:
        from liveclasses.models import LiveClass, Attendance
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end   = today_start + timedelta(days=1)

        todays_classes = LiveClass.objects.filter(
            is_active=True,
            scheduled_at__gte=today_start,
            scheduled_at__lt=today_end,
        ).select_related('course', 'trainer').order_by('scheduled_at')

        for lc in todays_classes:
            att_records = Attendance.objects.filter(
                live_class=lc, is_present=True
            ).select_related('student').order_by('joined_at')
            live_attendance_data.append({
                'class':      lc,
                'attendance': att_records,
                'att_count':  att_records.count(),
            })
    except Exception:
        pass

    return render(request, 'admin_dashboard.html', {
        'total_students':      total_students,
        'total_trainers':      total_trainers,
        'total_courses':       total_courses,
        'total_revenue':       total_revenue,
        'total_certificates':  total_certificates,
        'total_enrollments':   total_enrollments,
        'total_attendance':    total_attendance,
        'recent_enrollments':  recent_enrollments,
        'monthly_revenue':     monthly_revenue,
        'students':            students,
        'trainers':            trainers,
        'trainers_data':       trainers_data,
        'courses':             courses,
        'all_trainers':        trainers,
        'live_attendance_data': live_attendance_data,
    })


# ─── Admin: Edit user ─────────────────────────────────────────────
@login_required
@role_required('admin')
def admin_student_edit_view(request, user_id):
    user_obj = get_object_or_404(CustomUser, id=user_id)
    if request.method == 'POST':
        user_obj.first_name = request.POST.get('first_name', user_obj.first_name)
        user_obj.last_name  = request.POST.get('last_name',  user_obj.last_name)
        user_obj.phone      = request.POST.get('phone', user_obj.phone)
        user_obj.is_active  = 'is_active' in request.POST
        user_obj.save()
        messages.success(request, f"User '{user_obj.get_full_name()}' updated.")
        return redirect('admin_dashboard')
    return render(request, 'edit_user.html', {'user_obj': user_obj})


@login_required
@role_required('admin')
def admin_user_delete_view(request, user_id):
    user_obj = get_object_or_404(CustomUser, id=user_id)
    user_obj.is_active = False
    user_obj.save()
    messages.success(request, f"User '{user_obj.get_full_name()}' deactivated.")
    return redirect('admin_dashboard')


# ─── Admin: Course CRUD ───────────────────────────────────────────
@login_required
@role_required('admin')
def admin_course_create_view(request):
    if request.method == 'POST':
        from courses.forms import CourseForm
        form = CourseForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Course created.")
            return redirect('admin_dashboard')
    else:
        from courses.forms import CourseForm
        form = CourseForm()
    return render(request, 'course_form.html', {'form': form, 'action': 'Create'})


@login_required
@role_required('admin')
def admin_course_edit_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if request.method == 'POST':
        from courses.forms import CourseForm
        form = CourseForm(request.POST, request.FILES, instance=course)
        if form.is_valid():
            form.save()
            messages.success(request, "Course updated.")
            return redirect('admin_dashboard')
    else:
        from courses.forms import CourseForm
        form = CourseForm(instance=course)
    return render(request, 'course_form.html', {
        'form': form, 'course': course, 'action': 'Edit'
    })


@login_required
@role_required('admin')
def admin_course_delete_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    course.is_active = False
    course.save()
    messages.success(request, f"Course '{course.title}' deactivated.")
    return redirect('admin_dashboard')


# ─── Admin: Assign trainer ────────────────────────────────────────
@login_required
@role_required('admin')
def admin_assign_trainer_view(request, course_id):
    if request.method == 'POST':
        course     = get_object_or_404(Course, id=course_id)
        trainer_id = request.POST.get('trainer_id')
        if trainer_id:
            trainer = get_object_or_404(CustomUser, id=trainer_id, role='trainer')
            course.trainer = trainer
            course.save()
            messages.success(request, f"'{trainer.get_full_name()}' assigned to '{course.title}'.")
        else:
            course.trainer = None
            course.save()
            messages.success(request, f"Trainer removed from '{course.title}'.")
    return redirect('admin_dashboard')