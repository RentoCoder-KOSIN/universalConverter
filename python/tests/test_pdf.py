import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from converter.main import convert

try:
    import pypdf
    import pypdfium2  # noqa: F401
    from PIL import Image
except ImportError:  # ライブラリ未導入の環境ではスキップする
    pypdf = None


def make_text_pdf(text="Hello PDF"):
    """文字を 1 行だけ持つ最小の PDF（200 x 100 pt）を作る。"""

    stream = f"BT /F1 24 Tf 10 40 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@unittest.skipIf(pypdf is None, "pypdf / pypdfium2 / Pillow が入っていないためスキップ")
class PdfTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def blank_pdf(self, pages=1, width=200, height=100, password=None, name="blank.pdf"):
        writer = pypdf.PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=width, height=height)
        if password:
            writer.encrypt(password)
        path = self.tmp / name
        with open(path, "wb") as file:
            writer.write(file)
        return path

    def text_pdf(self, text="Hello PDF"):
        path = self.tmp / "text.pdf"
        path.write_bytes(make_text_pdf(text))
        return path

    # ---- PDF → テキスト ----

    def test_text_is_extracted(self):
        out = self.tmp / "o.txt"
        convert("pdf_to_txt", self.text_pdf("Hello PDF"), out)
        self.assertIn("Hello PDF", out.read_text(encoding="utf-8"))

    def test_pdf_without_text_is_rejected_with_helpful_message(self):
        with self.assertRaises(ValueError) as ctx:
            convert("pdf_to_txt", self.blank_pdf(), self.tmp / "o.txt")
        self.assertIn("テキストを取り出せません", str(ctx.exception))

    def test_too_many_pages_for_text(self):
        from converter.formats import pdf as module
        original = module.MAX_TEXT_PAGES
        module.MAX_TEXT_PAGES = 2
        try:
            with self.assertRaises(ValueError):
                convert("pdf_to_txt", self.blank_pdf(pages=3), self.tmp / "o.txt")
        finally:
            module.MAX_TEXT_PAGES = original

    # ---- PDF → 画像 ----

    def test_first_page_to_png(self):
        out = self.tmp / "o.png"
        convert("pdf_first_page_to_png", self.blank_pdf(pages=3), out)
        with Image.open(out) as image:
            self.assertEqual(image.format, "PNG")
            # 200 x 100 pt を 150 dpi にすると約 417 x 208 px
            self.assertAlmostEqual(image.width, 417, delta=2)
            self.assertAlmostEqual(image.height, 208, delta=2)

    def test_selected_page_to_png(self):
        out = self.tmp / "page.png"
        convert("pdf_page_to_png", self.blank_pdf(pages=3), out, page_number=2)
        with Image.open(out) as image:
            self.assertEqual(image.format, "PNG")
            self.assertAlmostEqual(image.width, 417, delta=2)

    def test_selected_page_must_exist(self):
        with self.assertRaisesRegex(ValueError, "指定したページがありません"):
            convert("pdf_page_to_png", self.blank_pdf(pages=1), self.tmp / "o.png", page_number=2)

    def test_png_zip_has_one_image_per_page(self):
        out = self.tmp / "o.zip"
        convert("pdf_to_png_zip", self.blank_pdf(pages=3), out)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(archive.namelist(), ["page_001.png", "page_002.png", "page_003.png"])
            Image.open(io.BytesIO(archive.read("page_002.png"))).verify()

    def test_too_many_pages_for_images(self):
        from converter.formats import pdf as module
        original = module.MAX_IMAGE_PAGES
        module.MAX_IMAGE_PAGES = 2
        try:
            with self.assertRaises(ValueError):
                convert("pdf_to_png_zip", self.blank_pdf(pages=3), self.tmp / "o.zip")
        finally:
            module.MAX_IMAGE_PAGES = original

    def test_huge_page_is_scaled_down_to_pixel_limit(self):
        from converter.formats import pdf as module
        original = module.MAX_RENDER_PIXELS
        module.MAX_RENDER_PIXELS = 40_000
        try:
            out = self.tmp / "o.png"
            convert("pdf_first_page_to_png", self.blank_pdf(width=14000, height=14000), out)
            with Image.open(out) as image:
                self.assertLessEqual(image.width * image.height, 40_000 * 1.05)
        finally:
            module.MAX_RENDER_PIXELS = original

    # ---- 異常系 ----

    def test_encrypted_pdf_is_rejected_by_all_operations(self):
        src = self.blank_pdf(password="secret", name="locked.pdf")
        for op, ext in [
            ("pdf_to_txt", "txt"),
            ("pdf_first_page_to_png", "png"),
            ("pdf_page_to_png", "png"),
            ("pdf_to_png_zip", "zip"),
        ]:
            with self.subTest(op=op):
                with self.assertRaises(ValueError) as ctx:
                    if op == "pdf_page_to_png":
                        convert(op, src, self.tmp / f"o.{ext}", page_number=1)
                    else:
                        convert(op, src, self.tmp / f"o.{ext}")
                self.assertIn("パスワード", str(ctx.exception))

    def test_not_a_pdf_is_rejected_by_all_operations(self):
        src = self.tmp / "fake.pdf"
        src.write_text("これは PDF ではありません")
        for op, ext in [
            ("pdf_to_txt", "txt"),
            ("pdf_first_page_to_png", "png"),
            ("pdf_page_to_png", "png"),
            ("pdf_to_png_zip", "zip"),
        ]:
            with self.subTest(op=op):
                with self.assertRaises(ValueError):
                    if op == "pdf_page_to_png":
                        convert(op, src, self.tmp / f"o.{ext}", page_number=1)
                    else:
                        convert(op, src, self.tmp / f"o.{ext}")

    def test_empty_and_truncated_pdf_are_rejected(self):
        good = make_text_pdf()
        for name, data in [("empty.pdf", b""), ("cut.pdf", good[:60])]:
            src = self.tmp / name
            src.write_bytes(data)
            for op, ext in [("pdf_to_txt", "txt"), ("pdf_first_page_to_png", "png")]:
                with self.subTest(file=name, op=op):
                    with self.assertRaises(ValueError):
                        convert(op, src, self.tmp / f"o.{ext}")

    # ---- 画像 → PDF ----

    def test_image_to_pdf(self):
        src = self.tmp / "a.png"
        Image.new("RGB", (300, 150), (200, 30, 30)).save(src)
        out = self.tmp / "o.pdf"
        convert("image_to_pdf", src, out)
        reader = pypdf.PdfReader(str(out))
        self.assertEqual(len(reader.pages), 1)
        # 300 x 150 px を 150 dpi にすると 144 x 72 pt
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 144, delta=1)

    def test_rgba_image_to_pdf(self):
        src = self.tmp / "a.png"
        Image.new("RGBA", (30, 30), (0, 0, 0, 0)).save(src)
        convert("image_to_pdf", src, self.tmp / "o.pdf")

    def test_non_image_to_pdf_is_rejected(self):
        src = self.tmp / "a.png"
        src.write_text("画像ではありません")
        with self.assertRaises(ValueError):
            convert("image_to_pdf", src, self.tmp / "o.pdf")

    def test_pdf_round_trip(self):
        png = self.tmp / "a.png"
        Image.new("RGB", (300, 150), (10, 120, 10)).save(png)
        pdf = self.tmp / "m.pdf"
        convert("image_to_pdf", png, pdf)
        back = self.tmp / "b.png"
        convert("pdf_first_page_to_png", pdf, back)
        with Image.open(back) as image:
            r, g, b = image.convert("RGB").getpixel((10, 10))
            self.assertGreater(g, r)  # 緑のまま


if __name__ == "__main__":
    unittest.main()
