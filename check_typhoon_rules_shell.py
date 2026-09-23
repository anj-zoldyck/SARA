from programs.models import EligibilityRule

typhoon_rules = EligibilityRule.objects.filter(rule_type='ACTIVE_TYPHOON_SIGNAL').select_related('assistance__program')
print(f'Total ACTIVE_TYPHOON_SIGNAL rules found: {typhoon_rules.count()}')
for r in typhoon_rules:
    program_name = r.assistance.program.name if r.assistance.program else "N/A"
    print(f'  - Rule ID: {r.id}, Assistance: {r.assistance.name}, Program: {program_name}, Is Active: {r.is_active}')
