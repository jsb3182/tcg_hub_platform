import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tcg_worker.media import CELL, InvalidImage, encode_sheet, normalized_png, place_cell


class MediaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)

    def test_preserves_aspect_and_pads_transparency(self):
        source = self.directory / "square.png"
        Image.new("RGBA", (800, 800), (255, 0, 0, 128)).save(source)
        with Image.open(io.BytesIO(normalized_png(source))) as cell:
            self.assertEqual(cell.size, CELL)
            self.assertEqual(cell.getpixel((0, 0)), (24, 24, 24))
            self.assertEqual(cell.getpixel((150, 219)), (140, 12, 12))

    def test_verifies_extension_signature_and_size(self):
        image = self.directory / "wrong.webp"
        Image.new("RGB", (2, 2)).save(image, format="JPEG")
        with self.assertRaises(InvalidImage):
            normalized_png(image)
        huge = self.directory / "huge.png"
        Image.new("1", (4000, 4000)).save(huge)
        with self.assertRaises(InvalidImage):
            normalized_png(huge)
        huge.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
        with self.assertRaises(InvalidImage):
            normalized_png(huge)

    def test_sheet_edges_and_quality(self):
        source = self.directory / "red.jpg"
        Image.new("RGB", CELL, "red").save(source)
        sheet = Image.new("RGB", (1200, 1314))
        data = normalized_png(source)
        self.assertEqual(place_cell(sheet, data, 0), (0, 0))
        self.assertEqual(place_cell(sheet, data, 11), (3, 2))
        with self.assertRaises(ValueError):
            place_cell(sheet, data, 12)
        with Image.open(io.BytesIO(encode_sheet(sheet))) as result:
            self.assertEqual((result.format, result.size), ("WEBP", (1200, 1314)))
            self.assertGreater(result.getpixel((1050, 1095))[0], 240)
            self.assertLess(result.getpixel((450, 219))[0], 8)
