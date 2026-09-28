from datetime import date
from typing import Protocol


class ReportRepository(Protocol):
    def load_staff(self, district_id: int | None) -> list[dict]: ...

    def query(
        self,
        kind: str,
        start_date: date,
        end_date: date,
        unit_id: int,
        staff_ids: list[int],
        procedure_type_ids: list[int] | None,
    ) -> list[dict]: ...
