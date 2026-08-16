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


class StaffDashboardTest(TestCase):
    """Test staff dashboard view context and analytics data"""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='MSWDO_STAFF'
        )
        self.barangay = Barangay.objects.create(name="Test Barangay")
        self.zone = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.household = Household.objects.create(barangay=self.barangay, zone=self.zone, house_number="123 Test St")
        self.family = Family.objects.create(household=self.household, family_name="Tester")
        self.member = FamilyMember.objects.create(family=self.family, first_name="John", last_name="Doe", birthdate="1990-01-01")

        # Create demographic members
        self.pwd_member = FamilyMember.objects.create(
            family=self.family, first_name="Jane", last_name="Doe", birthdate="1985-01-01", is_pwd=True
        )
        self.solo_parent_member = FamilyMember.objects.create(
            family=self.family, first_name="Bob", last_name="Doe", birthdate="1980-01-01", is_solo_parent=True
        )
        self.senior_member = FamilyMember.objects.create(
            family=self.family, first_name="Alice", last_name="Doe", birthdate="1950-01-01", is_senior_citizen=True
        )

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

    def test_staff_dashboard_has_analytics_context(self):
        """Test that staff dashboard includes all required analytics context variables"""
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Check demographics context
        self.assertIn('pwd_count', response.context)
        self.assertIn('solo_parent_count', response.context)
        self.assertIn('senior_count', response.context)
        self.assertEqual(response.context['pwd_count'], 1)
        self.assertEqual(response.context['solo_parent_count'], 1)
        self.assertEqual(response.context['senior_count'], 1)

        # Check RFID context
        self.assertIn('rfid_completion_percent', response.context)
        self.assertIn('total_families_rfid', response.context)

        # Check analytics data
        self.assertIn('analytics_labels', response.context)
        self.assertIn('analytics_data', response.context)
        self.assertIn('this_month_beneficiaries', response.context)

        # Check demographics chart data
        self.assertIn('demo_chart_labels', response.context)
        self.assertIn('demo_chart_data', response.context)
        self.assertEqual(response.context['demo_chart_labels'], ['PWDs', 'Solo Parents', 'Senior Citizens'])
        self.assertEqual(response.context['demo_chart_data'], [1, 1, 1])

        # Check monthly trend data
        self.assertIn('monthly_trend_labels', response.context)
        self.assertIn('monthly_trend_data', response.context)
        self.assertIn('monthly_trend_iso', response.context)

        # Check barangays with annotations
        self.assertIn('barangays', response.context)
        barangays = response.context['barangays']
        self.assertEqual(barangays.count(), 1)
        self.assertTrue(hasattr(barangays[0], 'household_count'))
        self.assertTrue(hasattr(barangays[0], 'family_count'))
        self.assertTrue(hasattr(barangays[0], 'rfid_count'))

    def test_staff_dashboard_analytics_data_matches_mswdo(self):
        """Test that staff dashboard analytics data matches mswdo dashboard for same data"""
        # Create MSWDO user for comparison
        mswdo_user = User.objects.create_user(
            username='mswdo_user',
            password='password123',
            role='MSWDO'
        )

        # Get staff dashboard context
        self.client.login(username='staff_user', password='password123')
        staff_response = self.client.get(reverse('staff_dashboard'))
        staff_context = staff_response.context

        # Get MSWDO dashboard context
        self.client.login(username='mswdo_user', password='password123')
        mswdo_response = self.client.get(reverse('mswdo_dashboard'))
        mswdo_context = mswdo_response.context

        # Compare analytics data (should be same for municipal-wide scope)
        self.assertEqual(
            staff_context['analytics_labels'],
            mswdo_context['analytics_labels']
        )
        self.assertEqual(
            staff_context['analytics_data'],
            mswdo_context['analytics_data']
        )
        self.assertEqual(
            staff_context['this_month_beneficiaries'],
            mswdo_context['this_month_beneficiaries']
        )


class StaffAPIAccessTest(TestCase):
    """Test API endpoint accessibility for MSWDO_STAFF role"""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username='staff_user',
            password='password123',
            role='MSWDO_STAFF'
        )
        self.mswdo_user = User.objects.create_user(
            username='mswdo_user',
            password='password123',
            role='MSWDO'
        )
        self.barangay_user = User.objects.create_user(
            username='barangay_user',
            password='password123',
            role='BARANGAY',
            barangay=Barangay.objects.create(name="Test Barangay")
        )
        self.barangay = Barangay.objects.create(name="Test Barangay 2")
        self.zone = Zone.objects.create(name="Zone 1", barangay=self.barangay)
        self.household = Household.objects.create(barangay=self.barangay, zone=self.zone, house_number="123 Test St")
        self.family = Family.objects.create(household=self.household, family_name="Tester")
        self.member = FamilyMember.objects.create(
            family=self.family, first_name="John", last_name="Doe", birthdate="1990-01-01", is_pwd=True
        )

    def test_api_demographics_staff_access_allowed(self):
        """Test that MSWDO_STAFF can access demographics API"""
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('api_demographics', args=['pwd']))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('residents', data)

    def test_api_demographics_mswdo_access_allowed(self):
        """Test that MSWDO can access demographics API"""
        self.client.login(username='mswdo_user', password='password123')
        response = self.client.get(reverse('api_demographics', args=['pwd']))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('residents', data)

    def test_api_demographics_barangay_access_denied(self):
        """Test that BARANGAY role cannot access demographics API"""
        self.client.login(username='barangay_user', password='password123')
        response = self.client.get(reverse('api_demographics', args=['pwd']))
        self.assertEqual(response.status_code, 403)

    def test_api_monthly_claims_staff_access_allowed(self):
        """Test that MSWDO_STAFF can access monthly claims API"""
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('api_monthly_claims', args=['2024-01']))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('breakdown', data)

    def test_api_monthly_claims_mswdo_access_allowed(self):
        """Test that MSWDO can access monthly claims API"""
        self.client.login(username='mswdo_user', password='password123')
        response = self.client.get(reverse('api_monthly_claims', args=['2024-01']))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('breakdown', data)

    def test_api_monthly_claims_barangay_access_denied(self):
        """Test that BARANGAY role cannot access monthly claims API"""
        self.client.login(username='barangay_user', password='password123')
        response = self.client.get(reverse('api_monthly_claims', args=['2024-01']))
        self.assertEqual(response.status_code, 403)

    def test_api_analytics_chart_data_staff_access_allowed(self):
        """Test that MSWDO_STAFF can access analytics chart data API"""
        self.client.login(username='staff_user', password='password123')
        response = self.client.get(reverse('api_analytics_chart_data'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('data', data)

    def test_api_analytics_chart_data_mswdo_access_allowed(self):
        """Test that MSWDO can access analytics chart data API"""
        self.client.login(username='mswdo_user', password='password123')
        response = self.client.get(reverse('api_analytics_chart_data'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('labels', data)
        self.assertIn('data', data)

    def test_api_analytics_chart_data_barangay_access_denied(self):
        """Test that BARANGAY role cannot access analytics chart data API"""
        self.client.login(username='barangay_user', password='password123')
        response = self.client.get(reverse('api_analytics_chart_data'))
        self.assertEqual(response.status_code, 403)


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


class SectorAgeAPITest(TestCase):
    """Test sector/age API endpoint for population data (10-sector life-stage breakdown)"""
    
    def setUp(self):
        # Create users for different roles
        self.mswdo_user = User.objects.create_user(
            username='mswdo',
            password='pass',
            role='MSWDO'
        )
        self.staff_user = User.objects.create_user(
            username='staff',
            password='pass',
            role='MSWDO_STAFF'
        )
        self.barangay1 = Barangay.objects.create(name="Barangay 1")
        self.barangay2 = Barangay.objects.create(name="Barangay 2")
        self.barangay_user = User.objects.create_user(
            username='barangay_admin',
            password='pass',
            role='BARANGAY',
            barangay=self.barangay1
        )
        
        # Create households and families for both barangays
        self.zone1 = Zone.objects.create(name="Zone 1", barangay=self.barangay1)
        self.zone2 = Zone.objects.create(name="Zone 2", barangay=self.barangay2)
        self.household1 = Household.objects.create(barangay=self.barangay1, zone=self.zone1, house_number="123 St")
        self.household2 = Household.objects.create(barangay=self.barangay2, zone=self.zone2, house_number="456 St")
        self.family1 = Family.objects.create(household=self.household1, family_name="Family1")
        self.family2 = Family.objects.create(household=self.household2, family_name="Family2")
        
        # Create archived family (should be excluded)
        self.family_archived = Family.objects.create(household=self.household1, family_name="Archived", is_archived=True)
        
        # Create members with various ages and sexes for barangay1
        from datetime import date
        today = date.today()
        
        # Male members (barangay1) - covering all 10 sectors
        self.member_m1 = FamilyMember.objects.create(
            family=self.family1, first_name="M1", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 3)  # Age 3 (Infant 0-5)
        )
        self.member_m2 = FamilyMember.objects.create(
            family=self.family1, first_name="M2", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 7)  # Age 7 (Child 6-12)
        )
        self.member_m3 = FamilyMember.objects.create(
            family=self.family1, first_name="M3", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 15)  # Age 15 (Adolescent 13-17)
        )
        self.member_m4 = FamilyMember.objects.create(
            family=self.family1, first_name="M4", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 20)  # Age 20 (Young Adult 18-24)
        )
        self.member_m5 = FamilyMember.objects.create(
            family=self.family1, first_name="M5", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 30)  # Age 30 (Adult 25-34)
        )
        self.member_m6 = FamilyMember.objects.create(
            family=self.family1, first_name="M6", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 40)  # Age 40 (Adult 35-44)
        )
        self.member_m7 = FamilyMember.objects.create(
            family=self.family1, first_name="M7", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 50)  # Age 50 (Adult 45-59)
        )
        self.member_m8 = FamilyMember.objects.create(
            family=self.family1, first_name="M8", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 65)  # Age 65 (Senior 60-69)
        )
        self.member_m9 = FamilyMember.objects.create(
            family=self.family1, first_name="M9", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 75)  # Age 75 (Senior 70-79)
        )
        self.member_m10 = FamilyMember.objects.create(
            family=self.family1, first_name="M10", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 85)  # Age 85 (Senior 80+)
        )
        
        # Female members (barangay1)
        self.member_f1 = FamilyMember.objects.create(
            family=self.family1, first_name="F1", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 4)  # Age 4 (Infant 0-5)
        )
        self.member_f2 = FamilyMember.objects.create(
            family=self.family1, first_name="F2", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 10)  # Age 10 (Child 6-12)
        )
        self.member_f3 = FamilyMember.objects.create(
            family=self.family1, first_name="F3", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 16)  # Age 16 (Adolescent 13-17)
        )
        self.member_f4 = FamilyMember.objects.create(
            family=self.family1, first_name="F4", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 22)  # Age 22 (Young Adult 18-24)
        )
        self.member_f5 = FamilyMember.objects.create(
            family=self.family1, first_name="F5", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 28)  # Age 28 (Adult 25-34)
        )
        self.member_f6 = FamilyMember.objects.create(
            family=self.family1, first_name="F6", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 38)  # Age 38 (Adult 35-44)
        )
        self.member_f7 = FamilyMember.objects.create(
            family=self.family1, first_name="F7", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 55)  # Age 55 (Adult 45-59)
        )
        self.member_f8 = FamilyMember.objects.create(
            family=self.family1, first_name="F8", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 62)  # Age 62 (Senior 60-69)
        )
        self.member_f9 = FamilyMember.objects.create(
            family=self.family1, first_name="F9", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 72)  # Age 72 (Senior 70-79)
        )
        self.member_f10 = FamilyMember.objects.create(
            family=self.family1, first_name="F10", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 82)  # Age 82 (Senior 80+)
        )
        
        # Member in archived family (should be excluded)
        self.member_archived = FamilyMember.objects.create(
            family=self.family_archived, first_name="Archived", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 25)  # Age 25
        )
        
        # Deceased member (should be excluded)
        self.member_deceased = FamilyMember.objects.create(
            family=self.family1, first_name="Deceased", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 35),  # Age 35
            date_of_death=today
        )
        
        # Members for barangay2 (for filtering test)
        self.member_brgy2_m1 = FamilyMember.objects.create(
            family=self.family2, first_name="B2M1", last_name="Test", sex='M',
            birthdate=today.replace(year=today.year - 12)  # Age 12 (Child 6-12)
        )
        self.member_brgy2_f1 = FamilyMember.objects.create(
            family=self.family2, first_name="B2F1", last_name="Test", sex='F',
            birthdate=today.replace(year=today.year - 19)  # Age 19 (Adolescent 13-17)
        )
    
    def test_sector_age_api_mswdo_municipal_wide(self):
        """Test MSWDO gets municipal-wide data by default"""
        self.client.login(username='mswdo', password='pass')
        response = self.client.get(reverse('api_sector_age_data'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Should include all members from both barangays (excluding archived/deceased)
        # Barangay1: 10 male + 10 female = 20
        # Barangay2: 1 male + 1 female = 2
        # Total: 11 male, 11 female
        self.assertEqual(data['sex_counts']['male'], 11)
        self.assertEqual(data['sex_counts']['female'], 11)
        
        # Verify 10 sectors returned
        self.assertEqual(len(data['sectors']), 10)
        
        # Verify sector labels
        expected_labels = [
            'Infant / Early Childhood', 'Child', 'Adolescent', 'Young Adult',
            'Adult', 'Adult', 'Adult', 'Senior Citizen', 'Senior Citizen', 'Senior Citizen'
        ]
        actual_labels = [s['label'] for s in data['sectors']]
        self.assertEqual(actual_labels, expected_labels)
    
    def test_sector_age_api_staff_municipal_wide(self):
        """Test MSWDO_STAFF gets municipal-wide data by default"""
        self.client.login(username='staff', password='pass')
        response = self.client.get(reverse('api_sector_age_data'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Same as MSWDO - municipal-wide
        self.assertEqual(data['sex_counts']['male'], 11)
        self.assertEqual(data['sex_counts']['female'], 11)
    
    def test_sector_age_api_barangay_forced_to_own(self):
        """Test BARANGAY role is forced to own barangay regardless of query param"""
        self.client.login(username='barangay_admin', password='pass')
        
        # Try to pass a different barangay ID (should be ignored)
        response = self.client.get(reverse('api_sector_age_data'), {'barangay': self.barangay2.id})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Should only return barangay1 data (user's barangay)
        # Barangay1: 10 male + 10 female = 20 (excluding archived/deceased)
        self.assertEqual(data['sex_counts']['male'], 10)
        self.assertEqual(data['sex_counts']['female'], 10)
    
    def test_sector_age_api_mswdo_filter_by_barangay(self):
        """Test MSWDO can filter by barangay"""
        self.client.login(username='mswdo', password='pass')
        
        # Filter to barangay1
        response = self.client.get(reverse('api_sector_age_data'), {'barangay': self.barangay1.id})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Should only return barangay1 data
        self.assertEqual(data['sex_counts']['male'], 10)
        self.assertEqual(data['sex_counts']['female'], 10)
        
        # Filter to barangay2
        response = self.client.get(reverse('api_sector_age_data'), {'barangay': self.barangay2.id})
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Should only return barangay2 data
        self.assertEqual(data['sex_counts']['male'], 1)
        self.assertEqual(data['sex_counts']['female'], 1)
    
    def test_sector_age_api_excludes_archived_families(self):
        """Test that members of archived families are excluded"""
        self.client.login(username='mswdo', password='pass')
        response = self.client.get(reverse('api_sector_age_data'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Archived family member (age 25) should not be counted
        # Adult 25-34 sector should only have M5(30) and F5(28) = 2
        # If archived was included, it would be 3
        adult_25_34 = next(s for s in data['sectors'] if s['range'] == '25-34')
        self.assertEqual(adult_25_34['total'], 2)
    
    def test_sector_age_api_excludes_deceased_members(self):
        """Test that deceased members are excluded"""
        self.client.login(username='mswdo', password='pass')
        response = self.client.get(reverse('api_sector_age_data'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Deceased member (age 35) should not be counted
        # Adult 35-44 sector should only have M6(40) and F6(38) = 2
        # If deceased was included, it would be 3
        adult_35_44 = next(s for s in data['sectors'] if s['range'] == '35-44')
        self.assertEqual(adult_35_44['total'], 2)
    
    def test_sector_age_api_10_sector_boundaries_correct(self):
        """Test that 10-sector boundaries are correctly calculated"""
        self.client.login(username='mswdo', password='pass')
        response = self.client.get(reverse('api_sector_age_data'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        sectors = data['sectors']
        
        # Check specific sectors (municipal-wide)
        # Infant 0-5: M1(3), F1(4) = 2
        infant = next(s for s in sectors if s['range'] == '0-5')
        self.assertEqual(infant['male'], 1)
        self.assertEqual(infant['female'], 1)
        self.assertEqual(infant['total'], 2)
        
        # Child 6-12: M2(7), F2(10), B2M1(12) = 3
        child = next(s for s in sectors if s['range'] == '6-12')
        self.assertEqual(child['male'], 2)
        self.assertEqual(child['female'], 1)
        self.assertEqual(child['total'], 3)
        
        # Adolescent 13-17: M3(15), F3(16), B2F1(19) = 3
        adolescent = next(s for s in sectors if s['range'] == '13-17')
        self.assertEqual(adolescent['male'], 1)
        self.assertEqual(adolescent['female'], 2)
        self.assertEqual(adolescent['total'], 3)
        
        # Young Adult 18-24: M4(20), F4(22) = 2
        young_adult = next(s for s in sectors if s['range'] == '18-24')
        self.assertEqual(young_adult['male'], 1)
        self.assertEqual(young_adult['female'], 1)
        self.assertEqual(young_adult['total'], 2)
        
        # Senior 80+: M10(85), F10(82) = 2
        senior_80 = next(s for s in sectors if s['range'] == '80 and over')
        self.assertEqual(senior_80['male'], 1)
        self.assertEqual(senior_80['female'], 1)
        self.assertEqual(senior_80['total'], 2)
    
    def test_sector_age_api_no_old_life_stages_data(self):
        """Test that old life-stage summary data is not returned"""
        self.client.login(username='mswdo', password='pass')
        response = self.client.get(reverse('api_sector_age_data'))
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        
        # Old life_stages key should not exist
        self.assertNotIn('life_stages', data)
        
        # Old age_brackets key should not exist
        self.assertNotIn('age_brackets', data)
        
        # Only sex_counts and sectors should exist
        self.assertIn('sex_counts', data)
        self.assertIn('sectors', data)
    
    def test_sector_age_api_invalid_barangay(self):
        """Test that invalid barangay ID returns error"""
        self.client.login(username='mswdo', password='pass')
        response = self.client.get(reverse('api_sector_age_data'), {'barangay': 99999})
        self.assertEqual(response.status_code, 400)
        
        data = response.json()
        self.assertIn('error', data)
    
    def test_sector_age_api_requires_login(self):
        """Test that API requires authentication"""
        response = self.client.get(reverse('api_sector_age_data'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
