from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from .models import JobListing, JobApplication, CompanyProfile
from certificates.models import Certificate


# ─── Public job board ────────────────────────────────────────────
def job_board_view(request):
    jobs = JobListing.objects.filter(
        is_active=True, is_approved=True
    ).select_related('company', 'required_course')

    q        = request.GET.get('q', '').strip()
    job_type = request.GET.get('type', '')
    level    = request.GET.get('level', '')

    if q:
        jobs = jobs.filter(
            Q(title__icontains=q) |
            Q(company__name__icontains=q) |
            Q(skills__icontains=q) |
            Q(location__icontains=q)
        )
    if job_type:
        jobs = jobs.filter(job_type=job_type)
    if level:
        jobs = jobs.filter(level=level)

    applied_job_ids = set()
    student_certs   = []
    if request.user.is_authenticated and request.user.role == 'student':
        applied_job_ids = set(
            JobApplication.objects.filter(student=request.user)
            .values_list('job_id', flat=True)
        )
        student_certs = Certificate.objects.filter(
            student=request.user
        ).select_related('course', 'exam_attempt')

    from courses.models import Course
    courses = Course.objects.filter(is_active=True)

    return render(request, 'job_board.html', {
        'jobs':            jobs,
        'applied_job_ids': applied_job_ids,
        'student_certs':   student_certs,
        'courses':         courses,
        'q':               q,
        'job_type':        job_type,
        'level':           level,
    })


# ─── Job detail ───────────────────────────────────────────────────
def job_detail_view(request, job_id):
    job = get_object_or_404(JobListing, id=job_id, is_active=True, is_approved=True)

    already_applied = False
    can_apply       = False
    qualifying_cert = None
    student_certs   = []

    if request.user.is_authenticated and request.user.role == 'student':
        already_applied = JobApplication.objects.filter(
            job=job, student=request.user
        ).exists()
        student_certs = Certificate.objects.filter(
            student=request.user
        ).select_related('course', 'exam_attempt')
        for cert in student_certs:
            if cert.exam_attempt and cert.exam_attempt.percentage >= job.min_exam_score:
                if job.required_course is None or cert.course == job.required_course:
                    qualifying_cert = cert
                    can_apply = True
                    break

    similar_jobs = JobListing.objects.filter(
        is_active=True, is_approved=True, company=job.company
    ).exclude(id=job.id)[:3]

    return render(request, 'job_detail.html', {
        'job':             job,
        'already_applied': already_applied,
        'can_apply':       can_apply,
        'qualifying_cert': qualifying_cert,
        'student_certs':   student_certs,
        'similar_jobs':    similar_jobs,
    })


# ─── Apply ────────────────────────────────────────────────────────
@login_required
def apply_job_view(request, job_id):
    if request.user.role != 'student':
        messages.error(request, "Only students can apply.")
        return redirect('job_board')

    job = get_object_or_404(JobListing, id=job_id, is_active=True, is_approved=True)

    if not job.is_open():
        messages.error(request, "This job is no longer accepting applications.")
        return redirect('job_detail', job_id=job.id)

    if JobApplication.objects.filter(job=job, student=request.user).exists():
        messages.warning(request, "You already applied for this job.")
        return redirect('job_detail', job_id=job.id)

    qualifying_cert = None
    for cert in Certificate.objects.filter(student=request.user).select_related('course', 'exam_attempt'):
        if cert.exam_attempt and cert.exam_attempt.percentage >= job.min_exam_score:
            if job.required_course is None or cert.course == job.required_course:
                qualifying_cert = cert
                break

    if not qualifying_cert:
        messages.error(request, f"You need a certificate with {job.min_exam_score}%+ to apply.")
        return redirect('job_detail', job_id=job.id)

    if request.method == 'POST':
        JobApplication.objects.create(
            job=job,
            student=request.user,
            certificate=qualifying_cert,
            cover_letter=request.POST.get('cover_letter', '').strip(),
            resume=request.FILES.get('resume'),
            status='applied',
        )
        messages.success(request, f"Applied for {job.title} at {job.company.name}!")
        return redirect('my_applications')

    return render(request, 'apply.html', {
        'job': job, 'qualifying_cert': qualifying_cert,
    })


# ─── Student: my applications ─────────────────────────────────────
@login_required
def my_applications_view(request):
    if request.user.role != 'student':
        return redirect('job_board')
    applications = JobApplication.objects.filter(
        student=request.user
    ).select_related('job', 'job__company', 'certificate').order_by('-applied_at')
    return render(request, 'my_applications.html', {'applications': applications})


# ─── Company: post a job ──────────────────────────────────────────
@login_required
def post_job_view(request):
    company, _ = CompanyProfile.objects.get_or_create(
        company_user=request.user,
        defaults={'name': request.user.get_full_name() or request.user.email, 'is_approved': False}
    )

    if request.method == 'POST':
        from courses.models import Course
        course_id = request.POST.get('required_course') or None
        course    = Course.objects.filter(id=course_id).first() if course_id else None
        JobListing.objects.create(
            company=company,
            title=request.POST.get('title', '').strip(),
            description=request.POST.get('description', '').strip(),
            requirements=request.POST.get('requirements', '').strip(),
            responsibilities=request.POST.get('responsibilities', '').strip(),
            job_type=request.POST.get('job_type', 'full_time'),
            level=request.POST.get('level', 'fresher'),
            location=request.POST.get('location', '').strip(),
            salary_min=request.POST.get('salary_min') or None,
            salary_max=request.POST.get('salary_max') or None,
            skills=request.POST.get('skills', '').strip(),
            required_course=course,
            min_exam_score=int(request.POST.get('min_exam_score', 50)),
            deadline=request.POST.get('deadline') or None,
            is_approved=False,
        )
        messages.success(request, "Job submitted for admin review.")
        return redirect('company_portal')

    from courses.models import Course
    courses = Course.objects.filter(is_active=True)
    return render(request, 'post_job.html', {'company': company, 'courses': courses})


# ─── Company: portal ─────────────────────────────────────────────
@login_required
def company_portal_view(request):
    company, _ = CompanyProfile.objects.get_or_create(
        company_user=request.user,
        defaults={'name': request.user.get_full_name() or request.user.email}
    )
    jobs = JobListing.objects.filter(company=company).order_by('-posted_at')
    applications = JobApplication.objects.filter(
        job__company=company
    ).select_related('student', 'job', 'certificate').order_by('-applied_at')
    return render(request, 'jobs/company_portal.html', {
        'company': company, 'jobs': jobs, 'applications': applications,
    })


# ─── Company: update application status ───────────────────────────
@login_required
def update_application_status_view(request, app_id):
    app = get_object_or_404(
        JobApplication, id=app_id, job__company__company_user=request.user
    )
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(JobApplication.STATUS_CHOICES):
            app.status        = new_status
            app.company_notes = request.POST.get('notes', '')
            app.save()
            return JsonResponse({'ok': True, 'status': app.get_status_display()})
    return JsonResponse({'ok': False}, status=400)


# ─── Admin: approve / reject jobs & companies ────────────────────
@login_required
def admin_jobs_view(request):
    if request.user.role != 'admin':
        return redirect('index')

    if request.method == 'POST':
        action   = request.POST.get('action')
        obj_id   = request.POST.get('id')
        obj_type = request.POST.get('type')
        if obj_type == 'job':
            job = get_object_or_404(JobListing, id=obj_id)
            job.is_approved = (action == 'approve')
            job.is_active   = (action == 'approve')
            job.save()
            messages.success(request, f"Job '{ job.title }' {'approved ✅' if job.is_approved else 'rejected ❌'}.")
        elif obj_type == 'company':
            co = get_object_or_404(CompanyProfile, id=obj_id)
            co.is_approved = (action == 'approve')
            co.save()
            messages.success(request, f"Company '{co.name}' {'approved ✅' if co.is_approved else 'rejected ❌'}.")
        return redirect('admin_jobs')

    pending_jobs      = JobListing.objects.filter(is_approved=False).select_related('company')
    pending_companies = CompanyProfile.objects.filter(is_approved=False)
    all_jobs          = JobListing.objects.filter(is_approved=True).select_related('company')

    return render(request, 'admin_jobs.html', {
        'pending_jobs':      pending_jobs,
        'pending_companies': pending_companies,
        'all_jobs':          all_jobs,
    })


# ─── Admin: post a job (auto-approved, live immediately) ──────────
@login_required
def admin_post_job_view(request):
    if request.user.role != 'admin':
        messages.error(request, "Access denied.")
        return redirect('index')

    from courses.models import Course
    courses = Course.objects.filter(is_active=True)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, "Job title is required.")
            return render(request, 'admin_post_job.html', {'courses': courses})

        # Get or create a company profile for this job
        # Admin can set the company name via the form
        company_name = request.POST.get('company_name', '').strip() or 'Teachvion Partner'

        company, _ = CompanyProfile.objects.get_or_create(
            name=company_name,
            defaults={
                'is_approved': True,
                'about':       f'Partner company listed by Teachvion admin.',
            }
        )
        # Always ensure admin-created companies are approved
        if not company.is_approved:
            company.is_approved = True
            company.save()

        course_id = request.POST.get('required_course') or None
        course    = Course.objects.filter(id=course_id).first() if course_id else None

        # Safely parse optional integer fields
        salary_min    = request.POST.get('salary_min', '').strip()
        salary_max    = request.POST.get('salary_max', '').strip()
        min_score_raw = request.POST.get('min_exam_score', '50').strip()

        try:
            min_score = int(min_score_raw) if min_score_raw else 50
        except ValueError:
            min_score = 50

        try:
            salary_min_val = int(salary_min) if salary_min else None
        except ValueError:
            salary_min_val = None

        try:
            salary_max_val = int(salary_max) if salary_max else None
        except ValueError:
            salary_max_val = None

        deadline = request.POST.get('deadline', '').strip() or None

        job = JobListing.objects.create(
            company=company,
            title=title,
            description=request.POST.get('description', '').strip(),
            requirements=request.POST.get('requirements', '').strip(),
            responsibilities=request.POST.get('responsibilities', '').strip(),
            job_type=request.POST.get('job_type', 'full_time'),
            level=request.POST.get('level', 'fresher'),
            location=request.POST.get('location', '').strip(),
            salary_min=salary_min_val,
            salary_max=salary_max_val,
            skills=request.POST.get('skills', '').strip(),
            required_course=course,
            min_exam_score=min_score,
            deadline=deadline,
            is_approved=True,    # ← auto-approved
            is_active=True,      # ← live immediately
        )

        messages.success(
            request,
            f"✅ Job '{job.title}' at {company.name} is now LIVE on the homepage!"
        )
        return redirect('admin_jobs')

    return render(request, 'admin_post_job.html', {'courses': courses})