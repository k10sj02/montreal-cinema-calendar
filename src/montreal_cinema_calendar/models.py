from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json

TZID = "America/Toronto"


@dataclass(frozen=True)
class Screening:
    source: str
    source_id: str
    title: str
    start: datetime
    venue: str
    address: str
    url: str
    description: str = ""
    runtime_minutes: int | None = None
    language: str = ""
    format: str = ""
    room: str = ""
    admission: str = ""
    status: str = "CONFIRMED"

    @property
    def uid(self) -> str:
        # Source IDs survive title, room and time corrections. If a source lacks an
        # ID, its adapter supplies a canonical URL/date based identity.
        raw = f"{self.source}|{self.source_id}".encode()
        return hashlib.sha256(raw).hexdigest()[:32] + "@montreal-cinema-calendar"

    @property
    def fingerprint(self) -> str:
        payload = asdict(self)
        payload["start"] = self.start.isoformat()
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Screening":
        data = dict(data)
        data["start"] = datetime.fromisoformat(data["start"])
        return cls(**data)

