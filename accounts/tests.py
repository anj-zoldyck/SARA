from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
from accounts.utils import validate_image_file
from accounts.models import User, Barangay


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
