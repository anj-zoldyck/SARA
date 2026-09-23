from django.core.management.base import BaseCommand
from programs.models import EligibilityRule


class Command(BaseCommand):
    help = 'Check for any ACTIVE_TYPHOON_SIGNAL eligibility rules in the database'

    def handle(self, *args, **options):
        typhoon_rules = EligibilityRule.objects.filter(rule_type='ACTIVE_TYPHOON_SIGNAL').select_related('assistance__program')
        self.stdout.write(f'Total ACTIVE_TYPHOON_SIGNAL rules found: {typhoon_rules.count()}')
        
        if typhoon_rules.count() == 0:
            self.stdout.write(self.style.SUCCESS('No ACTIVE_TYPHOON_SIGNAL rules found. Safe to proceed with removal.'))
        else:
            self.stdout.write(self.style.WARNING('Found ACTIVE_TYPHOON_SIGNAL rules. Details:'))
            for r in typhoon_rules:
                program_name = r.assistance.program.name if r.assistance.program else "N/A"
                self.stdout.write(f'  - Rule ID: {r.id}, Assistance: {r.assistance.name}, Program: {program_name}, Is Active: {r.is_active}')
