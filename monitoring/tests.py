from django.test import TestCase
from django.urls import reverse
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidClaim, AidSchedule
from django.utils import timezone
from datetime import timedelta, date

class BarangayAnalyticsTest(TestCase):
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.user = User.objects.create_user(
            username='barangay_admin', 
            password='password123', 
            role='BARANGAY',
            barangay=self.barangay
        )
        self.other_barangay = Barangay.objects.create(name="Other Barangay")
        
        self.zone = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.household = Household.objects.create(barangay=self.barangay, zone=self.zone, house_number="123 Test St")
        self.family = Family.objects.create(household=self.household, family_name="Tester")
        
        self.other_household = Household.objects.create(barangay=self.other_barangay, house_number="456 Other St")
        self.other_family = Family.objects.create(household=self.other_household, family_name="OtherTester")
        
        self.program = Program.objects.create(name="Test Program")
        
        self.cat_financial = AidCategory.objects.create(program=self.program, name="Financial")
        self.cat_medical = AidCategory.objects.create(program=self.program, name="Medical")
        
        self.asst_financial = Assistance.objects.create(program=self.program, aid_category=self.cat_financial, beneficiary_type='FAMILY')
        self.asst_medical = Assistance.objects.create(program=self.program, aid_category=self.cat_medical, beneficiary_type='FAMILY')
        
        self.schedule = AidSchedule.objects.create(
            assistance=self.asst_financial, 
            schedule_datetime=timezone.now() + timedelta(days=1),
            location="Plaza"
        )
        
        AidClaim.objects.create(
            family=self.family,
            assistance=self.asst_financial,
            schedule=self.schedule,
            claimed_at=timezone.now()
        )
        AidClaim.objects.create(
            family=self.family,
            assistance=self.asst_medical,
            schedule=self.schedule,
            claimed_at=timezone.now()
        )
        
        # Claim in other barangay
        AidClaim.objects.create(
            family=self.other_family,
            assistance=self.asst_medical,
            schedule=self.schedule,
            claimed_at=timezone.now()
        )
        
    def test_barangay_analytics_view(self):
        self.client.login(username='barangay_admin', password='password123')
        response = self.client.get(reverse('barangay_analytics'))
        
        self.assertEqual(response.status_code, 200)
        
        labels = response.context['labels']
        data = response.context['data']
        
        self.assertIn("Financial", labels)
        self.assertIn("Medical", labels)
        self.assertNotIn("RELIEF", labels)
        self.assertEqual(sum(data), 2)
        
    def test_barangay_dashboard_view(self):
        self.client.login(username='barangay_admin', password='password123')
        response = self.client.get(reverse('barangay_dashboard'))
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('analytics_labels', response.context)
        self.assertIn('analytics_data', response.context)
        self.assertIn('total_claims', response.context)
        
        self.assertEqual(response.context['total_claims'], 2)
        self.assertIn("Financial", response.context['analytics_labels'])


class AnalyticsAPITest(TestCase):
    def setUp(self):
        # Create MSWDO user
        self.mswdo_user = User.objects.create_user(
            username='mswdo',
            password='password123',
            role='MSWDO'
        )
        
        # Create test data
        self.barangay1 = Barangay.objects.create(name="Barangay 1")
        self.barangay2 = Barangay.objects.create(name="Barangay 2")
        
        self.zone1 = Zone.objects.create(name="Zone 1", barangay=self.barangay1)
        self.household1 = Household.objects.create(barangay=self.barangay1, zone=self.zone1, house_number="123")
        self.family1 = Family.objects.create(household=self.household1, family_name="Family1")
        
        # Create family member for individual-based claims
        from datetime import date
        self.member1 = FamilyMember.objects.create(
            family=self.family1,
            first_name="John",
            last_name="Doe",
            sex='M',
            birthdate=date.today() - timedelta(days=30 * 12),  # 30 years old
            relationship='HEAD'
        )
        
        self.zone2 = Zone.objects.create(name="Zone 2", barangay=self.barangay2)
        self.household2 = Household.objects.create(barangay=self.barangay2, zone=self.zone2, house_number="456")
        self.family2 = Family.objects.create(household=self.household2, family_name="Family2")
        
        self.program = Program.objects.create(name="Test Program", is_active=True)
        self.cat_relief = AidCategory.objects.create(program=self.program, name="Relief", is_active=True)
        self.cat_medical = AidCategory.objects.create(program=self.program, name="Medical", is_active=True)
        
        self.asst_relief_family = Assistance.objects.create(
            program=self.program,
            aid_category=self.cat_relief,
            beneficiary_type='FAMILY',
            is_active=True
        )
        self.asst_medical_individual = Assistance.objects.create(
            program=self.program,
            aid_category=self.cat_medical,
            beneficiary_type='INDIVIDUAL',
            is_active=True
        )
        
        # Create schedule with per_beneficiary_amount
        self.schedule = AidSchedule.objects.create(
            assistance=self.asst_relief_family,
            schedule_datetime=timezone.now(),
            location="Plaza",
            per_beneficiary_amount=500.00,
            budget=5000.00
        )
        
        # Create claims with amounts
        self.claim1 = AidClaim.objects.create(
            family=self.family1,
            assistance=self.asst_relief_family,
            schedule=self.schedule,
            claimed_at=timezone.now(),
            amount=500.00,
            claim_type='DISTRIBUTION'
        )
        
        self.claim2 = AidClaim.objects.create(
            family=self.family1,
            family_member=self.member1,
            assistance=self.asst_medical_individual,
            schedule=self.schedule,
            claimed_at=timezone.now(),
            amount=300.00,
            claim_type='DISTRIBUTION'
        )
        
        # Walk-in claim with amount
        self.claim3 = AidClaim.objects.create(
            family=self.family1,
            family_member=self.member1,
            assistance=self.asst_medical_individual,
            schedule=None,
            claimed_at=timezone.now(),
            amount=200.00,
            claim_type='WALK_IN'
        )
        
        # Claim in other barangay
        self.claim4 = AidClaim.objects.create(
            family=self.family2,
            assistance=self.asst_relief_family,
            schedule=self.schedule,
            claimed_at=timezone.now(),
            amount=500.00,
            claim_type='DISTRIBUTION'
        )
    
    def test_analytics_api_no_filters(self):
        """Test API with no filters returns all data"""
        self.client.force_login(self.mswdo_user)
        response = self.client.get(reverse('analytics_api'))
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Check KPIs
        self.assertEqual(data['kpis']['total_claims'], 4)
        self.assertEqual(data['kpis']['unique_beneficiaries'], 3)  # family1, member1, family2
        self.assertEqual(float(data['kpis']['total_aid_released']), 1300.00)  # Only DISTRIBUTION claims
        self.assertEqual(data['kpis']['walkin_count'], 1)
        self.assertEqual(data['kpis']['programs_with_claims'], 1)
        self.assertEqual(data['kpis']['barangays_covered'], 2)
        
        # Check claims by aid type
        self.assertEqual(len(data['claims_by_aid_type']), 2)
        
        # Check filter options are present
        self.assertIn('aid_categories', data['filter_options'])
        self.assertIn('programs', data['filter_options'])
        self.assertIn('barangays', data['filter_options'])
        self.assertIn('age_brackets', data['filter_options'])
    
    def test_analytics_api_with_barangay_filter(self):
        """Test API with barangay filter"""
        self.client.force_login(self.mswdo_user)
        response = self.client.get(reverse('analytics_api'), {'barangay': self.barangay1.id})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data['kpis']['total_claims'], 3)  # Only barangay1 claims
        self.assertEqual(data['kpis']['barangays_covered'], 1)
    
    def test_analytics_api_with_date_filter(self):
        """Test API with date range filter"""
        self.client.force_login(self.mswdo_user)
        
        # Filter for today only
        today_str = date.today().strftime('%Y-%m-%d')
        response = self.client.get(reverse('analytics_api'), {
            'date_from': today_str,
            'date_to': today_str
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # All claims were created today
        self.assertEqual(data['kpis']['total_claims'], 4)
    
    def test_analytics_api_with_gender_filter(self):
        """Test API with gender filter"""
        self.client.force_login(self.mswdo_user)
        response = self.client.get(reverse('analytics_api'), {'gender': 'M'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Only claims with family_member and male gender
        # claim2 and claim3 have member1 (male)
        self.assertEqual(data['kpis']['total_claims'], 2)
    
    def test_analytics_api_unique_beneficiaries_no_double_count(self):
        """Test that unique beneficiaries are not double-counted"""
        self.client.force_login(self.mswdo_user)
        
        # Add another claim for the same family (family-based)
        AidClaim.objects.create(
            family=self.family1,
            assistance=self.asst_relief_family,
            schedule=self.schedule,
            claimed_at=timezone.now(),
            amount=500.00,
            claim_type='DISTRIBUTION'
        )
        
        response = self.client.get(reverse('analytics_api'))
        data = response.json()
        
        # Should still be 3 unique beneficiaries (family1, member1, family2)
        # even though family1 now has 4 claims
        self.assertEqual(data['kpis']['total_claims'], 5)
        self.assertEqual(data['kpis']['unique_beneficiaries'], 3)
    
    def test_analytics_view_renders_template(self):
        """Test that the analytics view renders the template"""
        self.client.force_login(self.mswdo_user)
        response = self.client.get(reverse('analytics'))
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'monitoring/analytics.html')
