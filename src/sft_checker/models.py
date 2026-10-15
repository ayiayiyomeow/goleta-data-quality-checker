"""Serializable report models."""

from dataclasses import asdict, dataclass, field


@dataclass
class Issue:
    line_number: int
    issue_type: str
    description: str


@dataclass
class Report:
    total_lines: int = 0
    checked_lines: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    errors: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
