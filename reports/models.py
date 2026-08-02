from django.db import models
from django.conf import settings

class ReportGenerationLog(models.Model):
    REPORT_TYPE_CHOICES = (
        ('SUMMARY', 'Statistical Summary Report'),
        ('BENEFICIARY_LIST', 'Beneficiary List Report'),
    )
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    period_label = models.CharField(max_length=100)  # e.g. "April 2026" or "2nd Quarter 2026"
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_report_type_display()} — {self.period_label} — {self.generated_by} ({self.generated_at})"
