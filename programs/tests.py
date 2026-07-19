from django.test import TestCase
from accounts.models import Barangay
from households.models import Household, Family, FamilyMember, Zone
from programs.models import Program, AidCategory, Assistance, EligibilityRule
from programs.beneficiary_engine import evaluate_household_against_rules, evaluate_family_against_rules, get_eligible_pool
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
