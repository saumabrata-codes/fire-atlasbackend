from fastapi import APIRouter

from app.application.observations import get_observations

router = APIRouter()



@router.get("/sensors/comparison")
def sensor_comparison() -> dict:
    observations, sample_mode = get_observations()
    result = {}
    for sensor in ("MODIS", "VIIRS"):
        rows = [row for row in observations if row["sensor"] == sensor]
        frp = [row["frp"] for row in rows if row["frp"] is not None]
        confidence: dict[str, int] = {}
        for row in rows:
            label = str(row["confidence"] or "not provided")
            confidence[label] = confidence.get(label, 0) + 1
        result[sensor.lower()] = {
            "detections": len(rows), "mean_frp": round(sum(frp) / len(frp), 2) if frp else None,
            "max_frp": max(frp) if frp else None,
            "satellites": sorted({row["satellite"] for row in rows}),
            "products": sorted({row["product"] for row in rows}),
            "confidence_categories": confidence,
        }
    return {"sample_mode": sample_mode, "sensors": result,
            "method_note": "Sensor counts, FRP summaries, and confidence categories are reported separately; confidence scales are not assumed equivalent."}
