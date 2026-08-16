import datetime
from django.db.models import Count
from django.utils.dateformat import DateFormat
from collections import defaultdict
from distribution.models import AidClaim

# Shared age bracket definitions (10 brackets)
AGE_BRACKETS = [
    {'label': '0-5 years', 'range': '0-5', 'min_age': 0, 'max_age': 5},
    {'label': '6-12 years', 'range': '6-12', 'min_age': 6, 'max_age': 12},
    {'label': '13-17 years', 'range': '13-17', 'min_age': 13, 'max_age': 17},
    {'label': '18-24 years', 'range': '18-24', 'min_age': 18, 'max_age': 24},
    {'label': '25-34 years', 'range': '25-34', 'min_age': 25, 'max_age': 34},
    {'label': '35-44 years', 'range': '35-44', 'min_age': 35, 'max_age': 44},
    {'label': '45-59 years', 'range': '45-59', 'min_age': 45, 'max_age': 59},
    {'label': '60-69 years', 'range': '60-69', 'min_age': 60, 'max_age': 69},
    {'label': '70-79 years', 'range': '70-79', 'min_age': 70, 'max_age': 79},
    {'label': '80+ years', 'range': '80+', 'min_age': 80, 'max_age': None},
]

def get_age_bracket_index(age):
    """
    Returns the index of the age bracket for a given age.
    Uses the same 10-bracket logic as the dashboard sector/age panel.
    Returns None if age is None.
    """
    if age is None:
        return None
    
    if age <= 5:
        return 0
    elif 6 <= age <= 12:
        return 1
    elif 13 <= age <= 17:
        return 2
    elif 18 <= age <= 24:
        return 3
    elif 25 <= age <= 34:
        return 4
    elif 35 <= age <= 44:
        return 5
    elif 45 <= age <= 59:
        return 6
    elif 60 <= age <= 69:
        return 7
    elif 70 <= age <= 79:
        return 8
    else:
        return 9  # 80+

def get_category_claims_data(barangay=None, start_date=None, end_date=None):
    qs = AidClaim.objects.filter(assistance__isnull=False)
    if barangay:
        qs = qs.filter(family__household__barangay=barangay)
    if start_date:
        qs = qs.filter(claimed_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(claimed_at__date__lte=end_date)
        
    aid_data = (
        qs.values('assistance__aid_category__name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    labels = [item['assistance__aid_category__name'] for item in aid_data]
    data = [item['count'] for item in aid_data]
    
    total_claims = qs.count()
    return labels, data, total_claims

def get_unique_beneficiaries_count(start_date, end_date):
    claims = AidClaim.objects.filter(
        claimed_at__date__gte=start_date,
        claimed_at__date__lte=end_date
    )
    beneficiaries_set = set()
    for claim in claims:
        if claim.family_member_id:
            beneficiaries_set.add(f"member_{claim.family_member_id}")
        else:
            beneficiaries_set.add(f"family_{claim.family_id}")
    return len(beneficiaries_set)


def get_quarterly_report_data(start_date, end_date):
    """
    Returns aggregate counts for the Summary Report.
    Note: "total beneficiaries" represents unique families/individuals served within a month.
    "total claims" represents raw claim count (including repeats).
    """
    claims = AidClaim.objects.filter(
        claimed_at__date__gte=start_date,
        claimed_at__date__lte=end_date
    ).select_related('assistance', 'assistance__aid_category')
    
    # Group by month
    months_data = defaultdict(lambda: {
        'total_beneficiaries_set': set(),
        'total_claims': 0,
        'categories': defaultdict(int)
    })
    
    for claim in claims:
        # e.g., "April 2026"
        month_label = DateFormat(claim.claimed_at).format('F Y')
        
        md = months_data[month_label]
        md['total_claims'] += 1
        
        category_name = claim.assistance.aid_category.name if claim.assistance and claim.assistance.aid_category else 'Uncategorized'
        md['categories'][category_name] += 1
        
        # Determine unique beneficiary identifier
        if claim.family_member_id:
            md['total_beneficiaries_set'].add(f"member_{claim.family_member_id}")
        else:
            md['total_beneficiaries_set'].add(f"family_{claim.family_id}")
            
    # Format results
    result_months = []
    grand_total_claims = 0
    grand_total_beneficiaries_set = set()
    grand_categories = defaultdict(int)
    
    current_date = datetime.date(start_date.year, start_date.month, 1)
    
    while current_date <= end_date:
        month_label = DateFormat(current_date).format('F Y')
        if month_label in months_data:
            md = months_data[month_label]
            total_beneficiaries = len(md['total_beneficiaries_set'])
            
            categories_list = [{'name': name, 'count': count} for name, count in md['categories'].items()]
            categories_list.sort(key=lambda x: x['name'])
            
            result_months.append({
                'month_label': month_label,
                'total_beneficiaries': total_beneficiaries,
                'total_claims': md['total_claims'],
                'categories': categories_list
            })
            
            grand_total_claims += md['total_claims']
            grand_total_beneficiaries_set.update(md['total_beneficiaries_set'])
            for name, count in md['categories'].items():
                grand_categories[name] += count
                
        # Next month
        if current_date.month == 12:
            current_date = datetime.date(current_date.year + 1, 1, 1)
        else:
            current_date = datetime.date(current_date.year, current_date.month + 1, 1)
            
    if start_date.month == end_date.month and start_date.year == end_date.year:
        period_label = f"{DateFormat(start_date).format('F Y')} Monthly Report"
    else:
        quarter = (start_date.month - 1) // 3 + 1
        period_label = f"{quarter}{'st' if quarter==1 else 'nd' if quarter==2 else 'rd' if quarter==3 else 'th'} Quarter Report ({DateFormat(start_date).format('F')} to {DateFormat(end_date).format('F Y')})"
        
    grand_categories_list = [{'name': name, 'count': count} for name, count in grand_categories.items()]
    grand_categories_list.sort(key=lambda x: x['name'])
    
    return {
        'period_label': period_label,
        'months': result_months,
        'totals': {
            'total_beneficiaries': len(grand_total_beneficiaries_set),
            'total_claims': grand_total_claims,
            'categories': grand_categories_list
        }
    }

def get_beneficiary_list_data(start_date, end_date):
    """
    Returns a flat list of individual claim records for the Beneficiary List Report.
    """
    claims = AidClaim.objects.filter(
        claimed_at__date__gte=start_date,
        claimed_at__date__lte=end_date
    ).select_related(
        'family', 
        'family__household', 
        'family__household__barangay',
        'family__household__zone',
        'family_member',
        'assistance',
        'assistance__aid_category'
    ).order_by('claimed_at')
    
    result = []
    for claim in claims:
        if claim.family_member:
            name = f"{claim.family_member.first_name} {claim.family_member.last_name}"
        else:
            name = f"{claim.family.family_name} Family"
            
        barangay = claim.family.household.barangay.name if claim.family.household.barangay else "N/A"
        zone = claim.family.household.zone.name if claim.family.household.zone else "N/A"
        assistance_name = claim.assistance.aid_category.name if claim.assistance and claim.assistance.aid_category else "Uncategorized"
        
        result.append({
            'name': name,
            'barangay': barangay,
            'zone': zone,
            'assistance': assistance_name,
            'claimed_at': claim.claimed_at
        })
        
    return result
