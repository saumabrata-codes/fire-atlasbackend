from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RAW_ROOT = Path(os.environ.get("FIREATLAS_DATA_DIR", str(ROOT / "data"))) / "raw"


def preserve_source(sensor: str, product: str, body: str, record_count: int,
                    source_start=None, source_end=None) -> dict:
    now = datetime.now(timezone.utc)
    folder = RAW_ROOT / sensor.lower() / product.lower() / now.strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    payload = body.encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    stem = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{digest[:12]}"
    csv_path = folder / f"{stem}.csv"
    manifest_path = folder / f"{stem}.manifest.json"
    # Binary writes prevent Windows text-mode newline translation from changing
    # the archived payload after its checksum has been calculated.
    csv_path.write_bytes(payload)
    manifest = {
        "sensor": sensor, "product": product, "file": csv_path.name,
        "sha256": digest, "file_size": len(payload),
        "record_count": record_count, "downloaded_at": now.isoformat(),
        "source": "NASA FIRMS Area API",
    }
    if source_start is not None:
        manifest["source_date_start"] = source_start.isoformat()
    if source_end is not None:
        manifest["source_date_end"] = source_end.isoformat()
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {**manifest, "path": str(csv_path.relative_to(ROOT))}
