import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sft_checker import check_file


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "data.jsonl"

    def write(self, content):
        self.source.write_text(content, encoding="utf-8")
        return check_file(self.source)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "sft_checker", *map(str, args)],
            capture_output=True, text=True, cwd=self.root,
        )

    def test_sample(self):
        report = check_file(Path(__file__).resolve().parents[1] / "sample.jsonl")
        self.assertEqual((report.total_lines, report.checked_lines,
                          report.valid_records, report.invalid_records), (10, 10, 3, 7))
        self.assertEqual([issue.line_number for issue in report.errors], [3, 4, 5, 6, 7, 8, 10, 10])
        self.assertEqual({issue.issue_type for issue in report.errors},
                         {"missing_field", "invalid_format", "duplicate_record", "invalid_type"})

    def test_empty_file(self):
        self.assertEqual(self.write("").to_dict(), dict(
            total_lines=0, checked_lines=0, valid_records=0, invalid_records=0, errors=[]))

    def test_exact_duplicates_ignore_extra_fields_and_key_order(self):
        report = self.write('\n'.join([
            '{"instruction":"a","input":"","output":"b"}',
            '{"output":"b","input":"","instruction":"a","extra":1}',
            '{"instruction":"a ","input":"","output":"b"}',
            '{"instruction":"a","input":"","output":"b"}',
        ]))
        self.assertEqual((report.valid_records, report.invalid_records), (2, 2))
        self.assertTrue(all("第 1 行" in issue.description for issue in report.errors))

    def test_multiple_errors_count_once(self):
        report = self.write('{"input":null}\n')
        self.assertEqual(report.invalid_records, 1)
        self.assertEqual(len(report.errors), 3)

    def test_strict_json(self):
        report = self.write('\n'.join([
            'null', '123', '"string"', '[]', '{',
            '{"instruction":"a","input":"","output":"b","extra":NaN}',
            '{"instruction":"a","input":"","output":"b","output":"c"}',
        ]))
        self.assertEqual(report.invalid_records, 7)
        self.assertTrue(all(issue.issue_type == "invalid_format" for issue in report.errors))

    def test_bom_crlf_unicode_and_no_final_newline(self):
        self.source.write_bytes('\ufeff{"instruction":"中文","input":"","output":"好"}\r\n{}'
                                .encode("utf-8"))
        report = check_file(self.source)
        self.assertEqual((report.total_lines, report.valid_records, report.invalid_records), (2, 1, 1))

    def test_invalid_encoding_continues(self):
        self.source.write_bytes(b'\xff\n{"instruction":"a","input":"","output":"b"}\n')
        report = check_file(self.source)
        self.assertEqual((report.total_lines, report.valid_records, report.invalid_records), (2, 1, 1))

    def test_all_field_types_rejected(self):
        for value in (None, 1, True, [], {}):
            with self.subTest(value=value):
                report = self.write(json.dumps(dict(instruction="a", input=value, output="b")))
                self.assertEqual(report.errors[0].issue_type, "invalid_type")

    def test_cli_success_default_report(self):
        self.write('{"instruction":"a","input":"","output":"b"}\n')
        result = self.cli(self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.root / "data.report.json").read_text())
        self.assertEqual(data["valid_records"], 1)

    def test_cli_invalid_and_custom_report(self):
        self.write('{}\n')
        target = self.root / "report.json"
        result = self.cli(self.source, "-o", target)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(json.loads(target.read_text())["invalid_records"], 1)

    def test_cli_missing_source(self):
        result = self.cli(self.source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("错误", result.stderr)
        self.assertFalse((self.root / "data.report.json").exists())

    def test_cli_rejects_overwriting_input(self):
        self.write('{}\n')
        result = self.cli(self.source, "-o", self.source)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.source.read_text(), '{}\n')

    def test_cli_rejects_input_hardlink(self):
        self.write('{}\n')
        target = self.root / "alias.json"
        target.hardlink_to(self.source)
        self.assertEqual(self.cli(self.source, "-o", target).returncode, 2)
        self.assertEqual(self.source.read_text(), '{}\n')

    def test_cli_output_failure(self):
        self.write('{}\n')
        result = self.cli(self.source, "-o", self.root / "missing" / "report.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("错误", result.stderr)

    def test_cli_help(self):
        self.assertEqual(self.cli("--help").returncode, 0)


if __name__ == "__main__":
    unittest.main()
