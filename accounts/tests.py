from django.test import TestCase
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
from accounts.utils import validate_image_file


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

