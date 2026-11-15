from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
REPORT_ROOT = ROOT / "data" / "reports"


def _pdf_string(value: str) -> bytes:
    """Encode a printable PDF text string using the built-in WinAnsi font."""
    encoded = value.encode("cp1252", errors="replace")
    return b"<" + encoded.hex().upper().encode("ascii") + b"> Tj"


def _build_pdf_pages(lines: list[str]) -> bytes:
    wrapped: list[str] = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(line[index:index + 92] for index in range(0, len(line), 92))
    chunks = [wrapped[index:index + 46] for index in range(0, len(wrapped), 46)] or [["FireAtlas"]]
    objects: list[bytes] = []
    page_ids = [4 + index * 2 for index in range(len(chunks))]
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(chunks)} >>".encode("ascii"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for page_id, page_lines in zip(page_ids, chunks):
        stream_id = page_id + 1
        page = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {stream_id} 0 R >>")
        content = [b"BT", b"/F1 10 Tf", b"52 744 Td", b"14 TL"]
        for index, line in enumerate(page_lines):
            if index:
                content.append(b"T*")
            content.append(_pdf_string(line))
        content.append(b"ET")
        stream = b"\n".join(content)
        objects.append(page.encode("ascii"))
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return bytes(output)


def build_observation_report(observations: list[dict[str, Any]], sensor: str, sample_mode: bool) -> bytes:
    now = datetime.now(timezone.utc)
    dates = [str(row.get("acq_datetime", ""))[:10] for row in observations if row.get("acq_datetime")]
    products = sorted({str(row.get("product")) for row in observations if row.get("product")})
    lines = [
        "FIREATLAS - ACTIVE FIRE OBSERVATION REPORT",
        f"Generated (UTC): {now.isoformat(timespec='seconds')}",
        f"Data mode: {'Demonstration fixtures' if sample_mode else 'Persisted source observations'}",
        f"Sensor filter: {sensor}",
        f"Observations included: {len(observations)}",
        f"Acquisition dates: {min(dates) if dates else 'not available'} to {max(dates) if dates else 'not available'}",
        f"Source products: {', '.join(products) if products else 'not available'}",
        "",
        "SENSOR-SPECIFIC SUMMARY",
    ]
    for sensor_name in ("MODIS", "VIIRS"):
        rows = [row for row in observations if row.get("sensor") == sensor_name]
        if not rows:
            continue
        frp = [float(row["frp"]) for row in rows if row.get("frp") is not None]
        satellites = sorted({str(row.get("satellite")) for row in rows if row.get("satellite")})
        lines.append(f"{sensor_name}: {len(rows)} observations; satellites: {', '.join(satellites) or 'not provided'}")
        lines.append(f"  FRP (MW): mean {sum(frp) / len(frp):.2f}; max {max(frp):.2f}" if frp else "  FRP: not available")
        confidence: dict[str, int] = {}
        for row in rows:
            label = str(row.get("confidence") or "not provided")
            confidence[label] = confidence.get(label, 0) + 1
        lines.append("  Confidence labels (source scale preserved): " + ", ".join(f"{key}={value}" for key, value in sorted(confidence.items())))
    lines.extend([
        "",
        "METHOD AND LIMITATIONS",
        "Each record is a satellite hotspot observation, not a confirmed unique fire.",
        "MODIS and VIIRS observations and confidence labels are summarized separately.",
        "FRP values summarize observed records and do not measure burned area or damage.",
        "Missing observations are not interpreted as zero activity.",
        "This report makes no MODIS-to-VIIRS equivalence or universal conversion claim.",
        "",
        "PROVENANCE",
        "Source: NASA FIRMS active-fire products, or clearly labeled bundled fixtures in demonstration mode.",
        "Retain the accompanying source files and ingestion metadata for record-level audit.",
    ])
    return _build_pdf_pages(lines)


def archive_report(body: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(body).hexdigest()
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    safe_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_ROOT / f"fireatlas_observation_report_{safe_stamp}_{digest[:12]}.pdf"
    path.write_bytes(body)
    return {"path": str(path.relative_to(ROOT)), "sha256": digest, "file_size": len(body)}


def report_filename(sensor: str) -> str:
    normalized = re.sub(r"[^A-Z0-9_-]", "", sensor.upper()) or "ALL"
    return f"fireatlas-{normalized.lower()}-observation-report.pdf"
