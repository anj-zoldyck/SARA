from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from accounts.models import Barangay
from households.models import Household, Zone, Family, FamilyMember

User = get_user_model()


class RFIDRegistrationTestCase(TestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role='MSWDO'
        )
        self.client = Client(enforce_csrf_checks=False)
        self.client.login(username='testuser', password='testpass123')

        # Create test data
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.zone = Zone.objects.create(barangay=self.barangay, name='Zone 1')
        self.household = Household.objects.create(
            barangay=self.barangay,
            zone=self.zone,
            house_number='123',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        self.family1 = Family.objects.create(
            household=self.household,
            family_name='Family One'
        )
        self.family2 = Family.objects.create(
            household=self.household,
            family_name='Family Two'
        )

    def test_duplicate_rfid_registration_bug(self):
        """
        Test that registering an RFID already assigned to another family
        should show an error, but currently succeeds silently.
        This test reproduces the reported bug by testing the view behavior.
        """
        # First, register RFID "12345" to family1 directly via model
        self.family1.rfid_uid = '12345'
        self.family1.save()
        self.family1.refresh_from_db()
        self.assertEqual(self.family1.rfid_uid, '12345')

        # Now attempt to register the same RFID "12345" to family2 via the view
        response = self.client.post(
            f'/mswdo/rfid/register/{self.family2.id}/',
            {'rfid_uid': '12345'},
            follow=True
        )

        # Check if the bug exists: family2 should NOT have gotten the RFID
        self.family2.refresh_from_db()

        # If bug exists, family2.rfid_uid will be '12345' (wrong!)
        # If fixed, family2.rfid_uid should still be None
        if self.family2.rfid_uid == '12345':
            # Bug reproduced - duplicate registration succeeded
            self.fail("BUG REPRODUCED: Duplicate RFID registration succeeded when it should have been blocked")
        else:
            # Bug fixed - duplicate registration was blocked
            self.assertIsNone(self.family2.rfid_uid)

    def test_database_constraint_enforcement(self):
        """
        Test that the database UNIQUE constraint actually prevents
        duplicate RFID values at the database level.
        """
        # Register RFID to family1
        self.family1.rfid_uid = '77777'
        self.family1.save()
        
        # Try to directly set the same RFID on family2 (bypassing the view)
        # This should raise IntegrityError due to the database constraint
        with self.assertRaises(IntegrityError):
            self.family2.rfid_uid = '77777'
            self.family2.save()

    def test_cross_barangay_duplicate_rfid(self):
        """
        Test that RFID uniqueness is enforced globally across different barangays.
        This reproduces the reported bug where same RFID could be registered to
        families in different barangays.
        """
        # Create a second barangay and zone
        barangay2 = Barangay.objects.create(name='Test Barangay 2')
        zone2 = Zone.objects.create(barangay=barangay2, name='Zone 2')
        household2 = Household.objects.create(
            barangay=barangay2,
            zone=zone2,
            house_number='456',
            land_use='RESIDENTIAL',
            hazard_exposure='NONE'
        )
        
        # Create family in second barangay
        family_cross_barangay = Family.objects.create(
            household=household2,
            family_name='Cross Barangay Family'
        )
        
        # Register RFID to family1 (in original barangay)
        self.family1.rfid_uid = 'CROSS_BARANGAY_TEST'
        self.family1.save()
        self.family1.refresh_from_db()
        self.assertEqual(self.family1.rfid_uid, 'CROSS_BARANGAY_TEST')
        
        # Attempt to register same RFID to family in different barangay via view
        response = self.client.post(
            f'/mswdo/rfid/register/{family_cross_barangay.id}/',
            {'rfid_uid': 'CROSS_BARANGAY_TEST'},
            follow=True
        )
        
        # Check if the bug exists: family_cross_barangay should NOT have gotten the RFID
        family_cross_barangay.refresh_from_db()
        
        if family_cross_barangay.rfid_uid == 'CROSS_BARANGAY_TEST':
            # Bug reproduced - cross-barangay duplicate succeeded
            self.fail("BUG REPRODUCED: Cross-barangay duplicate RFID registration succeeded when it should have been blocked")
        else:
            # Bug fixed - cross-barangay duplicate was blocked
            self.assertIsNone(family_cross_barangay.rfid_uid)
