from django.test import TestCase, RequestFactory
from django.utils import timezone
from accounts.models import User, Barangay
from households.models import Zone, Household, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidSchedule, AssignedTo, AidClaim
from distribution.services import is_staff_assigned_to_scan
from distribution.views import scan_rfid
from django.contrib.messages.storage.fallback import FallbackStorage

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
