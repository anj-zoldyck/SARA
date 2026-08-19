from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
from django.utils import timezone
from accounts.utils import validate_image_file
from accounts.models import User, Barangay
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware


class ImageValidationTests(TestCase):
    """
    Test suite for the validate_image_file function in accounts/utils.py.
    Tests cover valid images, oversized files, disguised non-image files,
    and corrupted image data.
    """

    def create_test_image(self, format='JPEG', size=(100, 100)):
        """Helper to create a valid test image in memory."""
        img = Image.new('RGB', size, color='red')
        img_io = io.BytesIO()
        img.save(img_io, format=format)
        img_io.seek(0)
        return SimpleUploadedFile(
            f"test.{format.lower()}",
            img_io.read(),
            content_type=f'image/{format.lower()}'
        )

    def test_valid_jpeg_passes(self):
        """A valid JPEG image should pass validation."""
        image = self.create_test_image('JPEG')
        try:
            validate_image_file(image)
        except ValidationError:
            self.fail("Valid JPEG image raised ValidationError")

    def test_valid_png_passes(self):
        """A valid PNG image should pass validation."""
        image = self.create_test_image('PNG')
        try:
            validate_image_file(image)
        except ValidationError:
            self.fail("Valid PNG image raised ValidationError")

    def test_valid_gif_passes(self):
        """A valid GIF image should pass validation."""
        image = self.create_test_image('GIF')
        try:
            validate_image_file(image)
        except ValidationError:
            self.fail("Valid GIF image raised ValidationError")

    def test_valid_webp_passes(self):
        """A valid WEBP image should pass validation."""
        image = self.create_test_image('WEBP')
        try:
            validate_image_file(image)
        except ValidationError:
            self.fail("Valid WEBP image raised ValidationError")

    def test_oversized_file_rejected(self):
        """A file exceeding MAX_IMAGE_SIZE_MB should be rejected."""
        # Create a file larger than 5MB
        large_content = b'x' * (6 * 1024 * 1024)  # 6MB
        large_file = SimpleUploadedFile(
            "large.jpg",
            large_content,
            content_type='image/jpeg'
        )
        with self.assertRaises(ValidationError) as cm:
            validate_image_file(large_file)
        self.assertIn("too large", str(cm.exception))

    def test_text_file_renamed_as_jpg_rejected(self):
        """A text file renamed with .jpg extension should be rejected."""
        text_content = b"This is not an image, just plain text."
        fake_image = SimpleUploadedFile(
            "fake.jpg",
            text_content,
            content_type='image/jpeg'
        )
        with self.assertRaises(ValidationError) as cm:
            validate_image_file(fake_image)
        self.assertIn("not a valid image", str(cm.exception))

    def test_corrupted_image_rejected(self):
        """A corrupted/truncated image file should be rejected."""
        # Create invalid image data
        corrupted_data = b'\x89PNG\r\n\x1a\n' + b'corrupted data here'
        corrupted_file = SimpleUploadedFile(
            "corrupted.png",
            corrupted_data,
            content_type='image/png'
        )
        with self.assertRaises(ValidationError) as cm:
            validate_image_file(corrupted_file)
        self.assertIn("not a valid image", str(cm.exception))

    def test_unsupported_format_rejected(self):
        """An image format not in ALLOWED_IMAGE_FORMATS should be rejected."""
        # Create a BMP image (not in allowed formats)
        img = Image.new('RGB', (100, 100), color='blue')
        img_io = io.BytesIO()
        img.save(img_io, format='BMP')
        img_io.seek(0)
        bmp_file = SimpleUploadedFile(
            "test.bmp",
            img_io.read(),
            content_type='image/bmp'
        )
        with self.assertRaises(ValidationError) as cm:
            validate_image_file(bmp_file)
        self.assertIn("Unsupported image format", str(cm.exception))

    def test_file_pointer_reset_after_validation(self):
        """The file pointer should be reset to 0 after validation."""
        image = self.create_test_image('JPEG')
        validate_image_file(image)
        # After validation, the file pointer should be at 0
        self.assertEqual(image.tell(), 0)


class UserAccountsSearchTestCase(TestCase):
    """
    Test suite for the search functionality in user_accounts view.
    Tests cover partial name matches, email matches, username matches,
    combined filtering with role/barangay, pagination with search,
    and empty/whitespace-only search behavior.
    """

    def setUp(self):
        """Create test users with various names, usernames, and emails."""
        self.mswdo_user = User.objects.create_user(
            username='mswdo_admin',
            email='mswdo@example.com',
            password='testpass123',
            first_name='Admin',
            last_name='User',
            role='MSWDO'
        )
        
        self.staff1 = User.objects.create_user(
            username='staff_juan',
            email='juan.cruz@example.com',
            password='testpass123',
            first_name='Juan',
            last_name='Cruz',
            role='MSWDO_STAFF'
        )
        
        self.staff2 = User.objects.create_user(
            username='staff_maria',
            email='maria.santos@example.com',
            password='testpass123',
            first_name='Maria',
            last_name='Santos',
            role='MSWDO_STAFF'
        )
        
        self.barangay = Barangay.objects.create(name='San Jose')
        
        self.brgy_admin1 = User.objects.create_user(
            username='brgy_pedro',
            email='pedro.reyes@example.com',
            password='testpass123',
            first_name='Pedro',
            last_name='Reyes',
            role='BARANGAY',
            barangay=self.barangay
        )
        
        self.brgy_admin2 = User.objects.create_user(
            username='brgy_ana',
            email='ana.garcia@example.com',
            password='testpass123',
            first_name='Ana',
            last_name='Garcia',
            middle_name='Maria',
            role='BARANGAY',
            barangay=self.barangay
        )

    def test_search_by_first_name(self):
        """Search should match partial first name."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        request = factory.get('/mswdo/user-accounts/', {'search': 'Juan'})
        request.user = self.mswdo_user
        
        # Add session and messages middleware
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        # Check that Juan Cruz is in the context
        self.assertIn('Juan', str(response.content))
        # Should not contain Maria
        self.assertNotIn('Maria Santos', str(response.content))

    def test_search_by_last_name(self):
        """Search should match partial last name."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        request = factory.get('/mswdo/user-accounts/', {'search': 'Cruz'})
        request.user = self.mswdo_user
        
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cruz', str(response.content))
        self.assertNotIn('Santos', str(response.content))

    def test_search_by_email(self):
        """Search should match partial email."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        request = factory.get('/mswdo/user-accounts/', {'search': 'maria.santos'})
        request.user = self.mswdo_user
        
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Maria Santos', str(response.content))
        self.assertNotIn('Juan Cruz', str(response.content))

    def test_search_by_username(self):
        """Search should match partial username."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        request = factory.get('/mswdo/user-accounts/', {'search': 'staff_juan'})
        request.user = self.mswdo_user
        
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Juan Cruz', str(response.content))

    def test_search_combined_with_role_filter(self):
        """Search combined with role filter should use AND logic."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        # Search for "Maria" but filter by BARANGAY role
        # Maria Santos is MSWDO_STAFF, Ana Garcia is BARANGAY with middle name Maria
        request = factory.get('/mswdo/user-accounts/', {'search': 'Maria', 'role': 'BARANGAY'})
        request.user = self.mswdo_user
        
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        # Should find Ana Garcia (BARANGAY, middle name Maria)
        self.assertIn('Ana Garcia', str(response.content))
        # Should NOT find Maria Santos (MSWDO_STAFF)
        self.assertNotIn('Maria Santos', str(response.content))

    def test_search_combined_with_barangay_filter(self):
        """Search combined with barangay filter should use AND logic."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        # Search for "Reyes" and filter by barangay
        request = factory.get('/mswdo/user-accounts/', {'search': 'Reyes', 'role': 'BARANGAY', 'barangay': str(self.barangay.id)})
        request.user = self.mswdo_user
        
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('Pedro Reyes', str(response.content))
        self.assertNotIn('Juan Cruz', str(response.content))

    def test_empty_search_returns_all(self):
        """Empty or whitespace-only search should return unfiltered results."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        request = factory.get('/mswdo/user-accounts/', {'search': '   '})
        request.user = self.mswdo_user
        
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        # Should return all non-MSWDO users
        self.assertIn('Juan Cruz', str(response.content))
        self.assertIn('Maria Santos', str(response.content))
        self.assertIn('Pedro Reyes', str(response.content))
        self.assertIn('Ana Garcia', str(response.content))

    def test_no_search_param_returns_all(self):
        """No search parameter should return unfiltered results."""
        from django.test import RequestFactory
        from accounts.views import user_accounts
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        
        factory = RequestFactory()
        request = factory.get('/mswdo/user-accounts/')
        request.user = self.mswdo_user
        
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()
        
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        
        response = user_accounts(request)
        
        self.assertEqual(response.status_code, 200)
        # Should return all non-MSWDO users
        self.assertIn('Juan Cruz', str(response.content))
        self.assertIn('Maria Santos', str(response.content))
        self.assertIn('Pedro Reyes', str(response.content))
        self.assertIn('Ana Garcia', str(response.content))


class SessionExpiryTests(TestCase):
    """
    Test suite for session expiry configuration and @session_protected decorator.
    Tests verify that set_expiry is called with correct timeouts for different view types.
    """

    def setUp(self):
        """Create test user and set up request factory."""
        self.mswdo_user = User.objects.create_user(
            username='mswdo_test',
            email='mswdo@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Admin',
            role='MSWDO'
        )
        self.barangay = Barangay.objects.create(name='Test Barangay')
        self.barangay_user = User.objects.create_user(
            username='barangay_test',
            email='barangay@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Barangay',
            role='BARANGAY',
            barangay=self.barangay
        )
        self.factory = RequestFactory()

    def _add_session_to_request(self, request):
        """Helper to add session middleware to a request."""
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()

    def test_session_protected_default_timeout_900(self):
        """@session_protected without arguments should set 15-minute (900s) expiry."""
        from accounts.views import user_accounts
        
        request = self.factory.get('/mswdo/user-accounts/')
        request.user = self.mswdo_user
        self._add_session_to_request(request)
        
        # Call the view
        response = user_accounts(request)
        
        # Verify session expiry was set to 900 seconds
        self.assertEqual(request.session.get_expiry_age(), 900)

    def test_session_protected_scan_rfid_timeout_1800(self):
        """@session_protected(timeout=1800) should set 30-minute expiry for scan_rfid."""
        from distribution.views import scan_rfid
        from programs.models import Program, Assistance, AidCategory
        from distribution.models import AidSchedule
        from django.utils import timezone
        
        # Create minimal required test data (skip household/family to avoid address property issue)
        program = Program.objects.create(name='Test Program')
        category = AidCategory.objects.create(name='Test Category', program=program)
        assistance = Assistance.objects.create(
            program=program,
            aid_category=category,
            beneficiary_type='family'
        )
        schedule = AidSchedule.objects.create(
            assistance=assistance,
            created_by=self.mswdo_user,
            schedule_datetime=timezone.now()
        )
        
        request = self.factory.get(f'/mswdo/schedule/{schedule.id}/rfid/scan/')
        request.user = self.mswdo_user
        self._add_session_to_request(request)
        
        # Call the view (will likely fail due to staff assignment, but decorator should run)
        try:
            response = scan_rfid(request, schedule_id=schedule.id)
        except:
            pass  # Expected to fail due to missing staff assignment, but decorator should have run
        
        # Verify session expiry was set to 1800 seconds
        self.assertEqual(request.session.get_expiry_age(), 1800)

    def test_session_protected_finish_distribution_timeout_1800(self):
        """@session_protected(timeout=1800) should set 30-minute expiry for finish_distribution."""
        from distribution.views import finish_distribution
        from programs.models import Program, Assistance, AidCategory
        from distribution.models import AidSchedule
        from django.utils import timezone
        
        # Create required test data
        program = Program.objects.create(name='Test Program')
        category = AidCategory.objects.create(name='Test Category', program=program)
        assistance = Assistance.objects.create(
            program=program,
            aid_category=category,
            beneficiary_type='family'
        )
        schedule = AidSchedule.objects.create(
            assistance=assistance,
            created_by=self.mswdo_user,
            schedule_datetime=timezone.now()
        )
        
        request = self.factory.post(f'/mswdo/schedule/{schedule.id}/finish/')
        request.user = self.mswdo_user
        self._add_session_to_request(request)
        
        # Call the view (will likely fail due to missing staff assignment, but decorator should run)
        try:
            response = finish_distribution(request, schedule_id=schedule.id)
        except:
            pass  # Expected to fail, but decorator should have run
        
        # Verify session expiry was set to 1800 seconds
        self.assertEqual(request.session.get_expiry_age(), 1800)

    def test_session_protected_generate_report_stub_timeout_1800(self):
        """@session_protected(timeout=1800) should set 30-minute expiry for generate_report_stub."""
        from distribution.views import generate_report_stub
        
        request = self.factory.get('/mswdo/reports/generate-stub/')
        request.user = self.mswdo_user
        self._add_session_to_request(request)
        
        # Call the view
        response = generate_report_stub(request)
        
        # Verify session expiry was set to 1800 seconds
        self.assertEqual(request.session.get_expiry_age(), 1800)

    def test_scan_rfid_post_claim_extends_session(self):
        """POST claim to scan_rfid (without X-Background-Poll header) should call set_expiry(1800)."""
        from distribution.views import scan_rfid
        from distribution.models import AidSchedule
        from programs.models import Assistance, Program, AidCategory
        from accounts.models import Barangay
        
        # Create minimal test data
        program = Program.objects.create(name='Test Program')
        category = AidCategory.objects.create(name='Test Category', program=program)
        assistance = Assistance.objects.create(
            program=program,
            aid_category=category,
            beneficiary_type='family'
        )
        schedule = AidSchedule.objects.create(
            assistance=assistance,
            schedule_datetime=timezone.now(),
            is_active=True,
            is_finished=False
        )
        
        # Create POST request (real RFID claim, no background poll header)
        request = self.factory.post(f'/distribution/scan/{schedule.id}/', {
            'rfid_uid': 'test123'
        })
        request.user = self.barangay_user
        self._add_session_to_request(request)
        
        # Call the view - it may fail due to missing family, but decorator should run
        try:
            response = scan_rfid(request, schedule_id=schedule.id)
        except:
            pass  # Expected to fail, but decorator should have run
        
        # Verify session expiry was set to 1800 seconds (POST without header extends session)
        self.assertEqual(request.session.get_expiry_age(), 1800)

    def test_scan_rfid_get_with_background_poll_skips_expiry(self):
        """GET to scan_rfid with X-Background-Poll header should NOT call set_expiry()."""
        from distribution.views import scan_rfid
        from distribution.models import AidSchedule
        from programs.models import Assistance, Program, AidCategory
        from accounts.models import Barangay
        
        # Create minimal test data
        program = Program.objects.create(name='Test Program')
        category = AidCategory.objects.create(name='Test Category', program=program)
        assistance = Assistance.objects.create(
            program=program,
            aid_category=category,
            beneficiary_type='family'
        )
        schedule = AidSchedule.objects.create(
            assistance=assistance,
            schedule_datetime=timezone.now(),
            is_active=True,
            is_finished=False
        )
        
        # Create GET request with X-Background-Poll header (polling request)
        request = self.factory.get(f'/distribution/scan/{schedule.id}/')
        request.user = self.barangay_user
        request.META['HTTP_X_BACKGROUND_POLL'] = 'true'
        self._add_session_to_request(request)
        
        # Set initial expiry to a known value
        request.session.set_expiry(900)
        initial_expiry = request.session.get_expiry_age()
        
        # Call the view - it may fail due to missing staff assignment, but decorator should run
        try:
            response = scan_rfid(request, schedule_id=schedule.id)
        except:
            pass  # Expected to fail, but decorator should have run
        
        # Verify session expiry was NOT changed (still 900, not reset to 1800)
        # The decorator should skip set_expiry() when X-Background-Poll header is present
        self.assertEqual(request.session.get_expiry_age(), initial_expiry)

    def test_session_save_every_request_does_not_extend_polling_expiry(self):
        """SESSION_SAVE_EVERY_REQUEST should NOT extend expiry for polling endpoints."""
        from django.contrib.sessions.models import Session
        from monitoring.views import schedule_status
        
        # Authenticate user via client to create real session in database
        self.client.login(username='mswdo_test', password='testpass123')
        
        # Get the session from database
        session_key = self.client.session.session_key
        session_before = Session.objects.get(session_key=session_key)
        expire_date_before = session_before.expire_date
        
        # Wait a tiny bit to ensure timestamp difference would be detectable
        import time
        time.sleep(0.1)
        
        # Hit the polling endpoint (schedule_status with extend_session=False)
        response = self.client.get('/monitoring/schedule-status/')
        
        # Get the session from database again
        session_after = Session.objects.get(session_key=session_key)
        expire_date_after = session_after.expire_date
        
        # The expire_date should NOT have changed
        # If SESSION_SAVE_EVERY_REQUEST=True is extending it, this will fail
        self.assertEqual(expire_date_before, expire_date_after,
                        "SESSION_SAVE_EVERY_REQUEST is extending expiry for polling endpoints")

    def test_session_cookie_secure_is_boolean(self):
        """SESSION_COOKIE_SECURE is defined as a boolean in settings.py."""
        from django.conf import settings
        
        # Verify the setting exists and is a boolean
        self.assertIsNotNone(settings.SESSION_COOKIE_SECURE)
        self.assertIsInstance(settings.SESSION_COOKIE_SECURE, bool)
        # In settings.py it's defined as SESSION_COOKIE_SECURE = not DEBUG
        # This verifies the setting is properly configured

    @override_settings(DEBUG=True)
    def test_session_save_every_request_disabled(self):
        """SESSION_SAVE_EVERY_REQUEST should be False - decorator handles set_expiry explicitly."""
        from django.conf import settings
        
        self.assertEqual(settings.SESSION_SAVE_EVERY_REQUEST, False)

    def test_logout_endpoint_invalidates_session(self):
        """Logout endpoint should properly invalidate the session when called."""
        from django.contrib.sessions.models import Session
        
        # Login user via client
        self.client.login(username='mswdo_test', password='testpass123')
        
        # Get session key from the client
        session_key = self.client.session.session_key
        
        # Verify session exists in database
        self.assertTrue(Session.objects.filter(session_key=session_key).exists())
        
        # Call logout endpoint
        response = self.client.post('/logout/')
        
        # Verify redirect (logout view redirects to landing page)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/') or response.url.endswith('/landing/'))
        
        # Verify session is deleted from database
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

    @override_settings(DEBUG=True)
    def test_session_cookie_age_1800(self):
        """SESSION_COOKIE_AGE should be 1800 (30 minutes)."""
        from django.conf import settings
        
        self.assertEqual(settings.SESSION_COOKIE_AGE, 1800)
