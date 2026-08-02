from django.test import TestCase
from django.urls import reverse
from accounts.models import User, Barangay
from households.models import Household, Zone, Family
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidClaim, AidSchedule
from django.utils import timezone
from datetime import timedelta

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
