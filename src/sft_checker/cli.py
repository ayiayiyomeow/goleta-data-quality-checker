"""Command-line entry point."""

import argparse
from pathlib import Path
import sys

from .checker import check_file
from .reporting import ensure_distinct_paths, save_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 SFT JSONL/CSV 数据集并生成 JSON 报告")
    parser.add_argument("input_file", type=Path, help="UTF-8 数据集路径，按 .jsonl/.csv 扩展名自动识别")
    parser.add_argument("-o", "--output", type=Path, help="报告路径（默认：输入目录/<文件名>.report.json）")
    parser.add_argument("--export-valid", type=Path, help="将有效且去重后的数据导出为 JSONL")
    args = parser.parse_args(argv)
    source = args.input_file
    destination = args.output or source.with_name(f"{source.stem}.report.json")
    try:
        paths = [source, destination]
        if args.export_valid is not None:
            paths.append(args.export_valid)
        ensure_distinct_paths(*paths)
        report = check_file(source, export_valid=args.export_valid)
        save_report(report, destination)
    except (OSError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(f"检查完成：总行数={report.total_lines}，已检查={report.checked_lines}，"
          f"有效={report.valid_records}，无效={report.invalid_records}")
    print(f"报告：{destination}")
    if args.export_valid is not None:
        print(f"有效数据：{args.export_valid}")
    return 1 if report.invalid_records else 0
