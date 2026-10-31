import io
import json
import struct
import tarfile
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from converter.main import convert


class ArchiveTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tmp = self.root / "work"
        self.tmp.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def make_zip(self, entries, name="a.zip"):
        """entries: {名前: bytes}（名前が / で終わるものはディレクトリ）"""
        path = self.tmp / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry_name, data in entries.items():
                archive.writestr(entry_name, data)
        return path

    def make_targz(self, members, name="a.tar.gz"):
        """members: [(TarInfo, bytes または None)]"""
        path = self.tmp / name
        with tarfile.open(path, "w:gz") as archive:
            for info, data in members:
                archive.addfile(info, io.BytesIO(data) if data is not None else None)
        return path

    @staticmethod
    def tar_file(name, data):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mtime = time.time()
        return info, data

    def no_escape(self, filename):
        """作業ディレクトリの外にファイルが書き出されていないこと。"""
        self.assertFalse((self.root / filename).exists())
        self.assertFalse(Path("/tmp", filename).exists())


class ZipToTarGzTest(ArchiveTestCase):
    def test_normal_with_directory_and_japanese_name(self):
        src = self.make_zip({"docs/": b"", "docs/メモ.txt": "こんにちは".encode("utf-8"), "a.txt": b"A"})
        out = self.tmp / "o.tar.gz"
        convert("zip_to_targz", src, out)
        with tarfile.open(out, "r:gz") as archive:
            names = archive.getnames()
            self.assertEqual(sorted(names), ["a.txt", "docs", "docs/メモ.txt"])
            self.assertEqual(archive.extractfile("docs/メモ.txt").read().decode("utf-8"), "こんにちは")
            member = archive.getmember("a.txt")
            self.assertEqual((member.uid, member.gid, member.mode), (0, 0, 0o644))

    def test_path_traversal_is_rejected(self):
        for evil in ["../evil.txt", "a/../../evil.txt", "..\\evil.txt", "a\\..\\..\\evil.txt"]:
            with self.subTest(name=evil):
                src = self.make_zip({evil: b"x"})
                with self.assertRaises(ValueError):
                    convert("zip_to_targz", src, self.tmp / "o.tar.gz")
                self.no_escape("evil.txt")

    def test_absolute_paths_are_rejected(self):
        for evil in ["/etc/passwd", "C:\\Windows\\x.txt", "c:/x.txt"]:
            with self.subTest(name=evil):
                src = self.make_zip({evil: b"x"})
                with self.assertRaises(ValueError):
                    convert("zip_to_targz", src, self.tmp / "o.tar.gz")

    def test_symlink_is_rejected(self):
        path = self.tmp / "link.zip"
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo("link")
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "/etc/passwd")
        with self.assertRaises(ValueError):
            convert("zip_to_targz", path, self.tmp / "o.tar.gz")

    def test_encrypted_entry_is_rejected(self):
        src = self.make_zip({"a.txt": b"secret"})
        data = bytearray(src.read_bytes())
        # ローカルヘッダ（PK\x03\x04）とセントラルディレクトリ（PK\x01\x02）の暗号化フラグを立てる
        local = data.index(b"PK\x03\x04")
        central = data.index(b"PK\x01\x02")
        for offset in (local + 6, central + 8):
            flags = struct.unpack_from("<H", data, offset)[0] | 0x1
            struct.pack_into("<H", data, offset, flags)
        src.write_bytes(bytes(data))
        with self.assertRaises(ValueError) as ctx:
            convert("zip_to_targz", src, self.tmp / "o.tar.gz")
        self.assertIn("パスワード", str(ctx.exception))

    def test_too_many_entries(self):
        from converter.formats import archive as module
        original = module.MAX_ENTRIES
        module.MAX_ENTRIES = 3
        try:
            src = self.make_zip({f"f{i}.txt": b"x" for i in range(5)})
            with self.assertRaises(ValueError):
                convert("zip_to_targz", src, self.tmp / "o.tar.gz")
        finally:
            module.MAX_ENTRIES = original

    def test_total_size_limit(self):
        from converter.formats import archive as module
        original = module.MAX_TOTAL_BYTES
        module.MAX_TOTAL_BYTES = 100
        try:
            src = self.make_zip({"big.txt": b"abcdefghij" * 20})
            with self.assertRaises(ValueError) as ctx:
                convert("zip_to_targz", src, self.tmp / "o.tar.gz")
            self.assertIn("大きすぎ", str(ctx.exception))
        finally:
            module.MAX_TOTAL_BYTES = original

    def test_zip_bomb_ratio_is_rejected(self):
        src = self.make_zip({"zeros.bin": b"\x00" * (3 * 1024 * 1024)})  # 3MB が数 KB に圧縮される
        with self.assertRaises(ValueError) as ctx:
            convert("zip_to_targz", src, self.tmp / "o.tar.gz")
        self.assertIn("圧縮率", str(ctx.exception))

    def test_not_a_zip_empty_and_corrupted(self):
        good = self.make_zip({"a.txt": b"hello" * 100})
        cases = {
            "text.zip": b"not a zip",
            "empty.zip": b"",
            "cut.zip": good.read_bytes()[:30],
        }
        for name, data in cases.items():
            with self.subTest(file=name):
                src = self.tmp / name
                src.write_bytes(data)
                with self.assertRaises(ValueError):
                    convert("zip_to_targz", src, self.tmp / "o.tar.gz")

    def test_corrupted_data_is_rejected(self):
        src = self.make_zip({"a.txt": bytes(range(256)) * 50})
        data = bytearray(src.read_bytes())
        data[60] ^= 0xFF  # 圧縮データの一部を壊す
        src.write_bytes(bytes(data))
        with self.assertRaises(ValueError):
            convert("zip_to_targz", src, self.tmp / "o.tar.gz")


class TarGzToZipTest(ArchiveTestCase):
    def test_normal(self):
        dir_info = tarfile.TarInfo("docs")
        dir_info.type = tarfile.DIRTYPE
        src = self.make_targz([
            (dir_info, None),
            self.tar_file("docs/メモ.txt", "こんにちは".encode("utf-8")),
            self.tar_file("./a.txt", b"A"),
        ])
        out = self.tmp / "o.zip"
        convert("targz_to_zip", src, out)
        with zipfile.ZipFile(out) as archive:
            self.assertEqual(sorted(archive.namelist()), ["a.txt", "docs/", "docs/メモ.txt"])
            self.assertEqual(archive.read("docs/メモ.txt").decode("utf-8"), "こんにちは")
            self.assertIsNone(archive.testzip())

    def test_round_trip(self):
        original = {"a.txt": b"A" * 10, "dir/b.bin": bytes(range(256))}
        zip_path = self.make_zip(original)
        tar_path = self.tmp / "m.tar.gz"
        convert("zip_to_targz", zip_path, tar_path)
        back = self.tmp / "b.zip"
        convert("targz_to_zip", tar_path, back)
        with zipfile.ZipFile(back) as archive:
            for name, data in original.items():
                self.assertEqual(archive.read(name), data)

    def test_path_traversal_is_rejected(self):
        src = self.make_targz([self.tar_file("../evil.txt", b"x")])
        with self.assertRaises(ValueError):
            convert("targz_to_zip", src, self.tmp / "o.zip")
        self.no_escape("evil.txt")

    def test_absolute_path_is_rejected(self):
        src = self.make_targz([self.tar_file("/etc/evil.txt", b"x")])
        with self.assertRaises(ValueError):
            convert("targz_to_zip", src, self.tmp / "o.zip")

    def test_symlink_hardlink_and_device_are_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                info = tarfile.TarInfo("link")
                info.type = kind
                info.linkname = "/etc/passwd"
                src = self.make_targz([(info, None)])
                with self.assertRaises(ValueError):
                    convert("targz_to_zip", src, self.tmp / "o.zip")

    def test_total_size_limit(self):
        from converter.formats import archive as module
        original = module.MAX_TOTAL_BYTES
        module.MAX_TOTAL_BYTES = 100
        try:
            src = self.make_targz([self.tar_file("big.txt", b"x" * 500)])
            with self.assertRaises(ValueError):
                convert("targz_to_zip", src, self.tmp / "o.zip")
        finally:
            module.MAX_TOTAL_BYTES = original

    def test_too_many_entries(self):
        from converter.formats import archive as module
        original = module.MAX_ENTRIES
        module.MAX_ENTRIES = 3
        try:
            src = self.make_targz([self.tar_file(f"f{i}.txt", b"x") for i in range(5)])
            with self.assertRaises(ValueError):
                convert("targz_to_zip", src, self.tmp / "o.zip")
        finally:
            module.MAX_ENTRIES = original

    def test_not_targz_empty_and_corrupted(self):
        good = self.make_targz([self.tar_file("a.txt", b"hello" * 100)])
        cases = {"text.gz": b"not a gz", "empty.gz": b"", "cut.gz": good.read_bytes()[:40]}
        for name, data in cases.items():
            with self.subTest(file=name):
                src = self.tmp / name
                src.write_bytes(data)
                with self.assertRaises(ValueError):
                    convert("targz_to_zip", src, self.tmp / "o.zip")

    def test_plain_zip_is_rejected(self):
        src = self.make_zip({"a.txt": b"x"}, name="actually.gz")
        with self.assertRaises(ValueError):
            convert("targz_to_zip", src, self.tmp / "o.zip")


class ZipInfoTest(ArchiveTestCase):
    def info(self, src):
        out = self.tmp / "info.json"
        convert("zip_info", src, out)
        return json.loads(out.read_text(encoding="utf-8"))

    def test_lists_entries(self):
        src = self.make_zip({"docs/": b"", "docs/メモ.txt": b"12345", "a.txt": b"AB"})
        result = self.info(src)
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["total_size"], 7)
        self.assertEqual({e["name"] for e in result["entries"]}, {"docs/", "docs/メモ.txt", "a.txt"})
        self.assertEqual(result["warnings"], [])

    def test_unsafe_entries_are_reported_not_fatal(self):
        src = self.make_zip({"../evil.txt": b"x", "ok.txt": b"y"})
        result = self.info(src)
        self.assertEqual(result["count"], 2)
        self.assertTrue(any("evil.txt" in w for w in result["warnings"]))
        self.no_escape("evil.txt")

    def test_bomb_is_reported(self):
        src = self.make_zip({"zeros.bin": b"\x00" * (3 * 1024 * 1024)})
        result = self.info(src)
        self.assertTrue(any("圧縮率" in w for w in result["warnings"]))

    def test_not_a_zip(self):
        src = self.tmp / "a.zip"
        src.write_bytes(b"not a zip")
        with self.assertRaises(ValueError):
            convert("zip_info", src, self.tmp / "o.json")

    def test_empty_zip_is_valid(self):
        src = self.make_zip({})
        self.assertEqual(self.info(src)["count"], 0)


if __name__ == "__main__":
    unittest.main()
