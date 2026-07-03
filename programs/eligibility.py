"""
Centralized eligibility rule engine for S.A.R.A. assistance distributions.
Currently, eligibility criteria (age, pwd, solo parent, senior) are primarily 
applied to individual-based assistance. Family-based assistance generally 
relies on the whole family's status.
"""

ELIGIBILITY_CRITERIA = [
    {
        'field': 'requires_pwd',
        'label': 'PWD Only',
        'badge_class': 'acct-badge--pwd',
        'check': lambda member: member.is_pwd,
        'fail_msg': 'Not registered PWD'
    },
    {
        'field': 'requires_solo_parent',
        'label': 'Solo Parent Only',
        'badge_class': 'acct-badge--solo-parent',
        'check': lambda member: member.is_solo_parent,
        'fail_msg': 'Not registered Solo Parent'
    },
    {
        'field': 'requires_senior_citizen',
        'label': 'Senior Only',
        'badge_class': 'acct-badge--senior',
        'check': lambda member: member.is_senior_citizen,
        'fail_msg': 'Not registered Senior Citizen'
    }
]

def check_eligibility(member, assistance):
    """
    Checks if a FamilyMember meets all criteria for an Assistance.
    
    Args:
        member (FamilyMember): The member to check.
        assistance (Assistance): The assistance configuration.
        
    Returns:
        tuple: (is_eligible: bool, reasons: list[str])
    """
    reasons = []
    
    # 1. Minimum Age Check
    if assistance.minimum_age:
        if member.age is None or member.age < assistance.minimum_age:
            reasons.append(f"Under {assistance.minimum_age}")
            
    # 2. Iterate through configurable boolean criteria
    for criteria in ELIGIBILITY_CRITERIA:
        is_required = getattr(assistance, criteria['field'], False)
        if is_required:
            passes = criteria['check'](member)
            if not passes:
                reasons.append(criteria['fail_msg'])
                
    is_eligible = len(reasons) == 0
    return is_eligible, reasons

def get_eligibility_badges(assistance):
    """
    Returns a list of dictionaries with display labels and CSS classes
    for any active requirements on the assistance. Used for frontend badges.
    """
    badges = []
    
    if assistance.minimum_age:
        badges.append({
            'label': f"{assistance.minimum_age}+ yrs",
            'class': 'prog-age-badge'
        })
        
    for criteria in ELIGIBILITY_CRITERIA:
        if getattr(assistance, criteria['field'], False):
            badges.append({
                'label': criteria['label'],
                'class': criteria['badge_class']
            })
            
    return badges
