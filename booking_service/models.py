
from django.core.exceptions import ValidationError
from django.db import models

class Parent(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'parents'
        ordering = ['-created_at']
    def __str__(self):
        return f"{self.name} <{self.email}>"

class LSAProfile(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    skills = models.TextField(
        blank=True,
        help_text="Comma-separated or free-text description of the LSA's skills/specialties.",
    )
    experience = models.PositiveIntegerField(
        default=0,
        help_text="Years of experience.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lsa_profiles'
        verbose_name = 'LSA Profile'
        verbose_name_plural = 'LSA Profiles'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active'], name='lsa_is_active_idx'),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class BookingRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'

    parent = models.ForeignKey(
        Parent,
        on_delete=models.PROTECT,
        related_name='booking_requests',
    )
    lsa = models.ForeignKey(
        LSAProfile,
        on_delete=models.PROTECT,
        related_name='booking_requests',
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'booking_requests'
        ordering = ['-start_time']
        indexes = [
            models.Index(fields=['status'], name='booking_status_idx'),
            models.Index(fields=['start_time'], name='booking_start_time_idx'),
            models.Index(fields=['lsa', 'start_time'], name='booking_lsa_start_idx'),
            models.Index(fields=['parent', 'start_time'], name='booking_parent_start_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F('start_time')),
                name='booking_end_time_after_start_time',
            ),
        ]

    def __str__(self):
        return f"Booking #{self.pk}: {self.parent} -> {self.lsa} ({self.status})"

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("end_time must be after start_time.")
