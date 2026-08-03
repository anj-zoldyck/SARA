from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

# ----------------- AuditLog Model -----------------
class AuditLog(models.Model):
    """
    Centralized audit log for security-relevant events.
    MSWDO Admin-only access via audit_log_view.
    """
    ACTION_TYPE_CHOICES = (
        # Auth events
        ('LOGIN_SUCCESS', 'Login Success'),
        ('LOGIN_FAILURE', 'Login Failure'),
        ('LOGOUT', 'Logout'),
        ('OTP_SUCCESS', 'OTP Verification Success'),
        ('OTP_FAILURE', 'OTP Verification Failure'),
        # User management
        ('USER_CREATED', 'User Created'),
        ('USER_ACTIVATED', 'User Activated'),
        ('USER_DEACTIVATED', 'User Deactivated'),
        ('USER_ROLE_CHANGED', 'User Role Changed'),
        ('USER_BARANGAY_CHANGED', 'User Barangay Assignment Changed'),
        # Schedule lifecycle
        ('SCHEDULE_CREATED', 'Schedule Created'),
        ('SCHEDULE_EDITED', 'Schedule Edited'),
        ('SCHEDULE_CANCELLED', 'Schedule Cancelled'),
        ('SCHEDULE_FORCE_FINISHED', 'Schedule Force Finished'),
        ('SCHEDULE_AUTO_FINISHED', 'Schedule Auto Finished'),
        # Beneficiary list actions
        ('BENEFICIARY_LIST_GENERATED', 'Beneficiary List Generated'),
        ('BENEFICIARY_MANUAL_ADD', 'Beneficiary Manual Override Add'),
        ('BENEFICIARY_MANUAL_REMOVE', 'Beneficiary Manual Override Remove'),
        # Claims
        ('CLAIM_RFID', 'RFID Claim Processed'),
        ('CLAIM_WALKIN', 'Walk-in Claim Processed'),
        # Access-denied events
        ('ACCESS_DENIED_SCAN', 'Access Denied - Scan RFID'),
        ('ACCESS_DENIED_BENEFICIARY', 'Access Denied - Beneficiary List'),
        ('ACCESS_DENIED_SEARCH', 'Access Denied - Search Eligible'),
        ('ACCESS_DENIED_FINISH', 'Access Denied - Finish Distribution'),
        # Report generation
        ('REPORT_GENERATED', 'Report Generated'),
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="User who performed the action (null for anonymous failed login attempts)"
    )
    action_type = models.CharField(
        max_length=50,
        choices=ACTION_TYPE_CHOICES,
        db_index=True
    )
    # Generic foreign key to reference any target model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey('content_type', 'object_id')
    
    description = models.TextField(
        help_text="Human-readable description of the action (do not include sensitive values like passwords/OTPs)"
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['action_type', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
        ]

    def __str__(self):
        actor_str = f"{self.actor}" if self.actor else "Anonymous/System"
        return f"{self.created_at} - {actor_str}: {self.get_action_type_display()}"
