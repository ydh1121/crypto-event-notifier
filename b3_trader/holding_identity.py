"""Stable identity/revision for the existing manual holding, without DB writes."""
import hashlib
import json


def holding_revision(row):
    values = [row[k] for k in ('market', 'exchange', 'volume', 'avg_price', 'updated_ts')]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
