import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sft_checker import check_file


class CsvExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'data.csv'
        self.export = self.root / 'valid.jsonl'

    def write(self, text):
        self.source.write_text(text, encoding='utf-8')

    def exported(self):
        return [json.loads(line) for line in self.export.read_text().splitlines()]

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'sft_checker', str(self.source),
                               *map(str, args)], capture_output=True, text=True, cwd=self.root)

    def test_csv_strings_duplicates_missing_cells_and_extra_columns(self):
        self.write('instruction,input,output\na,001,true\na,001,true\nb,x\nc,x,y,z\nd,,\n')
        report = check_file(self.source, export_valid=self.export)
        self.assertEqual((report.total_lines, report.checked_lines, report.valid_records,
                          report.invalid_records), (5, 5, 2, 3))
        self.assertEqual([(e.line_number, e.issue_type) for e in report.errors],
                         [(3, 'duplicate_record'), (4, 'missing_field'), (5, 'invalid_format')])
        self.assertEqual(self.exported(), [dict(instruction='a', input='001', output='true'),
                                          dict(instruction='d', input='', output='')])

    def test_multiline_positions_bom_crlf_quotes_unicode(self):
        self.source.write_bytes('\ufeffinstruction,input,output\r\n"问,题","第一行\r\n第二行","答""案"\r\nx,y\r\n'
                                .encode('utf-8'))
        report = check_file(self.source, export_valid=self.export)
        self.assertEqual((report.total_lines, report.valid_records), (2, 1))
        self.assertEqual(report.errors[0].line_number, 4)
        self.assertEqual(self.exported()[0]['input'], '第一行\r\n第二行')
        self.assertEqual(self.exported()[0]['output'], '答"案')

    def test_missing_header_field(self):
        self.write('instruction,input\na,b\nc,d\n')
        report = check_file(self.source)
        self.assertEqual([(e.line_number, e.issue_type) for e in report.errors],
                         [(2, 'missing_field'), (3, 'missing_field')])

    def test_header_only_missing_field(self):
        self.write('instruction,input\n')
        report = check_file(self.source)
        self.assertEqual(report.invalid_records, 1)
        self.assertEqual(report.errors[0].line_number, 1)

    def test_duplicate_header(self):
        self.write('instruction,input,output,output\na,b,c,d\n')
        report = check_file(self.source, export_valid=self.export)
        self.assertEqual(report.errors[0].issue_type, 'invalid_format')
        self.assertEqual(self.exported(), [])

    def test_empty_and_header_only(self):
        for text in ('', 'instruction,input,output\n'):
            with self.subTest(text=text):
                self.write(text)
                report = check_file(self.source, export_valid=self.export)
                self.assertEqual(report.total_lines, 0)
                self.assertEqual(self.export.read_text(), '')

    def test_blank_row_and_malformed_quote(self):
        self.write('instruction,input,output\n\n"a"bad,b,c\nx,y,z\n')
        report = check_file(self.source)
        self.assertEqual((report.valid_records, report.invalid_records), (1, 2))
        self.assertEqual([e.line_number for e in report.errors], [2, 3])

    def test_unclosed_quote(self):
        self.write('instruction,input,output\n"broken\nremainder\n')
        report = check_file(self.source)
        self.assertEqual(report.total_lines, 1)
        self.assertEqual(report.errors[0].line_number, 2)

    def test_invalid_utf8_continues(self):
        self.source.write_bytes(b'instruction,input,output\na,\xff,c\nx,y,z\n')
        report = check_file(self.source)
        self.assertEqual((report.valid_records, report.invalid_records), (1, 1))
        self.assertEqual(report.errors[0].line_number, 2)

    def test_uppercase_extension_cli(self):
        self.source = self.root / 'data.CSV'
        self.write('instruction,input,output\na,b,c\n')
        result = self.cli('--export-valid', self.export)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.exported()), 1)
        self.assertEqual(json.loads((self.root / 'data.report.json').read_text())['valid_records'], 1)

    def test_jsonl_export_first_record_preserves_extra_fields(self):
        self.source = self.root / 'data.jsonl'
        first = dict(instruction='你好', input='', output='好\n呀', extra=1)
        duplicate = dict(first, extra=2)
        self.write('{}\n' + '\n'.join(json.dumps(r) for r in (first, duplicate)))
        result = self.cli('--export-valid', self.export)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.exported(), [first])
        self.assertEqual(check_file(self.export).valid_records, 1)

    def test_csv_export_preserves_extra_fields(self):
        self.write('output,extra,instruction,input\nb,first,a,\nb,second,a,\n')
        check_file(self.source, export_valid=self.export)
        self.assertEqual(self.exported(), [dict(output='b', extra='first', instruction='a', input='')])

    def test_unsupported_extension_preserves_existing_export(self):
        self.source = self.root / 'data.txt'
        self.write('anything')
        self.export.write_text('old')
        self.assertEqual(self.cli('--export-valid', self.export).returncode, 2)
        self.assertEqual(self.export.read_text(), 'old')
        self.assertFalse(list(self.root.glob('.*.tmp')))

    def test_export_path_collisions(self):
        self.write('instruction,input,output\na,b,c\n')
        original = self.source.read_bytes()
        for kind in ('same', 'symlink', 'hardlink', 'report'):
            with self.subTest(kind=kind):
                target = self.root / kind
                if kind == 'same':
                    target = self.source
                elif kind == 'symlink':
                    target.symlink_to(self.source)
                elif kind == 'hardlink':
                    target.hardlink_to(self.source)
                else:
                    target = self.root / 'data.report.json'
                self.assertEqual(self.cli('--export-valid', target).returncode, 2)
                self.assertEqual(self.source.read_bytes(), original)

    def test_api_collision(self):
        self.write('instruction,input,output\n')
        with self.assertRaises(ValueError):
            check_file(self.source, export_valid=self.source)

    def test_export_failure(self):
        self.write('instruction,input,output\na,b,c\n')
        self.assertEqual(self.cli('--export-valid', self.root / 'missing' / 'out.jsonl').returncode, 2)
        self.assertFalse((self.root / 'data.report.json').exists())

    def test_csv_sample(self):
        report = check_file(Path(__file__).resolve().parents[1] / 'sample_csv.csv', export_valid=self.export)
        self.assertEqual((report.total_lines, report.valid_records, report.invalid_records), (6, 3, 3))
        self.assertEqual(len(self.exported()), 3)


if __name__ == '__main__':
    unittest.main()
