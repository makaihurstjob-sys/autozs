from datetime import date

from pydantic import BaseModel


class ZFinanceSyncRequest(BaseModel):
    startDate: date | None = None
    endDate: date | None = None
    resetCursor: bool = False
