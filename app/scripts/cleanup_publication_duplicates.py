from __future__ import annotations

import argparse
from typing import Optional

from sqlalchemy import text

from app.db import SessionLocal


def delete_observation_duplicates(series_id: Optional[str] = None, dry_run: bool = True) -> int:
    """Delete duplicate rows sharing the same (series_id, observation_date).

    Keeps only the latest row by fetched_at within each (series_id, observation_date) group,
    regardless of vintage/publication versions. Returns the number of rows deleted. If dry_run=True,
    no deletions are performed; returns the number of rows that would be deleted.
    """
    where_series = ""
    params = {}
    if series_id:
        where_series = "AND series_id = :series_id"
        params["series_id"] = series_id

    # Use a window function to rank duplicates, keeping rn=1 (latest fetched_at)
    # Delete rows where rn > 1
    dedupe_cte = f"""
        WITH ranked AS (
            SELECT
                vintage_id,
                row_number() OVER (
                    PARTITION BY series_id, observation_date
                    ORDER BY fetched_at DESC, vintage_id DESC
                ) AS rn
            FROM series_vintages
            WHERE 1=1
            {where_series}
        )
    """

    with SessionLocal() as s:
        if dry_run:
            q = text(dedupe_cte + "SELECT count(*) AS to_delete FROM ranked WHERE rn > 1")
            res = s.execute(q, params).scalar_one()
            return int(res)
        else:
            q = text(
                dedupe_cte
                + "DELETE FROM series_vintages sv USING ranked r WHERE sv.vintage_id = r.vintage_id AND r.rn > 1 RETURNING sv.vintage_id"
            )
            res = s.execute(q, params).fetchall()
            s.commit()
            return len(res)


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete duplicate series_vintages rows by observation_date (keep latest fetched_at)")
    parser.add_argument("--series", dest="series_id", help="Limit to a specific series_id", default=None)
    parser.add_argument("--execute", dest="execute", action="store_true", help="Perform deletions (not a dry run)")
    args = parser.parse_args()

    num = delete_observation_duplicates(series_id=args.series_id, dry_run=not args.execute)
    if args.execute:
        print(f"Deleted {num} duplicate rows")
    else:
        print(f"Would delete {num} duplicate rows (dry run). Use --execute to apply.")


if __name__ == "__main__":
    main()


