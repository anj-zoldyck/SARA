import random
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Q
from households.models import Household, Family, FamilyMember, FloodProneArea, WeatherSnapshot
from distribution.models import AidClaim
from households.constants import get_tcws_signal

def evaluate_household_against_rules(household, rules):
    """
    Check whether a single Household satisfies ALL active rules attached to
    an Assistance (AND logic across rules). Each rule_type has its own
    evaluation logic below. Returns True/False.

    Why AND across rules: every example given during requirements gathering
    ("Flood AND Senior Citizen", "income below X AND flood-prone") implied
    all selected criteria must hold simultaneously — this matches how a real
    MSWDO caseworker would think about "who qualifies": every condition must
    be true, not just one of many.
    """
    for rule in rules:
        if rule.rule_type == 'INCOME_THRESHOLD':
            # Calculate total household income by summing monthly_income of all members in all families
            total_income = FamilyMember.objects.filter(family__household=household).aggregate(total=Sum('monthly_income'))['total'] or 0
            max_income = rule.config.get('max_income', 0)
            if total_income > max_income:
                return False

        elif rule.rule_type == 'HOUSEHOLD_SIZE_INCOME':
            members_count = FamilyMember.objects.filter(family__household=household).count()
            total_income = FamilyMember.objects.filter(family__household=household).aggregate(total=Sum('monthly_income'))['total'] or 0
            min_members = rule.config.get('min_members', 1)
            max_income = rule.config.get('max_income', 0)
            if members_count < min_members or total_income > max_income:
                return False

        elif rule.rule_type == 'FLOOD_PRONE':
            # Check if household is directly exposed to FLOOD, OR if the zone is flagged as flood-prone.
            # This ensures we catch both specifically flagged homes and general high-risk areas.
            has_flood_exposure = household.hazard_exposure == 'FLOOD'
            in_flood_prone_zone = FloodProneArea.objects.filter(zone=household.zone).exists() if household.zone else False
            if not (has_flood_exposure or in_flood_prone_zone):
                return False

        elif rule.rule_type == 'SPECIAL_CATEGORY':
            flags = rule.config.get('flags', [])
            # Rule specifies flags, members must have AT LEAST ONE of these flags (OR logic within the rule)
            if flags:
                queries = [Q(**{f"{flag}": True}) for flag in flags if flag in ['is_pwd', 'is_solo_parent', 'is_senior_citizen', 'is_indigenous', 'is_out_of_school_youth', 'is_out_of_school_children']]
                if queries:
                    # Combine queries with OR logic
                    query = queries[0]
                    for q in queries[1:]:
                        query |= q
                    # Check if any member in the household satisfies the OR condition
                    has_matching_member = FamilyMember.objects.filter(family__household=household).filter(query).exists()
                    if not has_matching_member:
                        return False
                        
        elif rule.rule_type == 'DAYS_SINCE_LAST_ASSISTANCE':
            # Query AidClaim across ALL assistances for this household's families.
            # This is intentionally a general cooldown (not per-program).
            min_days = rule.config.get('min_days', 0)
            threshold_date = timezone.now() - timedelta(days=min_days)
            # Find the most recent claim tied to this household
            last_claim = AidClaim.objects.filter(family__household=household).order_by('-claimed_at').first()
            if last_claim and last_claim.claimed_at > threshold_date:
                # Claimed too recently, so not eligible
                return False

        elif rule.rule_type == 'ROTATION_ELIGIBILITY':
            # Query the single most recent AidClaim for this household
            last_claim = AidClaim.objects.filter(family__household=household).order_by('-claimed_at').first()
            if last_claim:
                # If they have a prior claim, they are only eligible if the CURRENT assistance's aid_type 
                # is DIFFERENT from their last claim's aid_type.
                if last_claim.assistance.aid_type == rule.assistance.aid_type:
                    return False
            # If there's no prior claim at all, this automatically passes (nothing to rotate away from yet)

        elif rule.rule_type == 'ACTIVE_TYPHOON_SIGNAL':
            # Check the latest WeatherSnapshot
            min_signal = rule.config.get('min_signal', 1)
            snapshot = WeatherSnapshot.objects.filter(fetch_successful=True).order_by('-fetched_at').first()
            if not snapshot:
                # Fails gracefully if no weather data is available
                return False
                
            current_signal = get_tcws_signal(snapshot.current_wind_speed_kmh)
            if not current_signal or current_signal < min_signal:
                return False

    return True

def evaluate_family_against_rules(family, rules):
    """
    Same as above but for Family-based assistance — checks the family's
    household-level rules. 
    
    Family income is computed as the sum of all its members' monthly_income.
    We compute this dynamically by aggregating the monthly_income field of
    all FamilyMember records linked to this family.
    """
    for rule in rules:
        if rule.rule_type == 'INCOME_THRESHOLD':
            # Family income is computed as the sum of all its members' monthly_income
            total_income = family.members.aggregate(total=Sum('monthly_income'))['total'] or 0
            max_income = rule.config.get('max_income', 0)
            if total_income > max_income:
                return False

        elif rule.rule_type == 'HOUSEHOLD_SIZE_INCOME':
            members_count = family.members.count()
            total_income = family.members.aggregate(total=Sum('monthly_income'))['total'] or 0
            min_members = rule.config.get('min_members', 1)
            max_income = rule.config.get('max_income', 0)
            if members_count < min_members or total_income > max_income:
                return False

        elif rule.rule_type == 'FLOOD_PRONE':
            # We check the family's household's exposure and zone
            has_flood_exposure = family.household.hazard_exposure == 'FLOOD'
            in_flood_prone_zone = FloodProneArea.objects.filter(zone=family.household.zone).exists() if family.household.zone else False
            if not (has_flood_exposure or in_flood_prone_zone):
                return False

        elif rule.rule_type == 'SPECIAL_CATEGORY':
            flags = rule.config.get('flags', [])
            if flags:
                queries = [Q(**{f"{flag}": True}) for flag in flags if flag in ['is_pwd', 'is_solo_parent', 'is_senior_citizen', 'is_indigenous', 'is_out_of_school_youth', 'is_out_of_school_children']]
                if queries:
                    query = queries[0]
                    for q in queries[1:]:
                        query |= q
                    has_matching_member = family.members.filter(query).exists()
                    if not has_matching_member:
                        return False
                        
        elif rule.rule_type == 'DAYS_SINCE_LAST_ASSISTANCE':
            # Query AidClaim across ALL assistances for this specific family
            min_days = rule.config.get('min_days', 0)
            threshold_date = timezone.now() - timedelta(days=min_days)
            last_claim = AidClaim.objects.filter(family=family).order_by('-claimed_at').first()
            if last_claim and last_claim.claimed_at > threshold_date:
                return False

        elif rule.rule_type == 'ROTATION_ELIGIBILITY':
            last_claim = AidClaim.objects.filter(family=family).order_by('-claimed_at').first()
            if last_claim:
                if last_claim.assistance.aid_type == rule.assistance.aid_type:
                    return False
            # Automatically passes if no prior claims

        elif rule.rule_type == 'ACTIVE_TYPHOON_SIGNAL':
            min_signal = rule.config.get('min_signal', 1)
            snapshot = WeatherSnapshot.objects.filter(fetch_successful=True).order_by('-fetched_at').first()
            if not snapshot:
                return False
                
            current_signal = get_tcws_signal(snapshot.current_wind_speed_kmh)
            if not current_signal or current_signal < min_signal:
                return False

    return True

def get_eligible_pool(assistance, barangay=None, current_schedule=None):
    """
    Returns the full set of Households or Families (depending on
    assistance.beneficiary_type) that pass ALL active EligibilityRules
    for the given Assistance. This is the pool BEFORE prioritization/slot
    limiting is applied — Phase B will take this pool and narrow it down
    to the actual slot count using the prioritization strategy.
    
    Excludes any household/family already committed to another schedule's
    ACTIVE (unfinished) GeneratedBeneficiaryList to prevent double-allocating
    limited budget slots to the same highest-ranked beneficiaries across
    concurrent distributions.
    """
    from distribution.models import GeneratedBeneficiary
    rules = assistance.eligibility_rules.filter(is_active=True)
    eligible_pool = []
    
    if assistance.beneficiary_type == 'family':
        # Retrieve all families, then evaluate each using the family rules logic
        qs = Family.objects.all()
        if barangay:
            qs = qs.filter(household__barangay=barangay)
            
        # Exclude families on any active schedule's beneficiary list (other than the current one)
        active_entries = GeneratedBeneficiary.objects.filter(
            beneficiary_list__schedule__is_finished=False,
            family__isnull=False
        )
        if current_schedule:
            active_entries = active_entries.exclude(beneficiary_list__schedule=current_schedule)
        excluded_ids = active_entries.values_list('family_id', flat=True)
        qs = qs.exclude(id__in=excluded_ids)
        
        for family in qs:
            if evaluate_family_against_rules(family, rules):
                eligible_pool.append(family)
    else:
        # If assistance is individual-based, we return the eligible Households that match the rules.
        # This groups the eligible individuals by their Household.
        qs = Household.objects.all()
        if barangay:
            qs = qs.filter(barangay=barangay)
            
        # Exclude households on any active schedule's beneficiary list (other than the current one)
        active_entries = GeneratedBeneficiary.objects.filter(
            beneficiary_list__schedule__is_finished=False,
            household__isnull=False
        )
        if current_schedule:
            active_entries = active_entries.exclude(beneficiary_list__schedule=current_schedule)
        excluded_ids = active_entries.values_list('household_id', flat=True)
        qs = qs.exclude(id__in=excluded_ids)
        
        for household in qs:
            if evaluate_household_against_rules(household, rules):
                eligible_pool.append(household)
                
    return eligible_pool

def rank_eligible_pool(pool, strategy):
    """
    Sorts/ranks the eligible pool according to the Assistance's
    prioritization_strategy.
    
    - LOWEST_INCOME_FIRST: sort ascending by household/family income
      (Family income is computed dynamically as the aggregate sum of the monthly_income of all members in the family/household).
    
    - TYPHOON_PRIORITY: rank by vulnerability score (highest first).
      Formula: 
      +1 point if directly flood-exposed or in a flood-prone zone.
      +1 point for each special category condition met by any member (e.g. is_pwd, is_senior_citizen).
      This ensures the most vulnerable and marginalized populations are served first in disaster scenarios.
      
    - RANDOM: shuffle the pool randomly. 
      We use Python's random.shuffle because the pool is already evaluated and loaded into memory as a Python list by get_eligible_pool(). 
      Using Django's .order_by('?') would require sending IDs back to the database and re-evaluating the QuerySet, which is inefficient and slow on large datasets.
    """
    if strategy == 'LOWEST_INCOME_FIRST':
        def get_income(item):
            if isinstance(item, Family):
                return item.members.aggregate(total=Sum('monthly_income'))['total'] or 0
            else:
                return FamilyMember.objects.filter(family__household=item).aggregate(total=Sum('monthly_income'))['total'] or 0
        return sorted(pool, key=get_income)

    elif strategy == 'TYPHOON_PRIORITY':
        def get_vulnerability_score(item):
            score = 0
            household = item.household if isinstance(item, Family) else item
            
            # +1 if directly flood exposed or in a flood-prone zone
            has_flood_exposure = household.hazard_exposure == 'FLOOD'
            in_flood_prone_zone = FloodProneArea.objects.filter(zone=household.zone).exists() if household.zone else False
            if has_flood_exposure or in_flood_prone_zone:
                score += 1
                
            # +1 for each special category flag across all members
            members = item.members.all() if isinstance(item, Family) else FamilyMember.objects.filter(family__household=household)
            for member in members:
                if member.is_pwd: score += 1
                if member.is_senior_citizen: score += 1
                if member.is_solo_parent: score += 1
                if member.is_indigenous: score += 1
                if getattr(member, 'is_out_of_school_youth', False): score += 1
                if getattr(member, 'is_out_of_school_children', False): score += 1
                
            return score
            
        return sorted(pool, key=get_vulnerability_score, reverse=True)

    elif strategy == 'RANDOM':
        shuffled_pool = list(pool)
        random.shuffle(shuffled_pool)
        return shuffled_pool

    # Fallback to returning the original list if strategy is unknown
    return pool

def calculate_slot_count(budget, per_beneficiary_amount):
    """
    Returns the number of beneficiaries that can be funded.
    Uses integer division (floor) since you cannot fund a fractional beneficiary —
    e.g., budget=1,000,000 / per_beneficiary=5,000 = exactly 200,
    but budget=1,000,000 / per_beneficiary=7,500 = 133.33 → floors to 133, leaving
    a remainder unallocated. 
    The remainder is expected and fine, not a bug; the leftover amount simply 
    isn't distributed this cycle.
    """
    if not budget or not per_beneficiary_amount or per_beneficiary_amount <= 0:
        return 0
    return int(budget // per_beneficiary_amount)
