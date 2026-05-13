from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from .accounts import Account
from .errors import ClipError, Error
from .models import Offer


@dataclass
class ClipReport:
    account: Account
    clipped: list[Offer]
    clip_errors: list[ClipError] = field(default_factory=list)
    error: Optional[Error] = None
    highlight_keywords: list[str] = field(default_factory=list)

    @property
    def expiring_soon(self) -> list[Offer]:
        cutoff = datetime.now(timezone.utc) + timedelta(days=7)
        return [
            o
            for o in self.clipped
            if o.end_date is not None and o.end_date <= cutoff
        ]
