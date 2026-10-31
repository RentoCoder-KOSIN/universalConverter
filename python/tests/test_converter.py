import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from converter.main import convert

PYTHON_DIR = Path(__file__).resolve().parent.parent


class ConverterTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, content, encoding="utf-8"):
        path = self.tmp / name
        path.write_bytes(content.encode(encoding))
        return path


class CsvToJsonTest(ConverterTestCase):
    def test_normal(self):
        src = self.write("a.csv", "name,age\n田中,18\n佐藤,17\n")
        out = self.tmp / "a.json"
        convert("csv_to_json", src, out)
        self.assertEqual(
            json.loads(out.read_text(encoding="utf-8")),
            [{"name": "田中", "age": "18"}, {"name": "佐藤", "age": "17"}],
        )

    def test_japanese_is_not_escaped(self):
        src = self.write("a.csv", "name\n田中\n")
        out = self.tmp / "a.json"
        convert("csv_to_json", src, out)
        self.assertIn("田中", out.read_text(encoding="utf-8"))

    def test_bom(self):
        src = self.write("a.csv", "\ufeffname\n田中\n")
        out = self.tmp / "a.json"
        convert("csv_to_json", src, out)
        self.assertEqual(
            json.loads(out.read_text(encoding="utf-8")), [{"name": "田中"}]
        )

    def test_header_only_gives_empty_list(self):
        src = self.write("a.csv", "name,age\n")
        out = self.tmp / "a.json"
        convert("csv_to_json", src, out)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), [])

    def test_empty_file_gives_empty_list(self):
        src = self.write("a.csv", "")
        out = self.tmp / "a.json"
        convert("csv_to_json", src, out)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), [])

    def test_invalid_encoding_raises_value_error(self):
        src = self.write("a.csv", "name\n田中\n", encoding="shift_jis")
        with self.assertRaises(ValueError):
            convert("csv_to_json", src, self.tmp / "a.json")


class JsonToCsvTest(ConverterTestCase):
    def test_normal(self):
        src = self.write(
            "a.json", json.dumps([{"name": "田中", "age": 18}], ensure_ascii=False)
        )
        out = self.tmp / "a.csv"
        convert("json_to_csv", src, out)
        self.assertEqual(
            out.read_text(encoding="utf-8").splitlines(),
            ["name,age", "田中,18"],
        )

    def test_keys_differ_between_rows(self):
        src = self.write("a.json", json.dumps([{"a": 1}, {"a": 2, "b": 3}]))
        out = self.tmp / "a.csv"
        convert("json_to_csv", src, out)
        self.assertEqual(
            out.read_text(encoding="utf-8").splitlines(),
            ["a,b", "1,", "2,3"],
        )

    def test_null_and_nested_values(self):
        src = self.write("a.json", json.dumps([{"a": None, "b": {"x": 1}}]))
        out = self.tmp / "a.csv"
        convert("json_to_csv", src, out)
        lines = out.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "a,b")
        self.assertEqual(lines[1], ',"{""x"": 1}"')

    def test_commas_and_quotes_are_escaped(self):
        src = self.write("a.json", json.dumps([{"a": 'x,"y"'}]))
        out = self.tmp / "a.csv"
        convert("json_to_csv", src, out)
        self.assertEqual(
            out.read_text(encoding="utf-8").splitlines()[1], '"x,""y"""'
        )

    def test_top_level_not_list(self):
        src = self.write("a.json", json.dumps({"a": 1}))
        with self.assertRaises(ValueError):
            convert("json_to_csv", src, self.tmp / "a.csv")

    def test_items_not_objects(self):
        src = self.write("a.json", json.dumps([1, 2]))
        with self.assertRaises(ValueError):
            convert("json_to_csv", src, self.tmp / "a.csv")

    def test_invalid_json(self):
        src = self.write("a.json", "{not json")
        with self.assertRaises(ValueError):
            convert("json_to_csv", src, self.tmp / "a.csv")

    def test_empty_file(self):
        src = self.write("a.json", "")
        with self.assertRaises(ValueError):
            convert("json_to_csv", src, self.tmp / "a.csv")

    def test_empty_list_writes_empty_csv(self):
        src = self.write("a.json", "[]")
        out = self.tmp / "a.csv"
        convert("json_to_csv", src, out)
        self.assertTrue(out.is_file())


class CommonErrorsTest(ConverterTestCase):
    def test_missing_input(self):
        with self.assertRaises(FileNotFoundError):
            convert("csv_to_json", self.tmp / "none.csv", self.tmp / "o.json")

    def test_unknown_operation(self):
        src = self.write("a.csv", "a\n1\n")
        with self.assertRaises(ValueError):
            convert("nope", src, self.tmp / "o.json")

    def test_output_dir_is_a_file(self):
        src = self.write("a.csv", "a\n1\n")
        blocker = self.write("blocker", "x")
        with self.assertRaises(OSError):
            convert("csv_to_json", src, blocker / "o.json")


class CliTest(ConverterTestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "converter.main", *args],
            cwd=PYTHON_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_success_prints_json_and_exit_0(self):
        src = self.write("a.csv", "name\n田中\n")
        out = self.tmp / "a.json"
        result = self.run_cli("csv_to_json", str(src), str(out))
        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["success"])
        self.assertTrue(out.is_file())

    def test_failure_prints_json_and_exit_1(self):
        result = self.run_cli(
            "csv_to_json", str(self.tmp / "none.csv"), str(self.tmp / "o.json")
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["code"], "io_error")
        # 内部パスを含めない
        self.assertNotIn(str(self.tmp), payload["error"])

    def test_invalid_input_has_code_invalid_input(self):
        src = self.write("a.json", "{not json")
        result = self.run_cli("json_to_csv", str(src), str(self.tmp / "o.csv"))
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["code"], "invalid_input")

    def test_failure_does_not_leave_traceback(self):
        src = self.write("a.json", "{not json")
        result = self.run_cli("json_to_csv", str(src), str(self.tmp / "o.csv"))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
