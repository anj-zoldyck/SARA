from django.test import TestCase
from django.urls import reverse
from accounts.models import User, Barangay
from households.models import Household, Zone, Family, FamilyMember
from programs.models import Program, AidCategory, Assistance
from distribution.models import AidClaim, AidSchedule
from core.models import AuditLog
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


class AuditLogAccessControlTest(TestCase):
    """Feature 1: Test audit log access control - MSWDO only"""
    
    def setUp(self):
        self.mswdo = User.objects.create_user(username='mswdo', password='pass', role='MSWDO')
        self.staff = User.objects.create_user(username='staff', password='pass', role='MSWDO_STAFF')
        self.barangay = User.objects.create_user(username='barangay', password='pass', role='BARANGAY')
    
    def test_audit_log_mswdo_access_allowed(self):
        self.client.login(username='mswdo', password='pass')
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 200)
    
    def test_audit_log_staff_access_denied(self):
        self.client.login(username='staff', password='pass')
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 403)
    
    def test_audit_log_barangay_access_denied(self):
        self.client.login(username='barangay', password='pass')
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 403)
    
    def test_audit_log_anonymous_access_denied(self):
        response = self.client.get(reverse('audit_log'))
        self.assertEqual(response.status_code, 302)  # Redirect to login


class AuditLogEventLoggingTest(TestCase):
    """Feature 1: Test audit log event creation"""
    
    def setUp(self):
        self.mswdo = User.objects.create_user(username='mswdo', password='pass', role='MSWDO')
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.household = Household.objects.create(barangay=self.barangay, zone=self.zone, house_number="123 Test St")
        self.family = Family.objects.create(household=self.household, family_name="Tester")
        self.member = FamilyMember.objects.create(family=self.family, first_name="John", last_name="Doe", birthdate="1990-01-01")
        self.program = Program.objects.create(name="Test Program")
        self.cat_financial = AidCategory.objects.create(program=self.program, name="Financial")
        self.asst_financial = Assistance.objects.create(program=self.program, aid_category=self.cat_financial, beneficiary_type='INDIVIDUAL')
    
    def test_login_success_logged(self):
        response = self.client.post(reverse('login'), {'username': 'mswdo', 'password': 'pass'})
        self.assertEqual(AuditLog.objects.filter(action_type='LOGIN_SUCCESS').count(), 1)
    
    def test_login_failure_logged(self):
        response = self.client.post(reverse('login'), {'username': 'mswdo', 'password': 'wrong'})
        self.assertEqual(AuditLog.objects.filter(action_type='LOGIN_FAILURE').count(), 1)
    
    def test_schedule_creation_logged(self):
        self.client.login(username='mswdo', password='pass')
        response = self.client.post(reverse('schedule_distribution'), {
            'assistance': self.asst_financial.id,
            'schedule_datetime': (timezone.now() + timedelta(days=1)).isoformat(),
            'location': 'Test Location',
            'enable_selection': 'off'
        })
        self.assertEqual(AuditLog.objects.filter(action_type='SCHEDULE_CREATED').count(), 1)
    
    def test_user_creation_logged(self):
        self.client.login(username='mswdo', password='pass')
        response = self.client.post(reverse('create_user'), {
            'username': 'newuser',
            'first_name': 'New',
            'last_name': 'User',
            'role': 'MSWDO_STAFF',
            'barangay': self.barangay.id
        })
        self.assertEqual(AuditLog.objects.filter(action_type='USER_CREATED').count(), 1)


class ScheduleMetadataTest(TestCase):
    """Feature 2: Test AidSchedule metadata fields and staff visibility"""
    
    def setUp(self):
        self.mswdo = User.objects.create_user(username='mswdo', password='pass', role='MSWDO')
        self.staff = User.objects.create_user(username='staff', password='pass', role='MSWDO_STAFF')
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.household = Household.objects.create(barangay=self.barangay, zone=self.zone, house_number="123 Test St")
        self.family = Family.objects.create(household=self.household, family_name="Tester")
        self.member = FamilyMember.objects.create(family=self.family, first_name="John", last_name="Doe", birthdate="1990-01-01")
        self.program = Program.objects.create(name="Test Program")
        self.cat_financial = AidCategory.objects.create(program=self.program, name="Financial")
        self.asst_financial = Assistance.objects.create(program=self.program, aid_category=self.cat_financial, beneficiary_type='INDIVIDUAL')
    
    def test_schedule_has_metadata_fields(self):
        schedule = AidSchedule.objects.create(
            assistance=self.asst_financial,
            schedule_datetime=timezone.now(),
            location="Test",
            created_by=self.mswdo
        )
        self.assertIsNotNone(schedule.created_by)
        self.assertIsNotNone(schedule.created_at)
        self.assertIsNotNone(schedule.updated_at)
        self.assertIsNone(schedule.last_edited_by)  # Not edited yet
    
    def test_schedule_creation_sets_created_by(self):
        self.client.login(username='mswdo', password='pass')
        response = self.client.post(reverse('schedule_distribution'), {
            'assistance': self.asst_financial.id,
            'schedule_datetime': (timezone.now() + timedelta(days=1)).isoformat(),
            'location': 'Test Location',
            'enable_selection': 'off'
        })
        schedule = AidSchedule.objects.first()
        self.assertEqual(schedule.created_by, self.mswdo)
    
    def test_schedule_edit_sets_last_edited_by(self):
        schedule = AidSchedule.objects.create(
            assistance=self.asst_financial,
            schedule_datetime=timezone.now(),
            location="Test",
            created_by=self.mswdo
        )
        self.client.login(username='mswdo', password='pass')
        response = self.client.post(reverse('edit_schedule', args=[schedule.id]), {
            'assistance': self.asst_financial.id,
            'schedule_datetime': (timezone.now() + timedelta(days=1)).isoformat(),
            'location': 'Updated Location',
            'enable_selection': 'off'
        })
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_edited_by, self.mswdo)


class BarangayDashboardLocationMapTest(TestCase):
    """Test location map modal functionality on barangay dashboard"""
    
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.barangay_user = User.objects.create_user(
            username='barangay_admin',
            password='password123',
            role='BARANGAY',
            barangay=self.barangay
        )
        self.zone = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.program = Program.objects.create(name="Test Program")
        self.cat_financial = AidCategory.objects.create(program=self.program, name="Financial")
        self.asst_financial = Assistance.objects.create(
            program=self.program,
            aid_category=self.cat_financial,
            beneficiary_type='INDIVIDUAL'
        )
        
    def test_barangay_schedule_status_includes_location_fields(self):
        """Test that barangay_schedule_status JSON includes id, location_lat, location_lng"""
        self.client.login(username='barangay_admin', password='password123')
        
        # Create schedule with coordinates
        schedule_with_coords = AidSchedule.objects.create(
            assistance=self.asst_financial,
            schedule_datetime=timezone.now() + timedelta(hours=1),
            location="Test Location",
            location_lat=15.1234567,
            location_lng=120.9876543,
            barangay=self.barangay
        )
        
        # Create schedule without coordinates
        schedule_without_coords = AidSchedule.objects.create(
            assistance=self.asst_financial,
            schedule_datetime=timezone.now() + timedelta(hours=2),
            location="Test Location 2",
            barangay=self.barangay
        )
        
        response = self.client.get(reverse('barangay_schedule_status'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Check upcoming schedules (both should be in upcoming since they're in the future)
        upcoming = data['upcoming']
        self.assertEqual(len(upcoming), 2)
        
        # Find schedule with coordinates
        sched_with_coords = next((s for s in upcoming if s['id'] == schedule_with_coords.id), None)
        self.assertIsNotNone(sched_with_coords)
        self.assertEqual(sched_with_coords['location_lat'], 15.1234567)
        self.assertEqual(sched_with_coords['location_lng'], 120.9876543)
        self.assertEqual(sched_with_coords['location'], "Test Location")
        
        # Find schedule without coordinates
        sched_without_coords = next((s for s in upcoming if s['id'] == schedule_without_coords.id), None)
        self.assertIsNotNone(sched_without_coords)
        self.assertIsNone(sched_without_coords['location_lat'])
        self.assertIsNone(sched_without_coords['location_lng'])
        self.assertEqual(sched_without_coords['location'], "Test Location 2")
    
    def test_barangay_dashboard_has_location_modal(self):
        """Test that barangay dashboard includes location modal HTML"""
        self.client.login(username='barangay_admin', password='password123')
        response = self.client.get(reverse('barangay_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        # Check for location modal
        self.assertIn('id="locationModal"', response.content.decode())
        self.assertIn('locationMap', response.content.decode())
    
    def test_barangay_dashboard_cards_have_data_attributes(self):
        """Test that server-rendered schedule cards have location data attributes"""
        self.client.login(username='barangay_admin', password='password123')
        
        # Create schedule with coordinates
        schedule = AidSchedule.objects.create(
            assistance=self.asst_financial,
            schedule_datetime=timezone.now() + timedelta(hours=1),
            location="Test Location",
            location_lat=15.1234567,
            location_lng=120.9876543,
            barangay=self.barangay
        )
        
        response = self.client.get(reverse('barangay_dashboard'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        
        # Check for data attributes on schedule cards
        self.assertIn(f'data-schedule-id="{schedule.id}"', content)
        self.assertIn('data-lat="15.1234567"', content)
        self.assertIn('data-lng="120.9876543"', content)
        self.assertIn('data-location="Test Location"', content)


class BarangayZonesPageTest(TestCase):
    """Test barangay zones page functionality"""
    
    def setUp(self):
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.barangay_user = User.objects.create_user(
            username='barangay_admin',
            password='password123',
            role='BARANGAY',
            barangay=self.barangay
        )
        self.other_barangay = Barangay.objects.create(name="Other Barangay")
        self.other_user = User.objects.create_user(
            username='other_barangay_admin',
            password='password123',
            role='BARANGAY',
            barangay=self.other_barangay
        )
        
        # Create zones for test barangay
        self.zone1 = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.zone2 = Zone.objects.create(name="Zone 2", barangay=self.barangay)
        
        # Create zone for other barangay
        self.other_zone = Zone.objects.create(name="Other Zone", barangay=self.other_barangay)
    
    def test_barangay_zones_view_renders_successfully(self):
        """Test that barangay_zones view renders successfully for barangay user"""
        self.client.login(username='barangay_admin', password='password123')
        response = self.client.get(reverse('barangay_zones'))
        self.assertEqual(response.status_code, 200)
    
    def test_barangay_zones_shows_only_correct_barangay_zones(self):
        """Test that barangay_zones only shows zones for the logged-in user's barangay"""
        self.client.login(username='barangay_admin', password='password123')
        response = self.client.get(reverse('barangay_zones'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode()
        
        # Should show zones for test barangay
        self.assertIn('Zone 1', content)
        self.assertIn('Zone 2', content)
        
        # Should NOT show zone for other barangay
        self.assertNotIn('Other Zone', content)
    
    def test_barangay_zones_access_denied_for_non_barangay(self):
        """Test that barangay_zones denies access for non-barangay users"""
        mswdo_user = User.objects.create_user(
            username='mswdo',
            password='password123',
            role='MSWDO'
        )
        self.client.login(username='mswdo', password='password123')
        response = self.client.get(reverse('barangay_zones'))
        self.assertEqual(response.status_code, 403)
    
    def test_barangay_dashboard_no_longer_shows_zone_cards(self):
        """Test that barangay dashboard no longer renders zone-card elements"""
        self.client.login(username='barangay_admin', password='password123')
        response = self.client.get(reverse('barangay_dashboard'))
        self.assertEqual(response.status_code, 200)
        
        content = response.content.decode()
        
        # Should NOT have zone-card class (old implementation)
        self.assertNotIn('zone-card', content)
        
        # Should have link to zones page
        self.assertIn('View All Zones', content)
        self.assertIn(reverse('barangay_zones'), content)
