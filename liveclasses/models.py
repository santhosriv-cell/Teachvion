from django.db import models
from django.utils import timezone
import uuid


class LiveClass(models.Model):
    course        = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='live_classes')
    trainer       = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name='live_classes')
    title         = models.CharField(max_length=200)
    description   = models.TextField(blank=True)
    scheduled_at  = models.DateTimeField()
    duration_mins = models.PositiveIntegerField(default=60)
    room_name     = models.CharField(max_length=100, unique=True, blank=True)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    # Recording fields
    recording_url      = models.URLField(blank=True)        # Jitsi/Dropbox/Drive link
    recording_file     = models.FileField(upload_to='recordings/', blank=True, null=True)
    recording_status   = models.CharField(
        max_length=20,
        choices=[
            ('none',       'Not Recorded'),
            ('recording',  'Recording in Progress'),
            ('processing', 'Processing'),
            ('ready',      'Ready'),
            ('added',      'Added to Course'),
        ],
        default='none'
    )
    lesson_created     = models.ForeignKey(
        'courses.Lesson', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='from_live_class'
    )  # The lesson auto-created from this recording

    class Meta:
        ordering = ['scheduled_at']

    def save(self, *args, **kwargs):
        if not self.room_name:
            slug = self.course.title.lower().replace(' ', '-')[:30]
            self.room_name = f"teachvion-{slug}-{uuid.uuid4().hex[:6]}"
        super().save(*args, **kwargs)

    def is_live_now(self):
        now = timezone.now()
        end = self.scheduled_at + timezone.timedelta(minutes=self.duration_mins)
        return self.scheduled_at <= now <= end

    def has_ended(self):
        end = self.scheduled_at + timezone.timedelta(minutes=self.duration_mins)
        return timezone.now() > end

    def __str__(self):
        return f"{self.course.title} — {self.title}"


class Attendance(models.Model):
    live_class             = models.ForeignKey(LiveClass, on_delete=models.CASCADE, related_name='attendance')
    student                = models.ForeignKey('accounts.CustomUser', on_delete=models.CASCADE, related_name='attendance')
    joined_at              = models.DateTimeField(auto_now_add=True)
    left_at                = models.DateTimeField(null=True, blank=True)
    duration_mins_attended = models.PositiveIntegerField(default=0)
    is_present             = models.BooleanField(default=True)

    class Meta:
        unique_together = ('live_class', 'student')
        ordering = ['joined_at']

    def mark_left(self):
        self.left_at = timezone.now()
        if self.joined_at:
            delta = (self.left_at - self.joined_at).total_seconds() / 60
            self.duration_mins_attended = int(delta)
        self.save()

    def __str__(self):
        return f"{self.student.get_full_name()} — {self.live_class.title}"