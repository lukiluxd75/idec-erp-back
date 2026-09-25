from datetime import date

from . import queries
from .db import fetchall
from .staff import load_staff


class SqlReportRepository:
    def load_staff(self, district_id: int | None) -> list[dict]:
        return load_staff(district_id)

    def query(
        self,
        kind: str,
        start_date: date,
        end_date: date,
        unit_id: int,
        staff_ids: list[int],
        procedure_type_ids: list[int] | None,
    ) -> list[dict]:
        dated = {
            "ranking": queries.ranking_sql,
            "team_daily": queries.team_daily_sql,
            "staff_daily": queries.staff_daily_sql,
            "totals": queries.totals_sql,
            "by_type": queries.by_type_sql,
            "by_type_and_staff": queries.by_type_and_staff_sql,
            "procedures_in_period": queries.procedures_in_period_sql,
        }
        undated = {
            "pending": queries.pending_sql,
            "pending_procedures": queries.pending_procedures_sql,
        }
        if kind in dated:
            sql, params = dated[kind](start_date, end_date, unit_id, staff_ids, procedure_type_ids)
        elif kind in undated:
            sql, params = undated[kind](unit_id, staff_ids, procedure_type_ids)
        else:
            raise ValueError(f"Unsupported report query: {kind}")
        return fetchall(sql, params)
