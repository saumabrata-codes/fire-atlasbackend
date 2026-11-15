
from fastapi import APIRouter
from fastapi.responses import Response

from source_backend.api.v1.schemas.filters import DataFilter
from source_backend.application.report_service import build_csv_report

router = APIRouter()


@router.post("/report", tags=["Reports"])
async def download_report(filters: DataFilter):
    csv_content, metadata = build_csv_report(filters)

    filename = (
        f"fire_atlas_{filters.start_date}_"
        f"{filters.end_date}.csv"
    )

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Report-Provider": str(metadata["provider"]),
        "X-Report-Data-Status": str(metadata["data_status"]),
        "X-Report-Records": str(metadata["records_returned"]),
        "X-Report-Synthetic": str(metadata["is_synthetic"]),
        "X-Report-Start-Date": filters.start_date.isoformat(),
        "X-Report-End-Date": filters.end_date.isoformat(),
        "X-Report-Datasets": ",".join(metadata.get("source_datasets", [])),
    }

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )
