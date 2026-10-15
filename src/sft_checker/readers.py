"""Format-specific readers yielding (physical start line, value, issues)."""

import csv
import json
from pathlib import Path

from .models import Issue

FIELDS = ("instruction", "input", "output")


def _reject_constant(value: str):
    raise ValueError(f"JSON 不允许常量 {value}")


def _unique_keys(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 对象含重复键：{key}")
        result[key] = value
    return result


def read_jsonl(path: Path):
    with path.open("rb") as source:
        for number, raw in enumerate(source, 1):
            try:
                line = raw.decode("utf-8-sig" if number == 1 else "utf-8")
                record = json.loads(line, parse_constant=_reject_constant,
                                    object_pairs_hook=_unique_keys)
            except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                yield number, None, [Issue(number, "invalid_format", f"无法解析 UTF-8 JSON：{exc}")]
            else:
                yield number, record, []


def read_csv(path: Path):
    # surrogateescape lets one damaged record be reported without losing later rows.
    with path.open("r", encoding="utf-8-sig", errors="surrogateescape", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = None
        header_problems = []
        had_rows = False
        while True:
            number = reader.line_num + 1
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as exc:
                had_rows = True
                yield number, None, [Issue(number, "invalid_format", f"CSV 解析失败：{exc}")]
                if header is None:
                    # A broken header cannot provide a reliable column mapping.
                    header = []
                    header_problems = [("invalid_format", "CSV 表头无法解析")]
                continue
            encoding_error = any(any(0xDC80 <= ord(c) <= 0xDCFF for c in cell) for cell in row)
            if header is None:
                header = row
                if encoding_error or not row or len(set(row)) != len(row):
                    header_problems.append(("invalid_format", "CSV 表头为空、包含重复列名或无效 UTF-8"))
                for name in FIELDS:
                    if name not in header:
                        header_problems.append(("missing_field", f"CSV 表头缺少必需字段：{name}"))
                continue
            had_rows = True
            issues = [Issue(number, kind, message) for kind, message in header_problems]
            if encoding_error:
                issues.append(Issue(number, "invalid_format", "CSV 记录含无效 UTF-8"))
            if not row or len(row) > len(header):
                issues.append(Issue(number, "invalid_format", "CSV 空行或列数超过表头列数"))
            # zip omits absent cells so common validation reports missing fields.
            record = dict(zip(header, row))
            yield number, record, issues
        if not had_rows and header_problems:
            yield 1, None, [Issue(1, kind, message) for kind, message in header_problems]


def read_records(path: Path):
    readers = {".jsonl": read_jsonl, ".csv": read_csv}
    try:
        reader = readers[path.suffix.lower()]
    except KeyError:
        raise ValueError("不支持的文件扩展名，请使用 .jsonl 或 .csv") from None
    yield from reader(path)
