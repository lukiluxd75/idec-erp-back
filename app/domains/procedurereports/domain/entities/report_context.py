from dataclasses import dataclass


@dataclass(frozen=True)
class ReportContext:
    unit_id: int
    unit_name: str
    server: str
    database: str
