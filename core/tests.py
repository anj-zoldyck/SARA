from django.test import TestCase
from django.urls import reverse
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidClaim, AidSchedule
from django.utils import timezone
from datetime import timedelta

class MSWDODashboardTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='mswdo_admin', 
            password='password123', 
            role='MSWDO'
        )
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.household = Household.objects.create(barangay=self.barangay, zone=self.zone, house_number="123 Test St")
        self.family = Family.objects.create(household=self.household, family_name="Tester")
        self.member = FamilyMember.objects.create(family=self.family, first_name="John", last_name="Doe", birthdate="1990-01-01")
        
        self.program = Program.objects.create(name="Test Program")
        self.cat_financial = AidCategory.objects.create(program=self.program, name="Financial")
        self.asst_financial = Assistance.objects.create(program=self.program, aid_category=self.cat_financial, beneficiary_type='INDIVIDUAL')
        
        self.schedule = AidSchedule.objects.create(
            assistance=self.asst_financial, 
            schedule_datetime=timezone.now(),
            location="Plaza"
        )
        AidClaim.objects.create(
            family=self.family,
            family_member=self.member,
            assistance=self.asst_financial,
            schedule=self.schedule,
            claimed_at=timezone.now()
        )
        AidClaim.objects.create(
            family=self.family,
            family_member=self.member,
            assistance=self.asst_financial,
            schedule=self.schedule,
            claimed_at=timezone.now()
        )
        
    def test_mswdo_dashboard_analytics(self):
        self.client.login(username='mswdo_admin', password='password123')
        response = self.client.get(reverse('mswdo_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        self.assertIn("Financial", response.context['analytics_labels'])
        self.assertEqual(sum(response.context['analytics_data']), 2)
        self.assertEqual(response.context['this_month_beneficiaries'], 1)
