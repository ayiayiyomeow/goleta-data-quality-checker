"""Shared schema validation, deduplication, and optional streaming export."""

import json
from contextlib import nullcontext
from pathlib import Path

from .models import Issue, Report
from .readers import FIELDS, read_records
from .reporting import atomic_text_writer, ensure_distinct_paths


def check_file(path: str | Path, *, export_valid: str | Path | None = None) -> Report:
    """Validate records; optionally export first valid occurrences as JSONL."""
    path = Path(path)
    destination = Path(export_valid) if export_valid is not None else None
    if destination is not None:
        ensure_distinct_paths(path, destination)
    report = Report()
    seen: dict[tuple[str, str, str], int] = {}
    context = atomic_text_writer(destination) if destination is not None else nullcontext(None)
    with context as output:
        for number, record, issues in read_records(path):
            report.total_lines += 1
            report.checked_lines += 1
            if not issues:
                if not isinstance(record, dict):
                    issues.append(Issue(number, "invalid_format", "每行必须是 JSON 对象"))
                else:
                    for name in FIELDS:
                        if name not in record:
                            issues.append(Issue(number, "missing_field", f"缺少必需字段：{name}"))
                        elif not isinstance(record[name], str):
                            issues.append(Issue(number, "invalid_type", f"字段 {name} 必须为字符串"))
                    if not issues:
                        key = tuple(record[name] for name in FIELDS)
                        if key in seen:
                            issues.append(Issue(number, "duplicate_record", f"三个字段的值与第 {seen[key]} 行完全相同"))
                        else:
                            seen[key] = number
            if issues:
                report.invalid_records += 1
                report.errors.extend(issues)
            else:
                report.valid_records += 1
                if output is not None:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
    return report
