import json
import tempfile
import unittest
from pathlib import Path

from converter.main import convert


class TextTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write_bytes(self, name, data):
        path = self.tmp / name
        path.write_bytes(data)
        return path


class JsonFormatTest(TextTestCase):
    def test_formats_with_indent_and_keeps_japanese(self):
        src = self.write_bytes("a.json", '{"b":1,"a":"田中"}'.encode("utf-8"))
        out = self.tmp / "o.json"
        convert("json_format", src, out)
        text = out.read_text(encoding="utf-8")
        self.assertEqual(text, '{\n  "b": 1,\n  "a": "田中"\n}\n')

    def test_keeps_key_order(self):
        src = self.write_bytes("a.json", b'{"z":1,"a":2}')
        out = self.tmp / "o.json"
        convert("json_format", src, out)
        self.assertEqual(list(json.loads(out.read_text(encoding="utf-8"))), ["z", "a"])

    def test_bom(self):
        src = self.write_bytes("a.json", b"\xef\xbb\xbf[1]")
        out = self.tmp / "o.json"
        convert("json_format", src, out)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), [1])

    def test_invalid_json(self):
        src = self.write_bytes("a.json", b"{not json")
        with self.assertRaises(ValueError):
            convert("json_format", src, self.tmp / "o.json")

    def test_empty_file(self):
        src = self.write_bytes("a.json", b"")
        with self.assertRaises(ValueError):
            convert("json_format", src, self.tmp / "o.json")


class TxtToUtf8Test(TextTestCase):
    TEXT = "名前,年齢\r\n田中,18\r\n"

    def convert_bytes(self, data):
        src = self.write_bytes("a.txt", data)
        out = self.tmp / "o.txt"
        convert("txt_to_utf8", src, out)
        return out.read_bytes()

    def test_utf8_is_kept(self):
        self.assertEqual(self.convert_bytes(self.TEXT.encode("utf-8")), self.TEXT.encode("utf-8"))

    def test_utf8_bom_is_removed(self):
        result = self.convert_bytes(b"\xef\xbb\xbf" + self.TEXT.encode("utf-8"))
        self.assertEqual(result, self.TEXT.encode("utf-8"))

    def test_shift_jis(self):
        self.assertEqual(self.convert_bytes(self.TEXT.encode("cp932")), self.TEXT.encode("utf-8"))

    def test_euc_jp(self):
        text = "これはEUC-JPのテキストです。\n"
        self.assertEqual(self.convert_bytes(text.encode("euc_jp")), text.encode("utf-8"))

    def test_utf16_with_bom(self):
        self.assertEqual(self.convert_bytes(self.TEXT.encode("utf-16")), self.TEXT.encode("utf-8"))

    def test_newlines_are_not_changed(self):
        result = self.convert_bytes("a\r\nb\nc\r".encode("cp932"))
        self.assertEqual(result, b"a\r\nb\nc\r")

    def test_binary_is_rejected(self):
        with self.assertRaises(ValueError):
            self.convert_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    def test_undecodable_is_rejected(self):
        with self.assertRaises(ValueError):
            self.convert_bytes(b"\xff\xff\xff\xfe\x80\x81")

    def test_empty_file(self):
        self.assertEqual(self.convert_bytes(b""), b"")


if __name__ == "__main__":
    unittest.main()
