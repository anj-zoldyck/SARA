from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from households.models import Household, Zone, Family, FamilyMember
from accounts.models import Barangay
from distribution.models import AidSchedule, AidClaim
from programs.models import Program, Assistance, AidCategory
from distribution.views import scan_rfid, staff_walkin_rfid_lookup, staff_walkin_reactivate_family
from django.test import RequestFactory
from django.http import JsonResponse

User = get_user_model()


class FamilyArchivingTestCase(TestCase):
    def setUp(self):
        # Create test data
        self.barangay1 = Barangay.objects.create(name='Barangay 1')
        self.barangay2 = Barangay.objects.create(name='Barangay 2')
        
        self.zone1 = Zone.objects.create(barangay=self.barangay1, name='Zone 1')
        self.zone2 = Zone.objects.create(barangay=self.barangay2, name='Zone 2')
        
        self.household1 = Household.objects.create(
            barangay=self.barangay1,
            zone=self.zone1,
            house_number='123',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        
        self.household2 = Household.objects.create(
            barangay=self.barangay2,
            zone=self.zone2,
            house_number='456',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        
        # Create users
        self.barangay_admin1 = User.objects.create_user(
            username='barangay_admin1',
            password='testpass123',
            email='admin1@test.com',
            role='BARANGAY',
            barangay=self.barangay1
        )
        
        self.barangay_admin2 = User.objects.create_user(
            username='barangay_admin2',
            password='testpass123',
            email='admin2@test.com',
            role='BARANGAY',
            barangay=self.barangay2
        )
        
        self.mswdo_admin = User.objects.create_user(
            username='mswdo_admin',
            password='testpass123',
            email='mswdo@test.com',
            role='MSWDO'
        )
        
        self.mswdo_staff = User.objects.create_user(
            username='mswdo_staff',
            password='testpass123',
            email='staff@test.com',
            role='MSWDO_STAFF'
        )
        
        # Create families
        self.family1 = Family.objects.create(
            household=self.household1,
            family_name='Family 1',
            rfid_uid='RFID001',
            is_active=True
        )
        
        self.family2 = Family.objects.create(
            household=self.household2,
            family_name='Family 2',
            rfid_uid='RFID002',
            is_active=True
        )
        
        # Create family members
        self.member1 = FamilyMember.objects.create(
            family=self.family1,
            first_name='John',
            last_name='Doe',
            relationship='HEAD'
        )
        
        self.member2 = FamilyMember.objects.create(
            family=self.family2,
            first_name='Jane',
            last_name='Smith',
            relationship='HEAD'
        )
        
        # Create program and assistance for scheduled distribution tests
        self.program = Program.objects.create(name='Test Program', is_active=True)
        self.category = AidCategory.objects.create(
            program=self.program,
            name='Food Aid',
            is_active=True
        )
        self.assistance = Assistance.objects.create(
            program=self.program,
            aid_category=self.category,
            beneficiary_type='family',
            is_active=True
        )
        
        self.factory = RequestFactory()

    def test_barangay_admin_can_archive_family_in_own_barangay(self):
        """Barangay Admin can archive a family in their own barangay"""
        self.client.force_login(self.barangay_admin1)
        
        response = self.client.post(f'/barangay/families/{self.family1.id}/archive/')
        
        self.family1.refresh_from_db()
        self.assertTrue(self.family1.is_archived)
        self.assertIsNotNone(self.family1.archived_at)
        self.assertEqual(self.family1.archived_by, self.barangay_admin1)
        self.assertEqual(response.status_code, 302)  # Redirect after success

    def test_barangay_admin_cannot_archive_family_in_different_barangay(self):
        """Barangay Admin cannot archive a family in a different barangay"""
        self.client.force_login(self.barangay_admin1)
        
        response = self.client.post(f'/barangay/families/{self.family2.id}/archive/')
        
        self.family2.refresh_from_db()
        self.assertFalse(self.family2.is_archived)
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_barangay_admin_can_unarchive_family_in_own_barangay(self):
        """Barangay Admin can unarchive a family in their own barangay"""
        # First archive the family
        self.family1.is_archived = True
        self.family1.archived_at = timezone.now()
        self.family1.archived_by = self.barangay_admin1
        self.family1.save()
        
        self.client.force_login(self.barangay_admin1)
        
        response = self.client.post(f'/barangay/families/{self.family1.id}/unarchive/')
        
        self.family1.refresh_from_db()
        self.assertFalse(self.family1.is_archived)
        self.assertIsNone(self.family1.archived_at)
        self.assertIsNone(self.family1.archived_by)
        self.assertEqual(response.status_code, 302)  # Redirect after success

    def test_mswdo_cannot_access_archive_action(self):
        """MSWDO Admin cannot access archive action"""
        self.client.force_login(self.mswdo_admin)
        
        response = self.client.post(f'/barangay/families/{self.family1.id}/archive/')
        
        self.family1.refresh_from_db()
        self.assertFalse(self.family1.is_archived)
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_mswdo_staff_cannot_access_archive_action(self):
        """MSWDO Staff cannot access archive action"""
        self.client.force_login(self.mswdo_staff)
        
        response = self.client.post(f'/barangay/families/{self.family1.id}/archive/')
        
        self.family1.refresh_from_db()
        self.assertFalse(self.family1.is_archived)
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_mswdo_cannot_access_archived_families_list(self):
        """MSWDO Admin cannot access archived families list"""
        # Archive the family first
        self.family1.is_archived = True
        self.family1.save()
        
        self.client.force_login(self.mswdo_admin)
        
        response = self.client.get('/barangay/archived-families/')
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_mswdo_staff_cannot_access_archived_families_list(self):
        """MSWDO Staff cannot access archived families list"""
        # Archive the family first
        self.family1.is_archived = True
        self.family1.save()
        
        self.client.force_login(self.mswdo_staff)
        
        response = self.client.get('/barangay/archived-families/')
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_scan_rfid_blocks_archived_family(self):
        """scan_rfid rejects an archived family's RFID with distinct error message"""
        # Archive the family
        self.family1.is_archived = True
        self.family1.save()
        
        # Create an active schedule
        schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now(),
            location='Test Location',
            created_by=self.mswdo_admin
        )
        
        self.client.force_login(self.mswdo_staff)
        
        # Simulate RFID scan
        response = self.client.post(f'/mswdo/schedule/{schedule.id}/rfid/scan/', {
            'rfid_uid': 'RFID001'
        })
        
        # Should return error about archived family
        self.assertEqual(response.status_code, 200)
        self.assertIn('archived', response.content.decode().lower())
        
        # Verify no claim was created
        self.assertFalse(AidClaim.objects.filter(family=self.family1).exists())

    def test_scan_rfid_allows_non_archived_family(self):
        """scan_rfid allows non-archived families to claim normally"""
        # Create an active schedule
        schedule = AidSchedule.objects.create(
            assistance=self.assistance,
            schedule_datetime=timezone.now(),
            location='Test Location',
            created_by=self.mswdo_admin
        )
        
        self.client.force_login(self.mswdo_staff)
        
        # Simulate RFID scan
        response = self.client.post(f'/mswdo/schedule/{schedule.id}/rfid/scan/', {
            'rfid_uid': 'RFID001'
        })
        
        # Should succeed (or show member selection for individual-based assistance)
        self.assertNotEqual(response.status_code, 403)
        
        # Verify claim was created for family-based assistance
        self.assertTrue(AidClaim.objects.filter(family=self.family1).exists())

    def test_staff_walkin_rfid_lookup_returns_archived_status(self):
        """staff_walkin_rfid_lookup returns status='archived' for archived families"""
        # Archive the family
        self.family1.is_archived = True
        self.family1.save()
        
        self.client.force_login(self.mswdo_staff)
        
        response = self.client.get('/staff/walkin/rfid/', {'rfid_uid': 'RFID001'})
        if response.status_code == 302:
            print("REDIRECT URL:", response.url)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'archived')
        self.assertEqual(data['family_id'], self.family1.id)
        self.assertEqual(data['family_name'], self.family1.family_name)
        self.assertNotIn('members', data)  # No member data for archived families

    def test_staff_walkin_rfid_lookup_returns_success_for_active_family(self):
        """staff_walkin_rfid_lookup returns member list for active families"""
        self.client.force_login(self.mswdo_staff)
        
        response = self.client.get('/staff/walkin/rfid/', {'rfid_uid': 'RFID001'})
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('members', data)
        self.assertEqual(len(data['members']), 1)

    def test_staff_walkin_reactivate_family_success_by_mswdo_staff(self):
        """staff_walkin_reactivate_family successfully un-archives when called by MSWDO_STAFF"""
        # Archive the family
        self.family1.is_archived = True
        self.family1.archived_at = timezone.now()
        self.family1.archived_by = self.barangay_admin1
        self.family1.save()
        
        self.client.force_login(self.mswdo_staff)
        
        response = self.client.post('/staff/walkin/reactivate-family/', {
            'family_id': self.family1.id
        })
        
        self.family1.refresh_from_db()
        self.assertFalse(self.family1.is_archived)
        self.assertIsNone(self.family1.archived_at)
        self.assertIsNone(self.family1.archived_by)
        
        data = response.json()
        self.assertEqual(data['status'], 'success')

    def test_staff_walkin_reactivate_family_rejects_non_mswdo_staff(self):
        """staff_walkin_reactivate_family rejects calls from other roles"""
        # Archive the family
        self.family1.is_archived = True
        self.family1.save()
        
        self.client.login(username='mswdo_admin', password='testpass123')
        
        response = self.client.post('/staff/walkin/reactivate-family/', {
            'family_id': self.family1.id
        })
        
        self.family1.refresh_from_db()
        self.assertTrue(self.family1.is_archived)  # Should still be archived
        
        data = response.json()
        self.assertEqual(data['status'], 'error')

    def test_archived_families_list_shows_only_barangay_admins_families(self):
        """Archived Families list shows only families in the admin's barangay"""
        # Archive both families
        self.family1.is_archived = True
        self.family1.save()
        self.family2.is_archived = True
        self.family2.save()
        
        self.client.force_login(self.barangay_admin1)
        
        response = self.client.get('/barangay/archived-families/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Family 1')
        self.assertNotContains(response, 'Family 2')  # Different barangay

    def test_archived_family_add_member_rejected(self):
        self.family1.is_archived = True
        self.family1.save()
        self.client.force_login(self.barangay_admin1)
        response = self.client.post(f'/barangay/families/{self.family1.id}/members/add/', {
            'first_name': 'New', 'last_name': 'Member', 'relationship': 'SON', 'sex': 'M'
        })
        self.assertEqual(response.status_code, 302)
        # Should redirect back to family_detail
        self.assertRedirects(response, f'/barangay/families/{self.family1.id}/', fetch_redirect_response=False)
        self.assertEqual(self.family1.members.count(), 1) # Only the head member

    def test_archived_family_edit_member_rejected(self):
        self.family1.is_archived = True
        self.family1.save()
        self.client.force_login(self.barangay_admin1)
        response = self.client.post(f'/barangay/members/{self.member1.id}/edit/', {
            'first_name': 'Edited', 'last_name': 'Member', 'relationship': 'HEAD', 'sex': 'M'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f'/barangay/families/{self.family1.id}/', fetch_redirect_response=False)
        self.member1.refresh_from_db()
        self.assertEqual(self.member1.first_name, 'John') # Unchanged

    def test_archived_family_edit_name_rejected(self):
        self.family1.is_archived = True
        self.family1.save()
        self.client.force_login(self.barangay_admin1)
        response = self.client.post(f'/barangay/families/{self.family1.id}/edit-name/', {
            'family_name': 'New Name'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f'/barangay/families/{self.family1.id}/', fetch_redirect_response=False)
        self.family1.refresh_from_db()
        self.assertEqual(self.family1.family_name, 'Family 1') # Unchanged

    def test_archived_family_delete_member_rejected(self):
        self.family1.is_archived = True
        self.family1.save()
        self.client.force_login(self.barangay_admin1)
        response = self.client.post(f'/barangay/members/{self.member1.id}/delete/')
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f'/barangay/families/{self.family1.id}/', fetch_redirect_response=False)
        self.assertTrue(FamilyMember.objects.filter(id=self.member1.id).exists()) # Not deleted

    def test_archived_family_delete_family_rejected(self):
        self.family1.is_archived = True
        self.family1.save()
        self.client.force_login(self.barangay_admin1)
        response = self.client.post(f'/barangay/families/{self.family1.id}/delete/')
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f'/barangay/families/{self.family1.id}/', fetch_redirect_response=False)
        self.assertTrue(Family.objects.filter(id=self.family1.id).exists()) # Not deleted

    def test_unarchived_family_mutations_succeed(self):
        # Non-archived regression explicit tests
        self.family1.is_archived = False
        self.family1.save()
        self.client.force_login(self.barangay_admin1)
        
        # Edit Name
        response = self.client.post(f'/barangay/families/{self.family1.id}/edit-name/', {
            'family_name': 'Edited Family Name'
        })
        self.family1.refresh_from_db()
        self.assertEqual(self.family1.family_name, 'Edited Family Name')
        
        # Add Member
        response = self.client.post(f'/barangay/families/{self.family1.id}/members/add/', {
            'first_name': 'Child', 'last_name': 'Doe', 'relationship': 'SON', 'sex': 'M'
        })
        self.assertEqual(self.family1.members.count(), 2)
        
        child = self.family1.members.get(first_name='Child')
        
        # Edit Member
        response = self.client.post(f'/barangay/members/{child.id}/edit/', {
            'first_name': 'Child Edited', 'last_name': 'Doe', 'relationship': 'SON', 'sex': 'M'
        })
        child.refresh_from_db()
        self.assertEqual(child.first_name, 'Child Edited')
        
        # Delete Member
        response = self.client.post(f'/barangay/members/{child.id}/delete/')
        self.assertFalse(FamilyMember.objects.filter(id=child.id).exists())
        
        # Delete Family
        response = self.client.post(f'/barangay/families/{self.family1.id}/delete/')
        self.assertFalse(Family.objects.filter(id=self.family1.id).exists())

    def test_household_detail_shows_archived_badge(self):
        """Household detail page shows 'Archived' badge for an archived family"""
        self.family1.is_archived = True
        self.family1.save()
        
        self.client.force_login(self.barangay_admin1)
        response = self.client.get(f'/barangay/households/{self.household1.id}/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Archived')
        self.assertContains(response, 'acct-badge--inactive')
        # Using exact string match for 'Active' is tricky as it might appear elsewhere (e.g. is_active=True), but we can check it doesn't contain the active badge HTML
        self.assertNotContains(response, 'acct-badge--active')

    def test_household_detail_shows_active_badge(self):
        """Household detail page shows 'Active' badge for a non-archived active family"""
        self.family1.is_archived = False
        self.family1.is_active = True
        self.family1.save()
        
        self.client.force_login(self.barangay_admin1)
        response = self.client.get(f'/barangay/households/{self.household1.id}/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active')
        self.assertContains(response, 'acct-badge--active')
        self.assertNotContains(response, 'Archived')

    def test_household_detail_shows_inactive_badge(self):
        """Household detail page shows 'Inactive' badge for a non-archived inactive family"""
        self.family1.is_archived = False
        self.family1.is_active = False
        self.family1.save()
        
        self.client.force_login(self.barangay_admin1)
        response = self.client.get(f'/barangay/households/{self.household1.id}/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inactive')
        self.assertContains(response, 'acct-badge--inactive')
        self.assertNotContains(response, 'Archived')

class DeceasedMemberTestCase(TestCase):
    def setUp(self):
        self.barangay = Barangay.objects.create(name='Barangay Deceased')
        self.zone = Zone.objects.create(barangay=self.barangay, name='Zone Deceased')
        self.household = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='789',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        self.family = Family.objects.create(
            household=self.household,
            family_name='Test Family',
            rfid_uid='RFID_DEC',
            is_active=True
        )
        self.member1 = FamilyMember.objects.create(
            family=self.family,
            first_name='Alive',
            last_name='Member',
            relationship='HEAD',
            birthdate=timezone.now().date() - timezone.timedelta(days=365*30)
        )
        self.member2 = FamilyMember.objects.create(
            family=self.family,
            first_name='SoonToBeDeceased',
            last_name='Member',
            relationship='SPOUSE',
            birthdate=timezone.now().date() - timezone.timedelta(days=365*25)
        )
        self.admin = User.objects.create_user(
            username='b_admin',
            password='testpass123',
            email='admin@test.com',
            role='BARANGAY',
            barangay=self.barangay
        )
        self.other_barangay = Barangay.objects.create(name='Other Barangay')
        self.other_admin = User.objects.create_user(
            username='other_admin',
            password='testpass123',
            email='other@test.com',
            role='BARANGAY',
            barangay=self.other_barangay
        )

        self.program = Program.objects.create(name='Test Program', is_active=True)
        self.category = AidCategory.objects.create(program=self.program, name='Aid', is_active=True)
        self.individual_assistance = Assistance.objects.create(
            program=self.program, aid_category=self.category, beneficiary_type='individual', is_active=True
        )
        self.family_assistance = Assistance.objects.create(
            program=self.program, aid_category=self.category, beneficiary_type='family', is_active=True
        )

    def test_mark_member_deceased_success(self):
        self.client.force_login(self.admin)
        death_date = (timezone.now().date() - timezone.timedelta(days=1)).strftime("%Y-%m-%d")
        
        response = self.client.post(f'/barangay/members/{self.member2.id}/mark-deceased/', {
            'date_of_death': death_date
        })
        
        self.member2.refresh_from_db()
        self.assertIsNotNone(self.member2.date_of_death)
        self.assertTrue(self.member2.is_deceased)
        self.assertEqual(response.status_code, 302)
        
    def test_mark_member_deceased_rejects_wrong_barangay(self):
        self.client.force_login(self.other_admin)
        death_date = (timezone.now().date() - timezone.timedelta(days=1)).strftime("%Y-%m-%d")
        
        response = self.client.post(f'/barangay/members/{self.member2.id}/mark-deceased/', {
            'date_of_death': death_date
        })
        
        self.member2.refresh_from_db()
        self.assertIsNone(self.member2.date_of_death)
        self.assertEqual(response.status_code, 404)
        
    def test_mark_member_deceased_freezes_age(self):
        self.member2.date_of_death = self.member2.birthdate + timezone.timedelta(days=365*5)
        self.member2.save()
        self.assertEqual(self.member2.age, 5)
        
    def test_unmark_member_deceased(self):
        self.member2.date_of_death = timezone.now().date() - timezone.timedelta(days=1)
        self.member2.save()
        
        self.client.force_login(self.admin)
        response = self.client.post(f'/barangay/members/{self.member2.id}/unmark-deceased/')
        
        self.member2.refresh_from_db()
        self.assertIsNone(self.member2.date_of_death)
        self.assertFalse(self.member2.is_deceased)
        
    def test_eligibility_engine_short_circuits(self):
        from programs.eligibility import check_eligibility
        
        self.member2.date_of_death = timezone.now().date()
        self.member2.save()
        
        is_eligible, reasons = check_eligibility(self.member2, self.individual_assistance)
        self.assertFalse(is_eligible)
        self.assertIn("Deceased", reasons)
        
    def test_family_based_eligibility_unaffected(self):
        from programs.beneficiary_engine import evaluate_family_against_rules, get_eligible_pool
        from programs.models import EligibilityRule
        
        EligibilityRule.objects.create(
            assistance=self.family_assistance,
            rule_type='FLOOD_PRONE'
        )
        
        # Make the household flood prone
        from households.models import FloodProneArea
        fpa = FloodProneArea.objects.create(name='Test FPA')
        self.household.flood_prone_area = fpa
        self.household.save()
        
        self.member2.date_of_death = timezone.now().date()
        self.member2.save()
        
        is_eligible, reasons = evaluate_family_against_rules(self.family, self.family_assistance)
        self.assertTrue(is_eligible, "Family should remain eligible even with a deceased member")
        
        pool = get_eligible_pool(self.family_assistance)
        self.assertIn(self.family, pool)


