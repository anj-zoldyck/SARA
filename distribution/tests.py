from django.test import TestCase, RequestFactory, Client
from django.utils import timezone
from datetime import timedelta
from accounts.models import User, Barangay
from households.models import Zone, Household, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AssignedTo, AidClaim, GeneratedBeneficiaryList, GeneratedBeneficiary, DistributionVenue
from distribution.services import is_staff_assigned_to_scan
from distribution.views import scan_rfid, staff_walkin, search_eligible_candidates, finish_distribution
from django.contrib.messages.storage.fallback import FallbackStorage
from decimal import Decimal
import json

def add_messages(request):
    setattr(request, 'session', 'session')
    messages = FallbackStorage(request)
    setattr(request, '_messages', messages)

class AssignedToTestCase(TestCase):
    def setUp(self):
        # 1. Users
        self.staff1 = User.objects.create_user(username='staff1', email='staff1@test.com', role='MSWDO_STAFF', password='pwd')
        self.staff2 = User.objects.create_user(username='staff2', email='staff2@test.com', role='MSWDO_STAFF', password='pwd')
        
        # 2. Location
        self.barangay_a = Barangay.objects.create(name='Barangay A')
        self.barangay_b = Barangay.objects.create(name='Barangay B')
        
        self.zone_a1 = Zone.objects.create(name='Zone A1', barangay=self.barangay_a)
        self.zone_a2 = Zone.objects.create(name='Zone A2', barangay=self.barangay_a)
        
        # 3. Households and Families
        self.household_a1 = Household.objects.create(
            barangay=self.barangay_a, zone=self.zone_a1, house_number='123 A1', land_use='RESIDENTIAL', hazard_exposure='NONE'
        )
        self.family_a1 = Family.objects.create(household=self.household_a1, family_name='Family A1', rfid_uid='RFID_A1', is_active=True)
        
        self.household_a2 = Household.objects.create(
            barangay=self.barangay_a, zone=self.zone_a2, house_number='456 A2', land_use='RESIDENTIAL', hazard_exposure='NONE'
        )
        self.family_a2 = Family.objects.create(household=self.household_a2, family_name='Family A2', rfid_uid='RFID_A2', is_active=True)
        
        # household_b needs a zone because it's a required foreign key
        self.zone_b = Zone.objects.create(name='Zone B', barangay=self.barangay_b)
        self.household_b = Household.objects.create(
            barangay=self.barangay_b, zone=self.zone_b, house_number='789 B', land_use='RESIDENTIAL', hazard_exposure='NONE'
        )
        self.family_b = Family.objects.create(household=self.household_b, family_name='Family B', rfid_uid='RFID_B', is_active=True)
        
        # 4. Program and Assistance
        self.program = Program.objects.create(name='Relief', description='Relief Program')
        self.category = AidCategory.objects.create(name='Food Pack', program=self.program)
        self.assistance = Assistance.objects.create(
            program=self.program, 
            aid_category=self.category,
            beneficiary_type='family',
            is_active=True
        )
        
        # 5. Active Schedule
        self.schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now(),
            location='Plaza',
            is_active=True,
            is_finished=False
        )
        
        self.factory = RequestFactory()

    def test_no_assignment_schedule_stays_open(self):
        """
        Scenario 4: If a schedule has ZERO assignments, it should be open to ALL staff.
        """
        # Service logic test
        self.assertTrue(is_staff_assigned_to_scan(self.staff1, self.schedule, self.household_a1))
        self.assertTrue(is_staff_assigned_to_scan(self.staff2, self.schedule, self.household_a1))
        
        # View logic test
        request = self.factory.post('/scan/', {'rfid_uid': 'RFID_A1'})
        add_messages(request)
        request.user = self.staff1
        response = scan_rfid(request, self.schedule.id)
        
        # Should succeed and create a claim
        self.assertTrue(AidClaim.objects.filter(family=self.family_a1, schedule=self.schedule).exists())

    def test_assigned_staff_succeeds(self):
        """
        Scenario 1: Staff assigned to the specific barangay+zone succeeds.
        """
        AssignedTo.objects.create(schedule=self.schedule, staff=self.staff1, barangay=self.barangay_a, zone=self.zone_a1)
        
        # Service logic test
        self.assertTrue(is_staff_assigned_to_scan(self.staff1, self.schedule, self.household_a1))
        
        # View logic test
        request = self.factory.post('/scan/', {'rfid_uid': 'RFID_A1'})
        add_messages(request)
        request.user = self.staff1
        response = scan_rfid(request, self.schedule.id)
        
        self.assertTrue(AidClaim.objects.filter(family=self.family_a1, schedule=self.schedule).exists())

    def test_barangay_wide_assignment_works(self):
        """
        Scenario 2: Staff assigned to the barangay (zone=None) can scan for any zone in that barangay.
        """
        # Assign staff1 to Barangay A, zone=None
        AssignedTo.objects.create(schedule=self.schedule, staff=self.staff1, barangay=self.barangay_a, zone=None)
        
        self.assertTrue(is_staff_assigned_to_scan(self.staff1, self.schedule, self.household_a1))
        self.assertTrue(is_staff_assigned_to_scan(self.staff1, self.schedule, self.household_a2))
        self.assertFalse(is_staff_assigned_to_scan(self.staff1, self.schedule, self.household_b))
        
        request = self.factory.post('/scan/', {'rfid_uid': 'RFID_A2'})
        add_messages(request)
        request.user = self.staff1
        response = scan_rfid(request, self.schedule.id)
        
        self.assertTrue(AidClaim.objects.filter(family=self.family_a2, schedule=self.schedule).exists())

    def test_unassigned_staff_blocked(self):
        """
        Scenario 3: If schedule has assignments, unassigned staff or mismatched staff are blocked.
        """
        # Staff1 is assigned to A1
        AssignedTo.objects.create(schedule=self.schedule, staff=self.staff1, barangay=self.barangay_a, zone=self.zone_a1)
        
        # Staff2 has no assignments, should be blocked for A1
        self.assertFalse(is_staff_assigned_to_scan(self.staff2, self.schedule, self.household_a1))
        
        # Staff1 should be blocked for A2 (wrong zone)
        self.assertFalse(is_staff_assigned_to_scan(self.staff1, self.schedule, self.household_a2))
        
        # View test - Staff2 tries to scan A1
        request = self.factory.post('/scan/', {'rfid_uid': 'RFID_A1'})
        add_messages(request)
        request.user = self.staff2
        response = scan_rfid(request, self.schedule.id)
        
        # Should NOT create a claim
        self.assertFalse(AidClaim.objects.filter(family=self.family_a1).exists())
        
        # View test - Staff1 tries to scan A2
        request = self.factory.post('/scan/', {'rfid_uid': 'RFID_A2'})
        add_messages(request)
        request.user = self.staff1
        response = scan_rfid(request, self.schedule.id)
        
        # Should NOT create a claim
        self.assertFalse(AidClaim.objects.filter(family=self.family_a2).exists())

    def test_direct_url_access_blocked_for_unassigned_staff(self):
        """
        Verify that direct URL access (GET request) to a restricted schedule by an unassigned staff member
        returns a 403 Forbidden response.
        """
        # Staff1 is assigned to the schedule
        AssignedTo.objects.create(schedule=self.schedule, staff=self.staff1, barangay=self.barangay_a, zone=self.zone_a1)
        
        # Staff2 has no assignments, attempts to visit the URL directly via GET
        request = self.factory.get(f'/scan/{self.schedule.id}/')
        add_messages(request)
        request.user = self.staff2
        
        # The view should return HttpResponseRedirect (302) to redirect to a dashboard
        response = scan_rfid(request, self.schedule.id)
        self.assertEqual(response.status_code, 302)

    def test_concurrent_same_assistance_schedules(self):
        """
        Scenario 5: Two concurrent active schedules for the SAME Assistance.
        Verify that scans hit the specific explicit schedule and assignments are respected.
        """
        schedule_a = self.schedule
        schedule_a.barangay = self.barangay_a
        schedule_a.save()
        
        schedule_b = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now(),
            location='Plaza B',
            is_active=True,
            is_finished=False,
            barangay=None # all barangays
        )
        
        AssignedTo.objects.create(schedule=schedule_a, staff=self.staff1, barangay=self.barangay_a, zone=self.zone_a1)
        AssignedTo.objects.create(schedule=schedule_b, staff=self.staff2, barangay=self.barangay_b, zone=self.zone_b)
        
        # Staff 1 should be allowed to scan A1 for Schedule A
        self.assertTrue(is_staff_assigned_to_scan(self.staff1, schedule_a, self.household_a1))
        # Staff 1 should be BLOCKED for Schedule B (not assigned)
        self.assertFalse(is_staff_assigned_to_scan(self.staff1, schedule_b, self.household_a1))
        
        # View test - Staff 1 scans for Schedule A
        request_a = self.factory.post('/scan/', {'rfid_uid': 'RFID_A1'})
        add_messages(request_a)
        request_a.user = self.staff1
        response_a = scan_rfid(request_a, schedule_a.id)
        
        # Verify claim exists for Schedule A, but NOT Schedule B
        self.assertTrue(AidClaim.objects.filter(family=self.family_a1, schedule=schedule_a).exists())
        self.assertFalse(AidClaim.objects.filter(family=self.family_a1, schedule=schedule_b).exists())
        
        # View test - Staff 1 tries to scan for Schedule B (should fail assignment)
        request_b = self.factory.post('/scan/', {'rfid_uid': 'RFID_A2'})
        add_messages(request_b)
        request_b.user = self.staff1
        response_b = scan_rfid(request_b, schedule_b.id)
        self.assertFalse(AidClaim.objects.filter(family=self.family_a2, schedule=schedule_b).exists())

class MultiWordNameSearchTestCase(TestCase):
    """
    Test Bug 2 fix: Multi-word name search in staff_walkin should work correctly.
    """
    def setUp(self):
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(name='Zone 1', barangay=self.barangay)
        self.household = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='123',
            land_use='RESIDENTIAL'
        )
        self.family = Family.objects.create(
            household=self.household,
            family_name='Dela Cruz Family',
            is_active=True
        )
        
        # Create members with multi-word names
        self.member1 = FamilyMember.objects.create(
            family=self.family,
            first_name='Juan',
            middle_name='Reyes',
            last_name='Dela Cruz'
        )
        self.member2 = FamilyMember.objects.create(
            family=self.family,
            first_name='Maria',
            middle_name='Santos',
            last_name='Garcia'
        )
        
        self.staff = User.objects.create_user(
            username='staff',
            email='staff@test.com',
            role='MSWDO_STAFF',
            password='pwd'
        )
        self.factory = RequestFactory()

    def test_single_word_search(self):
        """Test that single word searches still work."""
        request = self.factory.get('/staff/walkin/', {'q': 'Juan'})
        request.user = self.staff
        add_messages(request)
        response = staff_walkin(request)
        
        self.assertEqual(response.status_code, 200)
        # Check that Juan is in the context
        self.assertIn('Juan', str(response.content))
        
        request = self.factory.get('/staff/walkin/', {'q': 'Dela'})
        request.user = self.staff
        add_messages(request)
        response = staff_walkin(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dela Cruz', str(response.content))

    def test_multi_word_search_first_last(self):
        """Test that 'Juan Dela Cruz' returns results."""
        request = self.factory.get('/staff/walkin/', {'q': 'Juan Dela Cruz'})
        request.user = self.staff
        add_messages(request)
        response = staff_walkin(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Juan', str(response.content))
        self.assertIn('Dela Cruz', str(response.content))

    def test_multi_word_search_last_first(self):
        """Test that 'Dela Cruz Juan' returns results (word order shouldn't matter)."""
        request = self.factory.get('/staff/walkin/', {'q': 'Dela Cruz Juan'})
        request.user = self.staff
        add_messages(request)
        response = staff_walkin(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Juan', str(response.content))
        self.assertIn('Dela Cruz', str(response.content))

    def test_multi_word_search_middle_name(self):
        """Test that middle name is included in search."""
        request = self.factory.get('/staff/walkin/', {'q': 'Juan Reyes'})
        request.user = self.staff
        add_messages(request)
        response = staff_walkin(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Juan', str(response.content))
        
        request = self.factory.get('/staff/walkin/', {'q': 'Reyes Dela Cruz'})
        request.user = self.staff
        add_messages(request)
        response = staff_walkin(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Dela Cruz', str(response.content))

    def test_search_returns_no_results_for_nonexistent(self):
        """Test that non-existent names return no results."""
        request = self.factory.get('/staff/walkin/', {'q': 'Nonexistent Name'})
        request.user = self.staff
        add_messages(request)
        response = staff_walkin(request)
        
        self.assertEqual(response.status_code, 200)
        # Should not contain any member names
        content_str = str(response.content)
        self.assertNotIn('Juan', content_str)
        self.assertNotIn('Maria', content_str)


class RFIDSearchExclusionTests(TestCase):
    """
    Tests for RFID registration requirement in manual override search (search_eligible_candidates).
    Households/families without RFID should never appear as selectable search results.
    """
    
    def setUp(self):
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(name='Zone 1', barangay=self.barangay)
        
        # Create MSWDO user for authentication
        self.mswdo = User.objects.create_user(
            username='mswdo',
            email='mswdo@test.com',
            role='MSWDO',
            password='pwd'
        )
        
        # Create program and assistance
        self.program = Program.objects.create(name='Test Program')
        self.category = AidCategory.objects.create(program=self.program, name='Test Category')
        
        # Family-based assistance
        self.family_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            aid_type='CASH'
        )
        
        # Individual-based assistance
        self.individual_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH'
        )
        
        # Create schedule with beneficiary list
        self.schedule = AidSchedule.objects.create(
            assistance=self.family_assistance,
            schedule_datetime=timezone.now(),
            location='Plaza',
            is_active=True,
            is_finished=False
        )
        
        # Create beneficiary list
        self.ben_list = GeneratedBeneficiaryList.objects.create(
            schedule=self.schedule,
            generated_by=self.mswdo,
            prioritization_strategy_used='RANDOM'
        )
        
        self.factory = RequestFactory()
    
    def test_family_with_rfid_appears_in_search(self):
        """
        A family WITH RFID should appear in search_eligible_candidates results.
        """
        household = Household.objects.create(
            house_number='123',
            barangay=self.barangay,
            zone=self.zone,
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        family_with_rfid = Family.objects.create(
            household=household,
            family_name='RFID Family',
            rfid_uid='1234567890'
        )
        FamilyMember.objects.create(
            family=family_with_rfid,
            first_name='John',
            last_name='Doe'
        )
        
        # Update schedule to use family assistance
        self.schedule.assistance = self.family_assistance
        self.schedule.save()
        
        request = self.factory.get(f'/search/{self.schedule.id}/', {'q': 'RFID Family'})
        request.user = self.mswdo
        response = search_eligible_candidates(request, self.schedule.id)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['id'], family_with_rfid.id)
    
    def test_family_without_rfid_excluded_from_search(self):
        """
        A family WITHOUT RFID should NOT appear in search_eligible_candidates results,
        even when searched by exact matching name.
        """
        household = Household.objects.create(
            house_number='456',
            barangay=self.barangay,
            zone=self.zone,
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        family_without_rfid = Family.objects.create(
            household=household,
            family_name='No RFID Family',
            rfid_uid=None
        )
        FamilyMember.objects.create(
            family=family_without_rfid,
            first_name='Jane',
            last_name='Smith'
        )
        
        # Update schedule to use family assistance
        self.schedule.assistance = self.family_assistance
        self.schedule.save()
        
        request = self.factory.get(f'/search/{self.schedule.id}/', {'q': 'No RFID Family'})
        request.user = self.mswdo
        response = search_eligible_candidates(request, self.schedule.id)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['results']), 0)
    
    def test_household_with_rfid_family_appears_in_individual_search(self):
        """
        For individual-based assistance, a household with at least one family having RFID
        should appear in search results.
        """
        household = Household.objects.create(
            house_number='101',
            barangay=self.barangay,
            zone=self.zone,
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        family_with_rfid = Family.objects.create(
            household=household,
            family_name='RFID Family',
            rfid_uid='9876543210'
        )
        head_member = FamilyMember.objects.create(
            family=family_with_rfid,
            first_name='Senior',
            last_name='Citizen',
            relationship='HEAD'
        )
        
        # Update schedule to use individual assistance
        self.schedule.assistance = self.individual_assistance
        self.schedule.save()
        
        request = self.factory.get(f'/search/{self.schedule.id}/', {'q': 'Senior Citizen'})
        request.user = self.mswdo
        response = search_eligible_candidates(request, self.schedule.id)
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['id'], household.id)
    
    def test_household_without_rfid_family_excluded_from_individual_search(self):
        """
        A household where NONE of its families have RFID should NOT appear in
        search_eligible_candidates results for individual-based assistance.
        """
        household = Household.objects.create(
            house_number='102',
            barangay=self.barangay,
            zone=self.zone,
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        family_without_rfid = Family.objects.create(
            household=household,
            family_name='No RFID Family',
            rfid_uid=None
        )
        head_member = FamilyMember.objects.create(
            family=family_without_rfid,
            first_name='Senior',
            last_name='Citizen',
            middle_name='NoRFID',
            relationship='HEAD'
        )

        # Update schedule to use individual assistance
        self.schedule.assistance = self.individual_assistance
        self.schedule.save()

        request = self.factory.get(f'/search/{self.schedule.id}/', {'q': 'Senior NoRFID'})
        request.user = self.mswdo
        response = search_eligible_candidates(request, self.schedule.id)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(len(data['results']), 0)


class IndividualBeneficiaryListTargetingTestCase(TestCase):
    """
    Test Bug 1 fix: Individual-based assistance beneficiary lists should target specific members,
    not all members in a household. The kiosk modal should only show members explicitly listed.
    """

    def setUp(self):
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(name='Zone 1', barangay=self.barangay)

        self.household = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='123',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        self.family = Family.objects.create(
            household=self.household,
            family_name='Test Family',
            rfid_uid='TEST_RFID',
            is_active=True
        )

        # Create multiple family members
        from datetime import date
        self.member_senior = FamilyMember.objects.create(
            family=self.family,
            first_name='Senior',
            last_name='Member',
            birthdate=date(1950, 1, 1),
            is_senior_citizen=True
        )
        self.member_adult = FamilyMember.objects.create(
            family=self.family,
            first_name='Adult',
            last_name='Member',
            birthdate=date(1980, 1, 1),
            is_senior_citizen=False
        )
        self.member_child = FamilyMember.objects.create(
            family=self.family,
            first_name='Child',
            last_name='Member',
            birthdate=date(2010, 1, 1),
            is_senior_citizen=False
        )

        self.mswdo = User.objects.create_user(
            username='mswdo',
            email='mswdo@test.com',
            role='MSWDO',
            password='pwd'
        )

        self.program = Program.objects.create(name='Test Program')
        self.category = AidCategory.objects.create(program=self.program, name='Medical')

        # Individual-based assistance with no demographic criteria
        self.individual_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH'
        )

        self.schedule = AidSchedule.objects.create(
            assistance=self.individual_assistance,
            schedule_datetime=timezone.now(),
            location='Plaza',
            is_active=True,
            is_finished=False,
            budget=Decimal('10000'),
            per_beneficiary_amount=Decimal('1000')
        )

        self.factory = RequestFactory()

    def test_beneficiary_list_targets_specific_member(self):
        """
        When a beneficiary list is generated for individual-based assistance,
        only the specific member(s) selected should be eligible in the kiosk modal.
        """
        # Generate beneficiary list - should only select senior member due to age
        ben_list = GeneratedBeneficiaryList.objects.create(
            schedule=self.schedule,
            generated_by=self.mswdo,
            prioritization_strategy_used='LOWEST_INCOME_FIRST'
        )

        # Manually add only the senior member to the list (simulating generation)
        GeneratedBeneficiary.objects.create(
            beneficiary_list=ben_list,
            household=self.household,
            family_member=self.member_senior
        )

        # Simulate RFID scan
        request = self.factory.post(f'/scan/{self.schedule.id}/', {'rfid_uid': 'TEST_RFID'})
        add_messages(request)
        request.user = self.mswdo
        request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'

        response = scan_rfid(request, self.schedule.id)
        data = json.loads(response.content)

        # Should return needs_selection with member data
        self.assertEqual(data['status'], 'needs_selection')
        self.assertEqual(len(data['members']), 3)

        # Check member statuses
        member_statuses = {m['id']: m['status'] for m in data['members']}

        # Senior member should be eligible_unclaimed
        self.assertEqual(member_statuses[self.member_senior.id], 'eligible_unclaimed')

        # Other members should be not_listed
        self.assertEqual(member_statuses[self.member_adult.id], 'not_listed')
        self.assertEqual(member_statuses[self.member_child.id], 'not_listed')

    def test_no_beneficiary_list_allows_generic_eligibility(self):
        """
        When no beneficiary list exists (open/ad-hoc distribution),
        all eligible members should be selectable based on generic eligibility.
        """
        # No beneficiary list created

        # Simulate RFID scan
        request = self.factory.post(f'/scan/{self.schedule.id}/', {'rfid_uid': 'TEST_RFID'})
        add_messages(request)
        request.user = self.mswdo
        request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'

        response = scan_rfid(request, self.schedule.id)
        data = json.loads(response.content)

        # Should return needs_selection with member data
        self.assertEqual(data['status'], 'needs_selection')
        self.assertEqual(len(data['members']), 3)

        # All members should be eligible_unclaimed (no demographic criteria)
        member_statuses = {m['id']: m['status'] for m in data['members']}
        for member_id in member_statuses:
            self.assertEqual(member_statuses[member_id], 'eligible_unclaimed')


class CategoryRestrictedAssistanceTestCase(TestCase):
    """
    Test Bug 2 fix: Category-restricted assistance (senior citizen / solo parent / PWD)
    must only generate a beneficiary pool of that category.
    """

    def setUp(self):
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(name='Zone 1', barangay=self.barangay)

        self.mswdo = User.objects.create_user(
            username='mswdo',
            email='mswdo@test.com',
            role='MSWDO',
            password='pwd'
        )

        self.program = Program.objects.create(name='Test Program')
        self.category = AidCategory.objects.create(program=self.program, name='Senior Assistance')

        # Senior-only assistance
        self.senior_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_senior_citizen=True
        )

        # PWD-only assistance
        self.pwd_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_pwd=True
        )

        self.factory = RequestFactory()

    def test_senior_only_assistance_filters_non_seniors(self):
        """
        When assistance requires senior citizen, only senior members should be in the eligible pool.
        """
        from datetime import date
        from programs.beneficiary_engine import get_eligible_pool

        # Create household with mixed members
        household = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='123',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        family = Family.objects.create(
            household=household,
            family_name='Mixed Family',
            rfid_uid='MIXED_RFID',
            is_active=True
        )

        senior = FamilyMember.objects.create(
            family=family,
            first_name='Senior',
            last_name='Person',
            birthdate=date(1950, 1, 1),
            is_senior_citizen=True
        )
        adult = FamilyMember.objects.create(
            family=family,
            first_name='Adult',
            last_name='Person',
            birthdate=date(1980, 1, 1),
            is_senior_citizen=False
        )

        # Get eligible pool for senior-only assistance
        pool = get_eligible_pool(self.senior_assistance, self.barangay)

        # Pool should contain FamilyMember objects
        pool_ids = [m.id for m in pool]

        # Senior should be in pool
        self.assertIn(senior.id, pool_ids)

        # Adult should NOT be in pool
        self.assertNotIn(adult.id, pool_ids)

    def test_pwd_only_assistance_filters_non_pwd(self):
        """
        When assistance requires PWD, only PWD members should be in the eligible pool.
        """
        from programs.beneficiary_engine import get_eligible_pool

        # Create household with mixed members
        household = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='456',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        family = Family.objects.create(
            household=household,
            family_name='PWD Family',
            rfid_uid='PWD_RFID',
            is_active=True
        )

        pwd_member = FamilyMember.objects.create(
            family=family,
            first_name='PWD',
            last_name='Person',
            is_pwd=True
        )
        non_pwd_member = FamilyMember.objects.create(
            family=family,
            first_name='NonPWD',
            last_name='Person',
            is_pwd=False
        )

        # Get eligible pool for PWD-only assistance
        pool = get_eligible_pool(self.pwd_assistance, self.barangay)

        # Pool should contain FamilyMember objects
        pool_ids = [m.id for m in pool]

        # PWD member should be in pool
        self.assertIn(pwd_member.id, pool_ids)

        # Non-PWD member should NOT be in pool
        self.assertNotIn(non_pwd_member.id, pool_ids)


class PrioritizationStrategyTestCase(TestCase):
    """
    Test new prioritization strategies: DAYS_SINCE_LAST_ASSISTANCE and SPECIAL_CATEGORY.
    """

    def setUp(self):
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(name='Zone 1', barangay=self.barangay)

        self.mswdo = User.objects.create_user(
            username='mswdo',
            email='mswdo@test.com',
            role='MSWDO',
            password='pwd'
        )

        self.program = Program.objects.create(name='Test Program')
        self.category = AidCategory.objects.create(program=self.program, name='Test Category')

        # Family-based assistance for DAYS_SINCE_LAST_ASSISTANCE test
        self.family_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            aid_type='CASH'
        )

        # Senior-only assistance for SPECIAL_CATEGORY test
        self.senior_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='individual',
            aid_type='CASH',
            requires_senior_citizen=True
        )

        from datetime import date

        # Create households/families with different claim histories
        # Household A: never claimed
        self.household_a = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='101',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        self.family_a = Family.objects.create(
            household=self.household_a,
            family_name='Never Claimed Family',
            rfid_uid='RFID_A',
            is_active=True
        )
        FamilyMember.objects.create(
            family=self.family_a,
            first_name='Member',
            last_name='A'
        )

        # Household B: claimed 30 days ago
        self.household_b = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='102',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        self.family_b = Family.objects.create(
            household=self.household_b,
            family_name='Old Claim Family',
            rfid_uid='RFID_B',
            is_active=True
        )
        FamilyMember.objects.create(
            family=self.family_b,
            first_name='Member',
            last_name='B'
        )
        # Create old claim
        old_schedule = AidSchedule.objects.create(
            assistance=self.family_assistance,
            schedule_datetime=timezone.now() - timedelta(days=30),
            location='Old Plaza',
            is_active=True,
            is_finished=True
        )
        AidClaim.objects.create(
            family=self.family_b,
            assistance=self.family_assistance,
            schedule=old_schedule,
            claimed_at=timezone.now() - timedelta(days=30)
        )

        # Household C: claimed 5 days ago
        self.household_c = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='103',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        self.family_c = Family.objects.create(
            household=self.household_c,
            family_name='Recent Claim Family',
            rfid_uid='RFID_C',
            is_active=True
        )
        FamilyMember.objects.create(
            family=self.family_c,
            first_name='Member',
            last_name='C'
        )
        # Create recent claim
        recent_schedule = AidSchedule.objects.create(
            assistance=self.family_assistance,
            schedule_datetime=timezone.now() - timedelta(days=5),
            location='Recent Plaza',
            is_active=True,
            is_finished=True
        )
        AidClaim.objects.create(
            family=self.family_c,
            assistance=self.family_assistance,
            schedule=recent_schedule,
            claimed_at=timezone.now() - timedelta(days=5)
        )

        # Create household with senior member for SPECIAL_CATEGORY test
        self.household_senior = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='201',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        self.family_senior = Family.objects.create(
            household=self.household_senior,
            family_name='Senior Family',
            rfid_uid='RFID_SENIOR',
            is_active=True
        )
        self.senior_member = FamilyMember.objects.create(
            family=self.family_senior,
            first_name='Senior',
            last_name='Person',
            birthdate=date(1950, 1, 1),
            is_senior_citizen=True
        )
        self.non_senior_member = FamilyMember.objects.create(
            family=self.family_senior,
            first_name='Adult',
            last_name='Person',
            birthdate=date(1980, 1, 1),
            is_senior_citizen=False
        )

        self.factory = RequestFactory()

    def test_days_since_last_assistance_ordering(self):
        """
        DAYS_SINCE_LAST_ASSISTANCE should rank never-claimed first, then by oldest claimed_at.
        """
        from programs.beneficiary_engine import get_eligible_pool, rank_eligible_pool

        # Get eligible pool (no eligibility rules, so all families are eligible)
        pool = get_eligible_pool(self.family_assistance, self.barangay)

        # Filter to only include our test families
        test_family_ids = {self.family_a.id, self.family_b.id, self.family_c.id}
        pool = [f for f in pool if f.id in test_family_ids]

        # Rank using DAYS_SINCE_LAST_ASSISTANCE
        ranked_pool = rank_eligible_pool(pool, 'DAYS_SINCE_LAST_ASSISTANCE')

        # Extract family IDs in ranked order
        ranked_ids = [f.id for f in ranked_pool]

        # Never-claimed family should be first
        self.assertEqual(ranked_ids[0], self.family_a.id)

        # Old claim (30 days) should come before recent claim (5 days)
        self.assertEqual(ranked_ids[1], self.family_b.id)
        self.assertEqual(ranked_ids[2], self.family_c.id)

    def test_special_category_stable_ordering(self):
        """
        SPECIAL_CATEGORY should return pool in stable, deterministic order (sorted by ID).
        """
        from programs.beneficiary_engine import get_eligible_pool, rank_eligible_pool

        # Get eligible pool for senior-only assistance
        pool = get_eligible_pool(self.senior_assistance, self.barangay)

        # Pool should only contain senior member
        pool_ids = [m.id for m in pool]
        self.assertIn(self.senior_member.id, pool_ids)
        self.assertNotIn(self.non_senior_member.id, pool_ids)

        # Rank using SPECIAL_CATEGORY
        ranked_pool = rank_eligible_pool(pool, 'SPECIAL_CATEGORY')

        # Should be sorted by ID (stable order)
        ranked_ids = [m.id for m in ranked_pool]
        self.assertEqual(ranked_ids, sorted(ranked_ids))

    def test_schedule_distribution_rejects_special_category_without_flag(self):
        """
        schedule_distribution view should reject SPECIAL_CATEGORY when assistance
        doesn't require any special category flag.
        """
        # Create a different category to avoid unique constraint violation
        regular_category = AidCategory.objects.create(program=self.program, name='Regular Category')
        
        # Create assistance without any special category flags
        regular_assistance = Assistance.objects.create(
            program=self.program,
            aid_category=regular_category,
            beneficiary_type='family',
            aid_type='CASH',
            requires_pwd=False,
            requires_solo_parent=False,
            requires_senior_citizen=False
        )

        # Try to create schedule with SPECIAL_CATEGORY strategy
        request = self.factory.post('/schedule/', {
            'assistance': str(regular_assistance.id),
            'schedule_datetime': (timezone.now() + timedelta(days=1)).isoformat(),
            'location': 'Test Location',
            'enable_selection': 'on',
            'budget': '10000',
            'per_beneficiary_amount': '1000',
            'prioritization_strategy': 'SPECIAL_CATEGORY'
        })
        add_messages(request)
        request.user = self.mswdo

        from distribution.views import schedule_distribution
        response = schedule_distribution(request)

        # Should redirect back with error message
        self.assertEqual(response.status_code, 302)

        # Check that no schedule was created
        self.assertFalse(AidSchedule.objects.filter(
            assistance=regular_assistance,
            prioritization_strategy='SPECIAL_CATEGORY'
        ).exists())

    def test_schedule_distribution_accepts_special_category_with_flag(self):
        """
        schedule_distribution view should accept SPECIAL_CATEGORY when assistance
        requires a special category flag.
        """
        # Try to create schedule with SPECIAL_CATEGORY strategy for senior assistance
        request = self.factory.post('/schedule/', {
            'assistance': str(self.senior_assistance.id),
            'schedule_datetime': (timezone.now() + timedelta(days=1)).isoformat(),
            'location': 'Test Location',
            'enable_selection': 'on',
            'budget': '10000',
            'per_beneficiary_amount': '1000',
            'prioritization_strategy': 'SPECIAL_CATEGORY'
        })
        add_messages(request)
        request.user = self.mswdo

        from distribution.views import schedule_distribution
        response = schedule_distribution(request)

        # Should redirect successfully
        self.assertEqual(response.status_code, 302)

        # Check that schedule was created with SPECIAL_CATEGORY strategy
        schedule = AidSchedule.objects.filter(
            assistance=self.senior_assistance,
            prioritization_strategy='SPECIAL_CATEGORY'
        ).first()
        self.assertIsNotNone(schedule)

    def test_aidschedule_prioritization_strategy_field_roundtrip(self):
        """
        Test that the prioritization_strategy field on AidSchedule round-trips correctly
        through the model and form.
        """
        # Create schedule with each strategy
        strategies = ['LOWEST_INCOME_FIRST', 'TYPHOON_PRIORITY', 'DAYS_SINCE_LAST_ASSISTANCE', 'SPECIAL_CATEGORY']
        
        for strategy in strategies:
            schedule = AidSchedule.objects.create(
                assistance=self.senior_assistance,
                schedule_datetime=timezone.now() + timedelta(days=1),
                location='Test Location',
                budget=Decimal('10000'),
                per_beneficiary_amount=Decimal('1000'),
                prioritization_strategy=strategy
            )
            
            # Reload from database
            schedule.refresh_from_db()
            
            # Verify strategy is preserved
            self.assertEqual(schedule.prioritization_strategy, strategy)
            
            # Clean up
            schedule.delete()


class StaffAssignmentAccessControlTestCase(TestCase):
    """
    Test Bug 3 fix: MSWDO Staff should be consistently blocked from schedules
    not assigned to them across all relevant views.
    """

    def setUp(self):
        self.staff = User.objects.create_user(
            username='staff',
            email='staff@test.com',
            role='MSWDO_STAFF',
            password='pwd'
        )
        self.mswdo = User.objects.create_user(
            username='mswdo',
            email='mswdo@test.com',
            role='MSWDO',
            password='pwd'
        )

        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(name='Zone 1', barangay=self.barangay)

        self.program = Program.objects.create(name='Test Program')
        self.category = AidCategory.objects.create(program=self.program, name='Test Category')
        self.assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            aid_type='CASH'
        )

        # Schedule with NO assignments (open access)
        self.open_schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now(),
            location='Plaza',
            is_active=True,
            is_finished=False
        )

        # Schedule with assignments (restricted)
        self.restricted_schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now(),
            location='Plaza',
            is_active=True,
            is_finished=False
        )
        # Assign staff to a different barangay (not the one they'll try to access)
        other_barangay = Barangay.objects.create(name='Other Barangay')
        other_zone = Zone.objects.create(name='Other Zone', barangay=other_barangay)
        AssignedTo.objects.create(
            schedule=self.restricted_schedule,
            staff=self.staff,
            barangay=other_barangay,
            zone=other_zone
        )

        self.factory = RequestFactory()

    def test_finish_distribution_blocks_unassigned_staff(self):
        """
        MSWDO_STAFF without assignment should be blocked from finish_distribution.
        """
        # Staff tries to finish restricted schedule
        request = self.factory.post(f'/finish/{self.restricted_schedule.id}/')
        add_messages(request)
        request.user = self.staff

        response = finish_distribution(request, self.restricted_schedule.id)

        # Should redirect to staff dashboard
        self.assertEqual(response.status_code, 302)

        # Should NOT finish the schedule
        self.restricted_schedule.refresh_from_db()
        self.assertFalse(self.restricted_schedule.is_finished)

    def test_finish_distribution_allows_assigned_staff(self):
        """
        MSWDO_STAFF with assignment should be allowed to finish_distribution.
        """
        # Assign staff to the restricted schedule's barangay
        AssignedTo.objects.create(
            schedule=self.restricted_schedule,
            staff=self.staff,
            barangay=self.barangay,
            zone=None
        )

        # Staff tries to finish restricted schedule
        request = self.factory.post(f'/finish/{self.restricted_schedule.id}/')
        add_messages(request)
        request.user = self.staff

        response = finish_distribution(request, self.restricted_schedule.id)

        # Should redirect to staff dashboard
        self.assertEqual(response.status_code, 302)

        # Should finish the schedule
        self.restricted_schedule.refresh_from_db()
        self.assertTrue(self.restricted_schedule.is_finished)
        self.assertEqual(self.restricted_schedule.finish_reason, 'FORCED')

    def test_search_eligible_candidates_blocks_unassigned_staff(self):
        """
        MSWDO_STAFF without assignment should be blocked from search_eligible_candidates.
        """
        # Create beneficiary list for restricted schedule
        ben_list = GeneratedBeneficiaryList.objects.create(
            schedule=self.restricted_schedule,
            generated_by=self.mswdo,
            prioritization_strategy_used='RANDOM'
        )

        # Staff tries to search candidates for restricted schedule
        request = self.factory.get(f'/search/{self.restricted_schedule.id}/', {'q': 'test'})
        request.user = self.staff

        response = search_eligible_candidates(request, self.restricted_schedule.id)

        # Should return 403 error
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Access Denied', data['message'])

    def test_search_eligible_candidates_allows_assigned_staff(self):
        """
        MSWDO_STAFF with assignment should be allowed to search_eligible_candidates.
        """
        # Create beneficiary list for restricted schedule
        ben_list = GeneratedBeneficiaryList.objects.create(
            schedule=self.restricted_schedule,
            generated_by=self.mswdo,
            prioritization_strategy_used='RANDOM'
        )

        # Assign staff to the restricted schedule's barangay
        AssignedTo.objects.create(
            schedule=self.restricted_schedule,
            staff=self.staff,
            barangay=self.barangay,
            zone=None
        )

        # Staff tries to search candidates for restricted schedule
        request = self.factory.get(f'/search/{self.restricted_schedule.id}/', {'q': 'test'})
        request.user = self.staff

        response = search_eligible_candidates(request, self.restricted_schedule.id)

        # Should return success (even if no results)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'success')

    def test_open_schedule_allows_any_staff(self):
        """
        Schedules with no assignments should be open to all MSWDO_STAFF.
        """
        # Staff tries to finish open schedule (no assignments)
        request = self.factory.post(f'/finish/{self.open_schedule.id}/')
        add_messages(request)
        request.user = self.staff

        response = finish_distribution(request, self.open_schedule.id)

        # Should succeed
        self.assertEqual(response.status_code, 302)
        self.open_schedule.refresh_from_db()
        self.assertTrue(self.open_schedule.is_finished)


class DistributionVenueCRUDTestCase(TestCase):
    """
    Test DistributionVenue CRUD operations via the venue management views.
    """

    def setUp(self):
        self.mswdo = User.objects.create_user(
            username='mswdo',
            email='mswdo@test.com',
            role='MSWDO',
            password='pwd'
        )
        self.staff = User.objects.create_user(
            username='staff',
            email='staff@test.com',
            role='MSWDO_STAFF',
            password='pwd'
        )
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.factory = RequestFactory()

    def test_venue_list_restricted_to_mswdo_and_staff(self):
        """Venue list should be accessible to MSWDO and MSWDO_STAFF."""
        # MSWDO should have access
        request = self.factory.get('/mswdo/venues/')
        add_messages(request)
        request.user = self.mswdo
        from distribution.views import venue_list
        response = venue_list(request)
        self.assertEqual(response.status_code, 200)

        # Staff should have access
        request = self.factory.get('/mswdo/venues/')
        add_messages(request)
        request.user = self.staff
        response = venue_list(request)
        self.assertEqual(response.status_code, 200)

    def test_venue_add_creates_venue(self):
        """Test creating a new venue via venue_add view."""
        from distribution.views import venue_add
        
        request = self.factory.post('/mswdo/venues/add/', {
            'name': 'Test Venue',
            'latitude': '14.9993',
            'longitude': '120.6117',
            'barangay': self.barangay.id
        })
        add_messages(request)
        request.user = self.mswdo
        response = venue_add(request)
        
        # Should redirect to venue list
        self.assertEqual(response.status_code, 302)
        
        # Verify venue was created
        venue = DistributionVenue.objects.get(name='Test Venue')
        self.assertEqual(venue.latitude, Decimal('14.9993'))
        self.assertEqual(venue.longitude, Decimal('120.6117'))
        self.assertEqual(venue.barangay, self.barangay)
        self.assertTrue(venue.is_active)

    def test_venue_add_without_barangay(self):
        """Test creating a municipal-wide venue (no barangay)."""
        from distribution.views import venue_add
        
        request = self.factory.post('/mswdo/venues/add/', {
            'name': 'Town Plaza',
            'latitude': '14.9993',
            'longitude': '120.6117',
            'barangay': ''
        })
        add_messages(request)
        request.user = self.mswdo
        response = venue_add(request)
        
        self.assertEqual(response.status_code, 302)
        
        venue = DistributionVenue.objects.get(name='Town Plaza')
        self.assertIsNone(venue.barangay)

    def test_venue_edit_updates_venue(self):
        """Test editing an existing venue."""
        from distribution.views import venue_edit
        
        venue = DistributionVenue.objects.create(
            name='Original Name',
            latitude=Decimal('14.9993'),
            longitude=Decimal('120.6117'),
            barangay=self.barangay
        )
        
        request = self.factory.post(f'/mswdo/venues/{venue.id}/edit/', {
            'name': 'Updated Name',
            'latitude': '15.0000',
            'longitude': '120.6200',
            'barangay': self.barangay.id
        })
        add_messages(request)
        request.user = self.mswdo
        response = venue_edit(request, venue.id)
        
        self.assertEqual(response.status_code, 302)
        
        venue.refresh_from_db()
        self.assertEqual(venue.name, 'Updated Name')
        self.assertEqual(venue.latitude, Decimal('15.0000'))
        self.assertEqual(venue.longitude, Decimal('120.6200'))

    def test_venue_deactivate_soft_deletes(self):
        """Test deactivating a venue (soft delete)."""
        from distribution.views import venue_deactivate
        
        venue = DistributionVenue.objects.create(
            name='Test Venue',
            latitude=Decimal('14.9993'),
            longitude=Decimal('120.6117'),
            barangay=self.barangay
        )
        
        request = self.factory.post(f'/mswdo/venues/{venue.id}/deactivate/')
        add_messages(request)
        request.user = self.mswdo
        response = venue_deactivate(request, venue.id)
        
        self.assertEqual(response.status_code, 302)
        
        venue.refresh_from_db()
        self.assertFalse(venue.is_active)
        # Venue should still exist in database
        self.assertTrue(DistributionVenue.objects.filter(id=venue.id).exists())

    def test_venue_activate_reactivates_venue(self):
        """Test reactivating a deactivated venue."""
        from distribution.views import venue_activate
        
        venue = DistributionVenue.objects.create(
            name='Test Venue',
            latitude=Decimal('14.9993'),
            longitude=Decimal('120.6117'),
            barangay=self.barangay,
            is_active=False
        )
        
        request = self.factory.post(f'/mswdo/venues/{venue.id}/activate/')
        add_messages(request)
        request.user = self.mswdo
        response = venue_activate(request, venue.id)
        
        self.assertEqual(response.status_code, 302)
        
        venue.refresh_from_db()
        self.assertTrue(venue.is_active)


class AidScheduleCoordinatesTestCase(TestCase):
    """
    Test AidSchedule saving with location_lat and location_lng coordinates.
    """

    def setUp(self):
        self.mswdo = User.objects.create_user(
            username='mswdo',
            email='mswdo@test.com',
            role='MSWDO',
            password='pwd'
        )
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.program = Program.objects.create(name='Test Program')
        self.category = AidCategory.objects.create(program=self.program, name='Test Category')
        self.assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            is_active=True
        )

    def test_schedule_model_saves_coordinates(self):
        """Test that AidSchedule model can save and retrieve coordinates."""
        schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now() + timedelta(hours=1),
            location='Test Location',
            location_lat=Decimal('14.9993'),
            location_lng=Decimal('120.6117'),
            barangay=self.barangay,
            created_by=self.mswdo
        )
        
        schedule.refresh_from_db()
        self.assertEqual(schedule.location_lat, Decimal('14.9993'))
        self.assertEqual(schedule.location_lng, Decimal('120.6117'))

    def test_schedule_model_without_coordinates(self):
        """Test that AidSchedule can be created without coordinates (legacy compatibility)."""
        schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now() + timedelta(hours=1),
            location='Test Location',
            barangay=self.barangay,
            created_by=self.mswdo
        )
        
        schedule.refresh_from_db()
        self.assertIsNone(schedule.location_lat)
        self.assertIsNone(schedule.location_lng)

    def test_schedule_model_updates_coordinates(self):
        """Test that coordinates can be updated on an existing schedule."""
        schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now() + timedelta(hours=1),
            location='Test Location',
            location_lat=Decimal('14.9993'),
            location_lng=Decimal('120.6117'),
            barangay=self.barangay,
            created_by=self.mswdo
        )
        
        schedule.location_lat = Decimal('15.0000')
        schedule.location_lng = Decimal('120.6200')
        schedule.save()
        
        schedule.refresh_from_db()
        self.assertEqual(schedule.location_lat, Decimal('15.0000'))
        self.assertEqual(schedule.location_lng, Decimal('120.6200'))


class DistributionVenueMigrationTestCase(TestCase):
    """
    Test that the data migration seeds the venues correctly.
    """

    def test_migration_seeds_venues(self):
        """Test that migration 0011_seed_distribution_venues creates 9 venues."""
        # The migration is applied automatically when the test database is created
        # We just need to verify the venues exist
        
        # Verify 9 venues were created
        venue_count = DistributionVenue.objects.count()
        self.assertEqual(venue_count, 9)
        
        # Verify specific venues exist
        venue_names = list(DistributionVenue.objects.values_list('name', flat=True))
        expected_venues = [
            'Santa Rita Town Plaza',
            'Becuran Covered Court',
            'Dila-Dila Sports Center',
            'San Matias Covered Court',
            'Santa Monica Covered Court',
            'San Agustin Covered Court',
            'San Basilio Covered Court',
            'San Isidro Covered Court',
            'San Juan Covered Court'
        ]
        
        for expected in expected_venues:
            self.assertIn(expected, venue_names)
        
        # All venues should be active
        inactive_count = DistributionVenue.objects.filter(is_active=False).count()
        self.assertEqual(inactive_count, 0)


class ReviewBeneficiariesLocationMapTestCase(TestCase):
    """
    Test that the review_beneficiaries page correctly displays the location map
    when coordinates are available, and shows fallback text when they are not.
    """

    def setUp(self):
        """Set up test data for review_beneficiaries tests."""
        from accounts.models import User, Barangay
        from programs.models import AidCategory, Program, Assistance
        from distribution.models import AidSchedule, GeneratedBeneficiaryList
        
        # Create MSWDO user
        self.mswdo_user = User.objects.create_user(
            username='mswdo_user',
            password='testpass123',
            role='MSWDO',
            first_name='MSWDO',
            last_name='User'
        )
        
        # Create barangay
        self.barangay = Barangay.objects.create(name='Test Barangay')
        
        # Create program, aid category, and assistance
        self.program = Program.objects.create(name='Test Program')
        self.aid_category = AidCategory.objects.create(name='Food Assistance', program=self.program)
        self.assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.aid_category,
            beneficiary_type='family',
            requires_pwd=False,
            requires_senior_citizen=False,
            requires_solo_parent=False
        )
        
        # Create schedule with coordinates
        self.schedule_with_coords = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now() + timedelta(days=7),
            location='Santa Rita Town Plaza',
            location_lat=Decimal('15.000282968104935'),
            location_lng=Decimal('120.61762685746417'),
            budget=Decimal('50000'),
            per_beneficiary_amount=Decimal('500'),
            created_by=self.mswdo_user
        )
        
        # Create beneficiary list for schedule with coords
        self.ben_list_with_coords = GeneratedBeneficiaryList.objects.create(
            schedule=self.schedule_with_coords,
            prioritization_strategy_used='LOWEST_INCOME_FIRST'
        )
        
        # Create schedule without coordinates (legacy)
        self.schedule_without_coords = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now() + timedelta(days=14),
            location='Municipal Hall (legacy entry)',
            location_lat=None,
            location_lng=None,
            budget=Decimal('30000'),
            per_beneficiary_amount=Decimal('300'),
            created_by=self.mswdo_user
        )
        
        # Create beneficiary list for schedule without coords
        self.ben_list_without_coords = GeneratedBeneficiaryList.objects.create(
            schedule=self.schedule_without_coords,
            prioritization_strategy_used='LOWEST_INCOME_FIRST'
        )

    def test_review_beneficiaries_with_coordinates_shows_map(self):
        """Test that review_beneficiaries shows map when coordinates are present."""
        self.client.force_login(self.mswdo_user)
        
        response = self.client.get(f'/mswdo/schedule/{self.schedule_with_coords.id}/beneficiaries/')
        
        self.assertEqual(response.status_code, 200)
        
        # Check that the location map div is present
        self.assertContains(response, 'locationMap')
        
        # Check that the Open in Maps link is present
        self.assertContains(response, 'Open in Maps')
        
        # Check that the fallback message is NOT present
        self.assertNotContains(response, 'Map location not available for this schedule')

    def test_review_beneficiaries_without_coordinates_shows_fallback(self):
        """Test that review_beneficiaries shows fallback text when coordinates are missing."""
        self.client.force_login(self.mswdo_user)
        
        response = self.client.get(f'/mswdo/schedule/{self.schedule_without_coords.id}/beneficiaries/')
        
        self.assertEqual(response.status_code, 200)
        
        # Check that the location map div is NOT present
        self.assertNotContains(response, 'id="locationMap"')
        
        # Check that the fallback message is present
        self.assertContains(response, 'Map location not available for this schedule')
        
        # Check that the Open in Maps link is NOT present
        self.assertNotContains(response, 'Open in Maps')
        
        # Check that the location text is still shown
        self.assertContains(response, self.schedule_without_coords.location)

    def test_review_beneficiaries_open_in_maps_url_format(self):
        """Test that the Open in Maps URL has the correct format."""
        self.client.force_login(self.mswdo_user)
        
        response = self.client.get(f'/mswdo/schedule/{self.schedule_with_coords.id}/beneficiaries/')
        
        self.assertEqual(response.status_code, 200)
        
        # Check that the Open in Maps link is present
        self.assertContains(response, 'Open in Maps')
        
        # Check that the Google Maps URL pattern is present
        self.assertContains(response, 'google.com/maps/dir/')

class WalkinReactivateFamilyTestCase(TestCase):
    """
    Test functionality for the reactivate-family view.
    """
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_test',
            email='stafftest@test.com',
            role='MSWDO_STAFF',
            password='pwd'
        )
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(name='Zone 1', barangay=self.barangay)
        self.household = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='123',
            land_use='RESIDENTIAL'
        )
        self.family = Family.objects.create(
            household=self.household,
            family_name='Archived Family',
            rfid_uid='ARCHIVED_RFID',
            is_active=True,
            is_archived=True
        )

    def test_reactivate_family_success(self):
        self.client.force_login(self.staff_user)
        
        # enforce_csrf_checks is False by default in test Client, ensuring view processing is fine.
        response = self.client.post(
            '/staff/walkin/reactivate-family/',
            {'family_id': self.family.id},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        
        self.family.refresh_from_db()
        self.assertFalse(self.family.is_archived)
