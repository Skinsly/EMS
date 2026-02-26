import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .models import IdempotencyRecord


def read_idempotency(db: Session, key: str) -> dict | None:
    row = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key))
    if not row:
        return None
    try:
        return json.loads(row.response_json)
    except json.JSONDecodeError:
        return None


def write_idempotency(db: Session, key: str, response: dict) -> None:
    row = IdempotencyRecord(idempotency_key=key, response_json=json.dumps(response, ensure_ascii=False))
    db.add(row)


def cleanup_expired_idempotency(db: Session) -> int:
    ttl = max(1, int(settings.idempotency_ttl_hours))
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=ttl)
    result = db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.created_at < cutoff))
    db.commit()
    return int(result.rowcount or 0)
