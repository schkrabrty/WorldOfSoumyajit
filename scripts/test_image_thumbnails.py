#!/usr/bin/env python3
"""Verify actual image dimensions, EXIF rotation, alpha, and source preservation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
    from image_thumbnails import create_thumbnail
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "Run tests with .site-manager/images-venv/bin/python3 or install scripts/requirements-images.txt")
class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source, self.small = self.root / "original", self.root / "small.webp"

    def tearDown(self): self.temp.cleanup()

    def test_landscape_keeps_proportions_and_original_bytes(self):
        Image.new("RGB", (2400, 1600), "orange").save(self.source, "JPEG")
        before = self.source.read_bytes()
        result = create_thumbnail(self.source, self.small)
        self.assertEqual((result["width"], result["height"]), (800, 533))
        self.assertEqual(self.source.read_bytes(), before)
        with Image.open(self.small) as image: self.assertEqual(image.format, "WEBP")
        self.assertLess(self.small.stat().st_size, self.source.stat().st_size)

    def test_exif_portrait_is_rotated_and_location_metadata_removed(self):
        exif = Image.Exif();exif[274] = 6;exif[270] = "Private camera information"
        Image.new("RGB", (2400, 1600), "purple").save(self.source, "JPEG", exif=exif)
        result = create_thumbnail(self.source, self.small)
        self.assertEqual((result["width"], result["height"]), (533, 800))
        with Image.open(self.small) as image: self.assertFalse(image.getexif())

    def test_small_images_are_never_upscaled(self):
        Image.new("RGB", (120, 80), "green").save(self.source, "PNG")
        result = create_thumbnail(self.source, self.small)
        self.assertEqual((result["width"], result["height"]), (120, 80))

    def test_transparency_is_preserved_for_rgba_and_grayscale_alpha(self):
        for mode, color in [("RGBA", (255, 0, 0, 0)), ("LA", (100, 0))]:
            with self.subTest(mode=mode):
                Image.new(mode, (100, 100), color).save(self.source, "PNG")
                create_thumbnail(self.source, self.small)
                with Image.open(self.small) as image: self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_animated_picture_uses_static_preview_and_keeps_original_animation(self):
        frames = [Image.new("RGB", (100, 50), color) for color in ["red", "blue"]]
        frames[0].save(self.source, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        before = self.source.read_bytes()
        create_thumbnail(self.source, self.small)
        with Image.open(self.small) as image: self.assertFalse(getattr(image, "is_animated", False))
        self.assertEqual(self.source.read_bytes(), before)

    def test_corrupt_picture_fails_without_writing_a_derivative(self):
        self.source.write_bytes(b"not actually a photo")
        with self.assertRaises(OSError): create_thumbnail(self.source, self.small)
        self.assertFalse(self.small.exists())

    def test_pixel_budget_rejects_large_images_before_rendering(self):
        Image.new("RGB", (100, 100)).save(self.source, "PNG")
        with patch.object(Image, "MAX_IMAGE_PIXELS", 9000), self.assertRaises(Image.DecompressionBombWarning):
            create_thumbnail(self.source, self.small)
        self.assertFalse(self.small.exists())


if __name__ == "__main__": unittest.main()
