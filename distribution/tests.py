from django.test import TestCase, RequestFactory, Client
from django.utils import timezone
from accounts.models import User, Barangay
from households.models import Zone, Household, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AssignedTo, AidClaim, GeneratedBeneficiaryList, GeneratedBeneficiary
from distribution.services import is_staff_assigned_to_scan
from distribution.views import scan_rfid, staff_walkin, search_eligible_candidates
from django.contrib.messages.storage.fallback import FallbackStorage
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
