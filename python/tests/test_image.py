import tempfile
import unittest
from pathlib import Path

from converter.main import convert

try:
    from PIL import Image
except ImportError:  # Pillow 未導入の環境ではこのファイルのテストをスキップする
    Image = None


@unittest.skipIf(Image is None, "Pillow が入っていないためスキップ")
class ImageConvertTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def make_image(self, name, mode="RGB", size=(8, 6), color=None, fmt=None, **save_kwargs):
        path = self.tmp / name
        color = color if color is not None else {"RGB": (200, 30, 30), "RGBA": (200, 30, 30, 128)}.get(mode, 100)
        Image.new(mode, size, color).save(path, format=fmt, **save_kwargs)
        return path

    def run_convert(self, op, src, out_name):
        out = self.tmp / out_name
        convert(op, src, out)
        return out

    def test_png_to_each_format(self):
        src = self.make_image("a.png", fmt="PNG")
        for op, ext, expected in [
            ("image_to_jpeg", "jpg", "JPEG"),
            ("image_to_webp", "webp", "WEBP"),
            ("image_to_bmp", "bmp", "BMP"),
            ("image_to_gif", "gif", "GIF"),
            ("image_to_png", "png", "PNG"),
        ]:
            with self.subTest(op=op):
                out = self.run_convert(op, src, f"o.{ext}")
                with Image.open(out) as result:
                    self.assertEqual(result.format, expected)
                    self.assertEqual(result.size, (8, 6))

    def test_jpeg_to_png(self):
        src = self.make_image("a.jpg", fmt="JPEG")
        out = self.run_convert("image_to_png", src, "o.png")
        with Image.open(out) as result:
            self.assertEqual(result.format, "PNG")

    def test_rgba_to_jpeg_is_flattened_on_white(self):
        src = self.make_image("a.png", mode="RGBA", color=(0, 0, 0, 0), fmt="PNG")
        out = self.run_convert("image_to_jpeg", src, "o.jpg")
        with Image.open(out) as result:
            self.assertEqual(result.mode, "RGB")
            r, g, b = result.getpixel((0, 0))
            self.assertGreater(min(r, g, b), 240)  # 透明部分は白になる

    def test_rgba_png_keeps_alpha_in_webp_and_png(self):
        src = self.make_image("a.png", mode="RGBA", color=(10, 20, 30, 100), fmt="PNG")
        for op, ext in [("image_to_png", "png"), ("image_to_webp", "webp")]:
            with self.subTest(op=op):
                out = self.run_convert(op, src, f"o.{ext}")
                with Image.open(out) as result:
                    self.assertIn("A", result.getbands())

    def test_extension_is_not_trusted(self):
        # 中身は PNG だが拡張子は .jpg
        src = self.make_image("fake.jpg", fmt="PNG")
        out = self.run_convert("image_to_webp", src, "o.webp")
        with Image.open(out) as result:
            self.assertEqual(result.format, "WEBP")

    def test_animated_gif_uses_first_frame(self):
        frames = [Image.new("RGB", (8, 6), c) for c in [(255, 0, 0), (0, 0, 255)]]
        src = self.tmp / "anim.gif"
        frames[0].save(src, save_all=True, append_images=frames[1:], duration=100, loop=0)
        out = self.run_convert("image_to_png", src, "o.png")
        with Image.open(out) as result:
            self.assertEqual(getattr(result, "n_frames", 1), 1)
            r, g, b = result.convert("RGB").getpixel((0, 0))
            self.assertGreater(r, b)  # 先頭フレーム（赤）

    def test_exif_orientation_is_applied_and_metadata_dropped(self):
        img = Image.new("RGB", (8, 4), (10, 10, 10))
        exif = Image.Exif()
        exif[0x0112] = 6  # 90 度回転が必要
        exif[0x010F] = "SecretMaker"
        src = self.tmp / "rot.jpg"
        img.save(src, format="JPEG", exif=exif)
        out = self.run_convert("image_to_jpeg", src, "o.jpg")
        with Image.open(out) as result:
            self.assertEqual(result.size, (4, 8))  # 向きが反映されている
            self.assertNotIn(0x010F, result.getexif())  # メタデータは残らない

    def test_not_an_image(self):
        src = self.tmp / "a.png"
        src.write_text("これは画像ではありません")
        with self.assertRaises(ValueError):
            convert("image_to_png", src, self.tmp / "o.png")

    def test_empty_file(self):
        src = self.tmp / "a.png"
        src.write_bytes(b"")
        with self.assertRaises(ValueError):
            convert("image_to_png", src, self.tmp / "o.png")

    def test_truncated_image(self):
        good = self.make_image("good.png", size=(64, 64), fmt="PNG")
        src = self.tmp / "cut.png"
        src.write_bytes(good.read_bytes()[:40])
        with self.assertRaises(ValueError):
            convert("image_to_jpeg", src, self.tmp / "o.jpg")

    def test_disallowed_format_is_rejected(self):
        src = self.make_image("a.tif", fmt="TIFF")
        with self.assertRaises(ValueError):
            convert("image_to_png", src, self.tmp / "o.png")

    def test_too_large_image_is_rejected(self):
        from converter.formats import image as image_module

        original = image_module.MAX_PIXELS
        image_module.MAX_PIXELS = 100  # 100 画素までに制限
        try:
            src = self.make_image("big.png", size=(50, 50), fmt="PNG")  # 2500 画素
            with self.assertRaises(ValueError) as ctx:
                convert("image_to_png", src, self.tmp / "o.png")
            self.assertIn("大きすぎ", str(ctx.exception))
        finally:
            image_module.MAX_PIXELS = original


class CliMissingLibraryTest(unittest.TestCase):
    def test_import_error_is_reported_as_unavailable(self):
        import json
        import subprocess
        import sys

        code = (
            "import sys; sys.modules['PIL'] = None;"
            "sys.argv = ['main', 'image_to_png', sys.argv[1], sys.argv[2]];"
            "from converter.main import main; main()"
        )
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "a.png"
            src.write_bytes(b"x")
            result = subprocess.run(
                [sys.executable, "-c", code, str(src), str(Path(tmp) / "o.png")],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True, text=True, encoding="utf-8",
            )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "unavailable")
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
