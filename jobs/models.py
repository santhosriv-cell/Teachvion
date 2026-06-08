from django.db import models
from django.utils import timezone


class CompanyProfile(models.Model):
    """Extended profile for partner companies."""
    company_user  = models.OneToOneField(
        'accounts.CustomUser', on_delete=models.CASCADE,
        related_name='company_profile',
        null=True, blank=True
    )
    # linked to PartnerCompany if already exists
    partner       = models.OneToOneField(
        'certificates.PartnerCompany', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='job_profile'
    )
    name          = models.CharField(max_length=200)
    logo          = models.ImageField(upload_to='company_logos/', blank=True, null=True)
    website       = models.URLField(blank=True)
    about         = models.TextField(blank=True)
    location      = models.CharField(max_length=200, blank=True)
    industry      = models.CharField(max_length=100, blank=True)
    is_approved   = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class JobListing(models.Model):
    TYPE_CHOICES = [
        ('full_time',  'Full Time'),
        ('part_time',  'Part Time'),
        ('internship', 'Internship'),
        ('contract',   'Contract'),
        ('remote',     'Remote'),
    ]
    LEVEL_CHOICES = [
        ('fresher',   'Fresher / Entry Level'),
        ('junior',    'Junior (1-2 yrs)'),
        ('mid',       'Mid Level (2-5 yrs)'),
        ('senior',    'Senior (5+ yrs)'),
    ]

    company          = models.ForeignKey(
        CompanyProfile, on_delete=models.CASCADE, related_name='jobs'
    )
    title            = models.CharField(max_length=200)
    description      = models.TextField()
    requirements     = models.TextField(blank=True)
    responsibilities = models.TextField(blank=True)
    job_type         = models.CharField(max_length=20, choices=TYPE_CHOICES, default='full_time')
    level            = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='fresher')
    location         = models.CharField(max_length=200, blank=True)
    salary_min       = models.PositiveIntegerField(null=True, blank=True)
    salary_max       = models.PositiveIntegerField(null=True, blank=True)
    skills           = models.CharField(max_length=500, blank=True,
                                        help_text='Comma-separated skills e.g. Python, Django, SQL')

    # Certificate gate: student must hold this course's certificate to apply
    required_course  = models.ForeignKey(
        'courses.Course', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='job_listings',
        help_text='Leave blank to allow any certified student'
    )
    min_exam_score   = models.PositiveIntegerField(
        default=50, help_text='Minimum exam score % required'
    )

    is_active        = models.BooleanField(default=True)
    is_approved      = models.BooleanField(default=False)  # admin approves
    deadline         = models.DateField(null=True, blank=True)
    posted_at        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-posted_at']

    def is_open(self):
        if not self.is_active or not self.is_approved:
            return False
        if self.deadline and self.deadline < timezone.now().date():
            return False
        return True

    def salary_display(self):
        if self.salary_min and self.salary_max:
            return f'₹{self.salary_min:,} – ₹{self.salary_max:,} / year'
        elif self.salary_min:
            return f'₹{self.salary_min:,}+ / year'
        return 'Not disclosed'

    def skills_list(self):
        return [s.strip() for s in self.skills.split(',') if s.strip()]

    def __str__(self):
        return f"{self.title} @ {self.company.name}"


class JobApplication(models.Model):
    STATUS_CHOICES = [
        ('applied',    'Applied'),
        ('reviewing',  'Under Review'),
        ('shortlisted','Shortlisted'),
        ('rejected',   'Rejected'),
        ('hired',      'Hired 🎉'),
    ]

    job           = models.ForeignKey(JobListing, on_delete=models.CASCADE, related_name='applications')
    student       = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.CASCADE, related_name='job_applications'
    )
    certificate   = models.ForeignKey(
        'certificates.Certificate', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='job_applications',
        help_text='Certificate used to qualify for this job'
    )
    resume        = models.FileField(upload_to='resumes/', blank=True, null=True)
    cover_letter  = models.TextField(blank=True)
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default='applied')
    applied_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)
    company_notes = models.TextField(blank=True)  # private notes by company

    class Meta:
        unique_together = ('job', 'student')
        ordering = ['-applied_at']

    def __str__(self):
        return f"{self.student.get_full_name()} → {self.job.title}"