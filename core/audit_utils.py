"""
Centralized audit logging utility for S.A.R.A.
Provides a single function to log security-relevant events to the AuditLog model.
"""
from django.contrib.contenttypes.models import ContentType
from core.models import AuditLog


def log_action(actor, action_type, target=None, description="", ip_address=None):
    """
    Log an audit event to the AuditLog model.
    
    Args:
        actor: User object who performed the action (can be None for anonymous events)
        action_type: String matching AuditLog.ACTION_TYPE_CHOICES
        target: Optional model instance being acted upon (for GenericForeignKey)
        description: Human-readable description (do NOT include sensitive values like passwords/OTPs)
        ip_address: Optional IP address string
    
    Returns:
        AuditLog instance (created)
    """
    content_type = None
    object_id = None
    
    if target is not None:
        content_type = ContentType.objects.get_for_model(target)
        object_id = target.pk
    
    return AuditLog.objects.create(
        actor=actor,
        action_type=action_type,
        content_type=content_type,
        object_id=object_id,
        description=description,
        ip_address=ip_address
    )
