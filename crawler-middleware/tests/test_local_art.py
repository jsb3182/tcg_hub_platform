import io
import unittest
from PIL import Image

from tcg_worker.local_art import capture_hash, delay_after, pokemon_target, provider, webp


class LocalArtTests(unittest.TestCase):
    def test_only_known_origins_and_paths(self):
        approved = "https://artworks-ko-db.ygoresources.com/0/40/7_1.png"
        self.assertEqual(provider(approved), "artworks-ko-db.ygoresources.com")
        for value in (approved+"?redirect=1", approved.replace("https:", "http:"),
                      approved.replace(".com/", ".com:100/"), approved.replace(".com/", ".com.invalid/"),
                      approved.replace(".com/", ".com@127.0.0.1/"), approved.replace("/0/", "/%2e%2e/"),
                      "http://nivelarena.co.kr/admin/photo.jpg", "https://evil.invalid/0/40/7_1.png"):
            self.assertIsNone(provider(value), value)
        self.assertTrue(provider("http://nivelarena.co.kr/data/file/cardlists/thumb-safe_225x315.jpg"))
        self.assertTrue(provider("https://en.ws-tcg.com/wordpress/wp-content/images/cardimages/5HYM/W101_E100.png"))
        self.assertIsNone(provider("http://en.ws-tcg.com/wordpress/wp-content/images/cardimages/5HYM/W101_E100.png"))
        self.assertEqual(delay_after("9000"), 9000)

    def test_encoded_pixels_determine_capture_hash(self):
        image = Image.new("RGB", (1000, 800))
        image.paste("white", (0, 0, 500, 800))
        buf = io.BytesIO()
        image.save(buf, "PNG")
        encoded = webp(buf.getvalue())
        with Image.open(io.BytesIO(encoded)) as result:
            self.assertEqual((result.format, result.size), ("WEBP", (480,384)))
        self.assertRegex(capture_hash(encoded), r"^[01]{64}$")
        lossless = io.BytesIO()
        image.save(lossless, "WEBP", lossless=True)
        self.assertEqual(capture_hash(lossless.getvalue()), "00010000"*8)
        blank = io.BytesIO()
        Image.new("RGB", (1,1)).save(blank, "WEBP")
        self.assertEqual(capture_hash(blank.getvalue()), "0"*64)
        with self.assertRaises((OSError, ValueError)):
            webp(b"<html>not a card</html>")
        image2 = io.BytesIO()
        Image.new("1", (4000, 4000)).save(image2,"PNG")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            webp(image2.getvalue())

    def test_moved_pokemon_image_requires_same_publisher_and_exact_printed_asset(self):
        page = "https://pokemoncard.co.kr/cards/detail/BS2014001001"
        before = "https://cards.image.pokemonkorea.co.kr/data/wmimages/XY/XY1/K1_X_001.jpg"
        path = "/public-assets/home/data/cards.image_www/data/wmimages/XY/XY1/K1_X_001.webp?w=512"
        img = '<img class="feature_image" src="'+path+'">'
        self.assertEqual(pokemon_target(img,page,before), "https://pokemoncard.co.kr"+path)
        for invalid in (img+img, img.replace("K1_X_001", "K1_X_002"), img.replace(path, "https://other.test"+path)):
            self.assertIsNone(pokemon_target(invalid,page,before))
