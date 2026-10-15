"""Shared atomic output and path collision protection."""

from contextlib import contextmanager
from itertools import combinations
import json
import os
from pathlib import Path
import tempfile

from .models import Report


def ensure_distinct_paths(*paths: Path) -> None:
    for first, second in combinations(paths, 2):
        if first.resolve() == second.resolve() or (
            first.exists() and second.exists() and first.samefile(second)
        ):
            raise ValueError("输入文件、报告和有效数据导出路径不能相同（包括链接）")


@contextmanager
def atomic_text_writer(destination: Path):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as output:
            temporary = Path(output.name)
            yield output
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_report(report: Report, destination: Path) -> None:
    with atomic_text_writer(destination) as output:
        json.dump(report.to_dict(), output, ensure_ascii=False, indent=2)
        output.write("\n")
