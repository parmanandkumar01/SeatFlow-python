"""PNR records repository."""

from __future__ import annotations

from typing import Any, Optional

from bingo_linux.database.database import Database
from bingo_linux.repositories.base_repository import BaseRepository


class PnrRepository(BaseRepository):
    """Repository for the pnr_records table."""

    table_name = "pnr_records"
    columns = [
        "id", "pnr_number", "train_number", "journey_date",
        "passenger_names", "booking_status", "fare_amount",
        "looked_up_at", "created_at", "updated_at",
    ]

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def get_by_pnr(self, pnr_number: str) -> Optional[dict[str, Any]]:
        """Return a PNR record by PNR number.

        Args:
            pnr_number: The PNR number.

        Returns:
            PNR record dictionary, or None.
        """
        conn = self.db.connect()
        row = conn.execute(
            "SELECT * FROM pnr_records WHERE pnr_number = ?",
            (pnr_number,),
        ).fetchone()
        return dict(row) if row else None

    def exists(self, pnr_number: str) -> bool:
        """Return True if a PNR record exists for the given number."""
        return self.get_by_pnr(pnr_number) is not None
