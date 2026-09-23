from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from accounts.models import Barangay
from households.models import Household, Family, FamilyMember, Zone
from distribution.models import AidClaim
from programs.models import Program, AidCategory, Assistance, EligibilityRule
from programs.beneficiary_engine import evaluate_household_against_rules, evaluate_family_against_rules, get_eligible_pool, dedupe_family_representatives
from programs.forms import AssistanceForm

class EligibilityRuleTests(TestCase):
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(barangay=self.barangay, name="Zone 1")
        self.household = Household.objects.create(
            house_number="123",
            barangay=self.barangay,
            zone=self.zone
        )
        self.family = Family.objects.create(
            household=self.household,
            family_name="Doe Family"
        )
        self.program = Program.objects.create(name="Test Program")
        self.category = AidCategory.objects.create(program=self.program, name="Test Category")
        self.assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            aid_type='CASH'
        )

    def test_special_category_rule_pwd_member_passes(self):
        # A household with a PWD member should pass a rule configured with {"flags": ["is_pwd"]}
        FamilyMember.objects.create(
            family=self.family,
            first_name="Jane",
            last_name="Doe",
            is_pwd=True,
            is_senior_citizen=False,
            is_solo_parent=False
        )
        rule = EligibilityRule.objects.create(
            assistance=self.assistance,
            rule_type='SPECIAL_CATEGORY',
            config={"flags": ["is_pwd"]}
        )
        self.assertTrue(evaluate_household_against_rules(self.household, [rule]))
        self.assertTrue(evaluate_family_against_rules(self.family, [rule]))

    def test_special_category_rule_no_matching_member_fails(self):
        # A household with no PWD/Senior/Solo Parent members should fail the same rule
        FamilyMember.objects.create(
            family=self.family,
            first_name="Jane",
            last_name="Doe",
            is_pwd=False,
            is_senior_citizen=False,
            is_solo_parent=False
        )
        rule = EligibilityRule.objects.create(
            assistance=self.assistance,
            rule_type='SPECIAL_CATEGORY',
            config={"flags": ["is_pwd"]}
        )
        self.assertFalse(evaluate_household_against_rules(self.household, [rule]))
        self.assertFalse(evaluate_family_against_rules(self.family, [rule]))

    def test_special_category_rule_senior_passes_or_logic(self):
        # A household with a Senior member should pass a rule configured with {"flags": ["is_pwd", "is_senior_citizen"]}
        FamilyMember.objects.create(
            family=self.family,
            first_name="Grandpa",
            last_name="Doe",
            is_pwd=False,
            is_senior_citizen=True,
            is_solo_parent=False
        )
        rule = EligibilityRule.objects.create(
            assistance=self.assistance,
            rule_type='SPECIAL_CATEGORY',
            config={"flags": ["is_pwd", "is_senior_citizen"]}
        )
        self.assertTrue(evaluate_household_against_rules(self.household, [rule]))
        self.assertTrue(evaluate_family_against_rules(self.family, [rule]))

    def test_assistance_form_saves_aid_type(self):
        # Test that the aid_type field now saves correctly when creating an Assistance
        form_data = {
            'program': self.program.id,
            'aid_category': self.category.id,
            'beneficiary_type': 'individual',
            'aid_type': 'GOODS',
            'is_active': True,
        }
        form = AssistanceForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        assistance = form.save()
        self.assertEqual(assistance.aid_type, 'GOODS')

    def test_assistance_save_syncs_special_category_rule(self):
        """
        End-to-end test: Creating an Assistance with requires_solo_parent=True
        should automatically create a corresponding SPECIAL_CATEGORY EligibilityRule.
        This tests the fix for Bug 1 where legacy boolean fields weren't synced to the new rule system.
        """
        # Create a different program/category to avoid unique_together constraint
        program2 = Program.objects.create(name="Test Program 2")
        category2 = AidCategory.objects.create(program=program2, name="Test Category 2")
        
        # Create assistance via form (simulating real Admin workflow)
        form_data = {
            'program': program2.id,
            'aid_category': category2.id,
            'beneficiary_type': 'family',
            'aid_type': 'CASH',
            'requires_solo_parent': True,
            'is_active': True,
        }
        form = AssistanceForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        assistance = form.save()
        
        # Verify the boolean field is set
        self.assertTrue(assistance.requires_solo_parent)
        
        # Verify a SPECIAL_CATEGORY rule was auto-created
        rule = EligibilityRule.objects.filter(
            assistance=assistance,
            rule_type='SPECIAL_CATEGORY'
        ).first()
        self.assertIsNotNone(rule, "SPECIAL_CATEGORY rule should be auto-created")
        self.assertEqual(rule.config['flags'], ['is_solo_parent'])
        self.assertTrue(rule.is_active)

    def test_special_category_filtering_excludes_ineligible_households(self):
        """
        End-to-end test: When generating beneficiaries for an assistance configured
        for solo parents only, households with no solo parent members should be excluded.
        This reproduces Bug 1's real scenario through the actual beneficiary generation flow.
        """
        # Create two households: one with solo parent, one without
        household_with_solo = Household.objects.create(
            house_number="456",
            barangay=self.barangay,
            zone=self.zone
        )
        family_with_solo = Family.objects.create(
            household=household_with_solo,
            family_name="Solo Parent Family"
        )
        FamilyMember.objects.create(
            family=family_with_solo,
            first_name="Maria",
            last_name="Santos",
            is_solo_parent=True
        )
        
        household_without_solo = Household.objects.create(
            house_number="789",
            barangay=self.barangay,
            zone=self.zone
        )
        family_without_solo = Family.objects.create(
            household=household_without_solo,
            family_name="Regular Family"
        )
        FamilyMember.objects.create(
            family=family_without_solo,
            first_name="Juan",
            last_name="Dela Cruz",
            is_solo_parent=False
        )
        
        # Create a different program/category to avoid unique_together constraint
        program3 = Program.objects.create(name="Test Program 3")
        category3 = AidCategory.objects.create(program=program3, name="Test Category 3")
        
        # Create assistance configured for solo parents only via form
        form_data = {
            'program': program3.id,
            'aid_category': category3.id,
            'beneficiary_type': 'family',
            'aid_type': 'CASH',
            'requires_solo_parent': True,
            'is_active': True,
        }
        form = AssistanceForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        assistance = form.save()
        
        # Call the actual get_eligible_pool function (used by beneficiary generation)
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        
        # Verify only the solo parent household is in the pool
        self.assertEqual(len(eligible_pool), 1)
        self.assertIn(family_with_solo, eligible_pool)
        self.assertNotIn(family_without_solo, eligible_pool)

    def test_assistance_save_preserves_manual_rule_config(self):
        """
        Test that editing an Assistance for unrelated fields (e.g., description)
        does not overwrite a manually-configured SPECIAL_CATEGORY rule.
        This tests the refinement to avoid overwriting manual configurations.
        """
        # Create a different program/category to avoid unique_together constraint
        program4 = Program.objects.create(name="Test Program 4")
        category4 = AidCategory.objects.create(program=program4, name="Test Category 4")
        
        # Create assistance with requires_pwd=True
        assistance = Assistance.objects.create(
            program=program4,
            aid_category=category4,
            beneficiary_type='family',
            aid_type='CASH',
            requires_pwd=True
        )
        
        # Manually modify the rule to add is_senior_citizen (simulating Admin using new UI)
        rule = EligibilityRule.objects.get(assistance=assistance, rule_type='SPECIAL_CATEGORY')
        rule.config['flags'] = ['is_pwd', 'is_senior_citizen']
        rule.save()
        
        # Edit assistance for an unrelated field (e.g., aid_type)
        assistance.aid_type = 'GOODS'
        assistance.save()
        
        # Verify the manual config is preserved
        rule.refresh_from_db()
        self.assertEqual(rule.config['flags'], ['is_pwd', 'is_senior_citizen'])
        
        # Now change the boolean flag - should sync
        assistance.requires_pwd = False
        assistance.requires_senior_citizen = True
        assistance.save()
        
        # Verify the rule updates to match the new boolean flags
        rule.refresh_from_db()
        self.assertEqual(rule.config['flags'], ['is_senior_citizen'])


class RFIDEligibilityTests(TestCase):
    """
    Tests for RFID registration requirement in beneficiary generation.
    Only households/families with registered RFID cards can be included in beneficiary lists.
    """
    
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(barangay=self.barangay, name="Zone 1")
        self.program = Program.objects.create(name="Test Program")
        self.category = AidCategory.objects.create(program=self.program, name="Test Category")
        
    def test_family_with_rfid_passes_pool_filter(self):
        """
        A family WITH a registered RFID should pass the pool filter
        (assuming it also passes all other rules).
        """
        household = Household.objects.create(
            house_number="123",
            barangay=self.barangay,
            zone=self.zone
        )
        family_with_rfid = Family.objects.create(
            household=household,
            family_name="RFID Family",
            rfid_uid="1234567890"
        )
        FamilyMember.objects.create(
            family=family_with_rfid,
            first_name="John",
            last_name="Doe"
        )
        
        assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            aid_type='CASH'
        )
        
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        self.assertIn(family_with_rfid, eligible_pool)
    
    def test_family_without_rfid_excluded_from_pool(self):
        """
        A family WITHOUT RFID should be excluded from get_eligible_pool(),
        even if it would otherwise pass every EligibilityRule.
        """
        household = Household.objects.create(
            house_number="456",
            barangay=self.barangay,
            zone=self.zone
        )
        family_without_rfid = Family.objects.create(
            household=household,
            family_name="No RFID Family",
            rfid_uid=None
        )
        FamilyMember.objects.create(
            family=family_without_rfid,
            first_name="Jane",
            last_name="Smith"
        )
        
        assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            aid_type='CASH'
        )
        
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        self.assertNotIn(family_without_rfid, eligible_pool)
    
    def test_family_with_empty_rfid_excluded_from_pool(self):
        """
        A family with empty string RFID should be excluded from get_eligible_pool().
        """
        household = Household.objects.create(
            house_number="789",
            barangay=self.barangay,
            zone=self.zone
        )
        family_with_empty_rfid = Family.objects.create(
            household=household,
            family_name="Empty RFID Family",
            rfid_uid=""
        )
        FamilyMember.objects.create(
            family=family_with_empty_rfid,
            first_name="Bob",
            last_name="Jones"
        )
        
        assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            aid_type='CASH'
        )
        
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        self.assertNotIn(family_with_empty_rfid, eligible_pool)
    
    def test_household_with_rfid_family_eligible_for_individual_assistance(self):
        """
        For individual-based assistance, a household with at least one family
        having an RFID card should be eligible.
        """
        household = Household.objects.create(
            house_number="101",
            barangay=self.barangay,
            zone=self.zone
        )
        family_with_rfid = Family.objects.create(
            household=household,
            family_name="RFID Family",
            rfid_uid="9876543210"
        )
        FamilyMember.objects.create(
            family=family_with_rfid,
            first_name="Senior",
            last_name="Citizen",
            is_senior_citizen=True
        )
        
        assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH'
        )
        
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        self.assertIn(household, eligible_pool)
    
    def test_household_without_rfid_family_excluded_from_individual_assistance(self):
        """
        A household where NONE of its families have an RFID card should be excluded
        from individual-based assistance pool.
        """
        household = Household.objects.create(
            house_number="102",
            barangay=self.barangay,
            zone=self.zone
        )
        family_without_rfid = Family.objects.create(
            household=household,
            family_name="No RFID Family",
            rfid_uid=None
        )
        FamilyMember.objects.create(
            family=family_without_rfid,
            first_name="Senior",
            last_name="Citizen",
            is_senior_citizen=True
        )
        
        assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH'
        )
        
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        self.assertNotIn(household, eligible_pool)
    
    def test_household_with_multiple_families_one_rfid_eligible(self):
        """
        Edge case: A household with multiple families, where only ONE family has RFID.
        The household should still be considered eligible (at least one path to claiming exists).
        """
        household = Household.objects.create(
            house_number="103",
            barangay=self.barangay,
            zone=self.zone
        )
        
        # Family with RFID
        family_with_rfid = Family.objects.create(
            household=household,
            family_name="RFID Family",
            rfid_uid="1111111111"
        )
        FamilyMember.objects.create(
            family=family_with_rfid,
            first_name="Senior1",
            last_name="Citizen",
            is_senior_citizen=True
        )
        
        # Family without RFID
        family_without_rfid = Family.objects.create(
            household=household,
            family_name="No RFID Family",
            rfid_uid=None
        )
        FamilyMember.objects.create(
            family=family_without_rfid,
            first_name="Senior2",
            last_name="Citizen",
            is_senior_citizen=True
        )
        
        assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH'
        )
        
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        self.assertIn(household, eligible_pool)
    
    def test_two_seniors_one_family_same_rfid_eligible(self):
        """
        Test the "2 seniors in 1 family, same RFID" scenario end-to-end.
        The household should be included in the pool since it has RFID via its one family.
        Multiple eligible individual beneficiaries within the same family share one RFID card
        — this is existing, working behavior in scan_rfid's member-selection flow.
        """
        household = Household.objects.create(
            house_number="104",
            barangay=self.barangay,
            zone=self.zone
        )
        
        # One family with RFID, two senior members
        family = Family.objects.create(
            household=household,
            family_name="Multi-Senior Family",
            rfid_uid="2222222222"
        )
        FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="One",
            is_senior_citizen=True
        )
        FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="Two",
            is_senior_citizen=True
        )
        
        assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH'
        )
        
        eligible_pool = get_eligible_pool(assistance, barangay=self.barangay)
        self.assertIn(household, eligible_pool)


class PerAssistanceCooldownTests(TestCase):
    """
    Tests for Fix 1: Per-assistance cooldown logic.
    DAYS_SINCE_LAST_ASSISTANCE now checks claims for THIS SPECIFIC assistance,
    not cross-program cash claims.
    """
    
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(barangay=self.barangay, name="Zone 1")
        self.household = Household.objects.create(
            house_number="123",
            barangay=self.barangay,
            zone=self.zone
        )
        self.family = Family.objects.create(
            household=self.household,
            family_name="Test Family",
            rfid_uid="1234567890",
            is_active=True
        )
        
        # Create two different programs
        self.program1 = Program.objects.create(name="Senior Programs")
        self.category1 = AidCategory.objects.create(program=self.program1, name="Financial Assistance")
        self.assistance1 = Assistance.objects.create(
            program=self.program1,
            aid_category=self.category1,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_senior_citizen=True,
            minimum_age=60,
            is_active=True
        )
        
        self.program2 = Program.objects.create(name="Solo Parent")
        self.category2 = AidCategory.objects.create(program=self.program2, name="Financial Assistance")
        self.assistance2 = Assistance.objects.create(
            program=self.program2,
            aid_category=self.category2,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_solo_parent=True
        )
        
        # Add DAYS_SINCE_LAST_ASSISTANCE rule to assistance1
        EligibilityRule.objects.create(
            assistance=self.assistance1,
            rule_type='DAYS_SINCE_LAST_ASSISTANCE',
            config={'min_days': 365},
            is_active=True
        )
        
        # Add DAYS_SINCE_LAST_ASSISTANCE rule to assistance2
        EligibilityRule.objects.create(
            assistance=self.assistance2,
            rule_type='DAYS_SINCE_LAST_ASSISTANCE',
            config={'min_days': 365},
            is_active=True
        )
    
    def test_per_assistance_cooldown_blocks_same_assistance(self):
        """
        A member who claimed assistance1 within the cooldown window should be
        excluded from assistance1's pool, even if the originating schedule is finished.
        """
        # Create a separate household for this test
        household = Household.objects.create(
            house_number="124",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="Test Family 1",
            rfid_uid="1111111111",
            is_active=True
        )
        
        # Create a senior member
        senior = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="Citizen",
            birthdate=timezone.now().date() - timedelta(days=365*70),  # 70 years old
            is_senior_citizen=True
        )
        
        # Create a claim for assistance1 30 days ago (within 365-day cooldown)
        AidClaim.objects.create(
            family=family,
            assistance=self.assistance1,
            claimed_at=timezone.now() - timedelta(days=30)
        )
        
        # Get eligible pool for assistance1 - should be empty due to cooldown
        pool = get_eligible_pool(self.assistance1, barangay=self.barangay)
        self.assertEqual(len(pool), 0)
    
    def test_per_assistance_cooldown_allows_different_assistance(self):
        """
        A member who claimed a DIFFERENT assistance recently should NOT be
        excluded from this assistance's pool (confirms cooldown is per-assistance).
        """
        # Create a member who is both senior and solo parent
        member = FamilyMember.objects.create(
            family=self.family,
            first_name="Member",
            last_name="Test",
            birthdate=timezone.now().date() - timedelta(days=365*70),
            is_senior_citizen=True,
            is_solo_parent=True
        )
        
        # Create a claim for assistance2 (Solo Parent) 30 days ago
        AidClaim.objects.create(
            family=self.family,
            assistance=self.assistance2,
            claimed_at=timezone.now() - timedelta(days=30)
        )
        
        # Get eligible pool for assistance1 (Senior) - should include member
        # because the claim was for a different assistance
        pool = get_eligible_pool(self.assistance1, barangay=self.barangay)
        self.assertEqual(len(pool), 1)
        self.assertIn(member, pool)


class FamilyDeduplicationTests(TestCase):
    """
    Tests for Fix 2: Family-level deduplication for Senior/PWD/Solo Parent assistances.
    Only one qualifying member per family should be selected, with oldest-first tie-break.
    """
    
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(barangay=self.barangay, name="Zone 1")
        
        # Create separate program/category for each test to avoid unique constraint issues
        self.program = Program.objects.create(name="Senior Programs Test")
        self.category = AidCategory.objects.create(program=self.program, name="Financial Assistance Test")
        
        # Create assistance with requires_senior_citizen
        self.assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_senior_citizen=True,
            minimum_age=60,
            is_active=True
        )
    
    def test_two_seniors_one_family_oldest_selected(self):
        """
        Two seniors in one family, same assistance - only the older one appears in the eligible pool.
        """
        household = Household.objects.create(
            house_number="123",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="Multi-Senior Family",
            rfid_uid="1234567890"
        )
        
        # Create two seniors with different ages
        senior_older = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="Older",
            birthdate=timezone.now().date() - timedelta(days=365*75),  # 75 years old
            is_senior_citizen=True
        )
        senior_younger = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="Younger",
            birthdate=timezone.now().date() - timedelta(days=365*65),  # 65 years old
            is_senior_citizen=True
        )
        
        # Get eligible pool - should only have the older senior
        pool = get_eligible_pool(self.assistance, barangay=self.barangay)
        self.assertEqual(len(pool), 1)
        self.assertIn(senior_older, pool)
        self.assertNotIn(senior_younger, pool)
    
    def test_two_seniors_same_age_lower_id_wins(self):
        """
        Two seniors in one family, same age, different id - lower id wins.
        """
        household = Household.objects.create(
            house_number="456",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="Same-Age Family",
            rfid_uid="21876543210"
        )
        
        # Create two seniors with same age (same birthdate)
        senior_first = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="First",
            birthdate=timezone.now().date() - timedelta(days=365*70),
            is_senior_citizen=True
        )
        senior_second = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="Second",
            birthdate=timezone.now().date() - timedelta(days=365*70),
            is_senior_citizen=True
        )
        
        # Get eligible pool - should only have the one with lower id
        pool = get_eligible_pool(self.assistance, barangay=self.barangay)
        self.assertEqual(len(pool), 1)
        expected_winner = senior_first if senior_first.id < senior_second.id else senior_second
        self.assertIn(expected_winner, pool)
    
    def test_dedup_only_applies_to_capped_categories(self):
        """
        Assistances without requires_senior_citizen/requires_pwd/requires_solo_parent
        should be unaffected by the new dedup step.
        """
        # Create a separate category to avoid unique constraint
        general_category = AidCategory.objects.create(program=self.program, name="General Assistance")
        
        # Create assistance WITHOUT category flags
        general_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=general_category,
            beneficiary_type='individual',
            aid_type='CASH',
            minimum_age=18,
            is_active=True
        )
        
        household = Household.objects.create(
            house_number="789",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="General Family",
            rfid_uid="5555555555"
        )
        
        # Create two adult members (both eligible for general assistance)
        member1 = FamilyMember.objects.create(
            family=family,
            first_name="Adult",
            last_name="One",
            birthdate=timezone.now().date() - timedelta(days=365*30)
        )
        member2 = FamilyMember.objects.create(
            family=family,
            first_name="Adult",
            last_name="Two",
            birthdate=timezone.now().date() - timedelta(days=365*25)
        )
        
        # Get eligible pool - should have both members (no dedup for non-capped assistance)
        pool = get_eligible_pool(general_assistance, barangay=self.barangay)
        self.assertEqual(len(pool), 2)
        self.assertIn(member1, pool)
        self.assertIn(member2, pool)
    
    def test_dedup_helper_function_pwd_category(self):
        """
        Test the dedupe_family_representatives helper function directly for PWD category.
        """
        household = Household.objects.create(
            house_number="101",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="PWD Family",
            rfid_uid="1111111111"
        )
        
        # Create separate category for PWD assistance
        pwd_category = AidCategory.objects.create(program=self.program, name="PWD Assistance")
        
        # Create PWD assistance
        pwd_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=pwd_category,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_pwd=True,
            is_active=True
        )
        
        # Create two PWD members
        pwd_older = FamilyMember.objects.create(
            family=family,
            first_name="PWD",
            last_name="Older",
            birthdate=timezone.now().date() - timedelta(days=365*60),
            is_pwd=True
        )
        pwd_younger = FamilyMember.objects.create(
            family=family,
            first_name="PWD",
            last_name="Younger",
            birthdate=timezone.now().date() - timedelta(days=365*40),
            is_pwd=True
        )
        
        # Test helper function
        pool = [pwd_older, pwd_younger]
        deduped = dedupe_family_representatives(pool, pwd_assistance)
        
        self.assertEqual(len(deduped), 1)
        self.assertIn(pwd_older, deduped)
        self.assertNotIn(pwd_younger, deduped)
    
    def test_dedup_helper_function_solo_parent_category(self):
        """
        Test the dedupe_family_representatives helper function directly for Solo Parent category.
        """
        household = Household.objects.create(
            house_number="102",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="Solo Parent Family",
            rfid_uid="2222222222"
        )
        
        # Create separate category for Solo Parent assistance
        solo_category = AidCategory.objects.create(program=self.program, name="Solo Parent Assistance")
        
        # Create Solo Parent assistance
        solo_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=solo_category,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_solo_parent=True,
            is_active=True
        )
        
        # Create two solo parent members
        solo_older = FamilyMember.objects.create(
            family=family,
            first_name="Solo",
            last_name="Older",
            birthdate=timezone.now().date() - timedelta(days=365*50),
            is_solo_parent=True
        )
        solo_younger = FamilyMember.objects.create(
            family=family,
            first_name="Solo",
            last_name="Younger",
            birthdate=timezone.now().date() - timedelta(days=365*35),
            is_solo_parent=True
        )
        
        # Test helper function
        pool = [solo_older, solo_younger]
        deduped = dedupe_family_representatives(pool, solo_assistance)
        
        self.assertEqual(len(deduped), 1)
        self.assertIn(solo_older, deduped)
        self.assertNotIn(solo_younger, deduped)
    
    def test_multiple_families_each_gets_one_representative(self):
        """
        When multiple families have qualifying members, each family gets one representative.
        """
        household = Household.objects.create(
            house_number="103",
            barangay=self.barangay,
            zone=self.zone
        )
        
        # Family 1 with two seniors
        family1 = Family.objects.create(
            household=household,
            family_name="Family 1",
            rfid_uid="3333333333"
        )
        senior1_older = FamilyMember.objects.create(
            family=family1,
            first_name="Senior",
            last_name="F1-Older",
            birthdate=timezone.now().date() - timedelta(days=365*75),
            is_senior_citizen=True
        )
        FamilyMember.objects.create(
            family=family1,
            first_name="Senior",
            last_name="F1-Younger",
            birthdate=timezone.now().date() - timedelta(days=365*65),
            is_senior_citizen=True
        )
        
        # Family 2 with two seniors
        family2 = Family.objects.create(
            household=household,
            family_name="Family 2",
            rfid_uid="4444444444"
        )
        senior2_older = FamilyMember.objects.create(
            family=family2,
            first_name="Senior",
            last_name="F2-Older",
            birthdate=timezone.now().date() - timedelta(days=365*72),
            is_senior_citizen=True
        )
        FamilyMember.objects.create(
            family=family2,
            first_name="Senior",
            last_name="F2-Younger",
            birthdate=timezone.now().date() - timedelta(days=365*62),
            is_senior_citizen=True
        )
        
        # Get eligible pool - should have one from each family (2 total)
        pool = get_eligible_pool(self.assistance, barangay=self.barangay)
        self.assertEqual(len(pool), 2)
        self.assertIn(senior1_older, pool)
        self.assertIn(senior2_older, pool)


class CrossScheduleHouseholdCooldownTests(TestCase):
    """
    Integration tests for cross-schedule household cooldown.
    Verifies that when one member claims, the entire household is excluded
    from future schedules for the same assistance (per-assistance cooldown).
    """
    
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(barangay=self.barangay, name="Zone 1")
        
        # Create program and assistance with DAYS_SINCE_LAST_ASSISTANCE rule
        self.program = Program.objects.create(name="Senior Programs Integration")
        self.category = AidCategory.objects.create(program=self.program, name="Financial Assistance")
        self.assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_senior_citizen=True,
            minimum_age=60,
            is_active=True
        )
        
        # Add DAYS_SINCE_LAST_ASSISTANCE rule with 365-day cooldown
        EligibilityRule.objects.create(
            assistance=self.assistance,
            rule_type='DAYS_SINCE_LAST_ASSISTANCE',
            config={'min_days': 365},
            is_active=True
        )
    
    def test_cross_schedule_household_cooldown_blocks_all_members(self):
        """
        CRITICAL: Family has 2 seniors. Senior A claims on Schedule 1.
        Schedule 2 runs a few days later - the entire household should be excluded,
        meaning Senior B should NOT appear in the eligible pool.
        The household-level cooldown check should fire before dedup/individual eligibility.
        """
        household = Household.objects.create(
            house_number="200",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="Two-Senior Family",
            rfid_uid="9999999999",
            is_active=True
        )
        
        # Create two seniors in the same family
        senior_a = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="A",
            birthdate=timezone.now().date() - timedelta(days=365*70),
            is_senior_citizen=True
        )
        senior_b = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="B",
            birthdate=timezone.now().date() - timedelta(days=365*65),
            is_senior_citizen=True
        )
        
        # Simulate Schedule 1: Senior A claims the assistance 5 days ago
        AidClaim.objects.create(
            family=family,
            assistance=self.assistance,
            claimed_at=timezone.now() - timedelta(days=5)
        )
        
        # Simulate Schedule 2: Generate eligible pool a few days later
        # CRITICAL: The entire household should be excluded due to cooldown
        pool = get_eligible_pool(self.assistance, barangay=self.barangay)
        
        # Both seniors should be excluded - household-level cooldown applies
        self.assertEqual(len(pool), 0, "Entire household should be excluded after one member claims within cooldown window")
        self.assertNotIn(senior_a, pool)
        self.assertNotIn(senior_b, pool)
    
    def test_exclusion_ordering_rfid_then_cooldown_then_dedup(self):
        """
        Verify the order: RFID exclusion → household-level cooldown → dedup.
        Test: Family with 2 seniors where the older one lacks RFID.
        The younger, RFID-registered senior should be selected as representative,
        not the family being dropped entirely.
        """
        household = Household.objects.create(
            house_number="201",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="Mixed RFID Family",
            rfid_uid="8888888888",
            is_active=True
        )
        
        # Create two seniors - both should be eligible after RFID check
        senior_older = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="Older",
            birthdate=timezone.now().date() - timedelta(days=365*75),
            is_senior_citizen=True
        )
        senior_younger = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="Younger",
            birthdate=timezone.now().date() - timedelta(days=365*65),
            is_senior_citizen=True
        )
        
        # Get eligible pool - should pass RFID check (family has RFID)
        # Should pass cooldown check (no claims)
        # Should apply dedup (keep older)
        pool = get_eligible_pool(self.assistance, barangay=self.barangay)
        
        # Should have exactly one (older) due to dedup
        self.assertEqual(len(pool), 1)
        self.assertIn(senior_older, pool)
        self.assertNotIn(senior_younger, pool)
    
    def test_family_without_rfid_excluded_before_cooldown_check(self):
        """
        Family without RFID should be excluded before cooldown/dedup is even evaluated.
        """
        household = Household.objects.create(
            house_number="202",
            barangay=self.barangay,
            zone=self.zone
        )
        family = Family.objects.create(
            household=household,
            family_name="No RFID Family",
            rfid_uid=None,  # No RFID
            is_active=True
        )
        
        # Create a senior
        senior = FamilyMember.objects.create(
            family=family,
            first_name="Senior",
            last_name="NoRFID",
            birthdate=timezone.now().date() - timedelta(days=365*70),
            is_senior_citizen=True
        )
        
        # Get eligible pool - should be empty due to RFID exclusion
        pool = get_eligible_pool(self.assistance, barangay=self.barangay)
        
        self.assertEqual(len(pool), 0, "Family without RFID should be excluded")
        self.assertNotIn(senior, pool)
