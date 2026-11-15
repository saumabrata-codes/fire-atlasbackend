from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.core.config import get_settings
from source_backend.main import app as source_app

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-FireAtlas-Report-Id", "X-FireAtlas-Report-Tracked", "X-FireAtlas-Report-Sample-Mode"],
)
app.include_router(router, prefix=settings.api_v1_prefix)
app.mount("/source", source_app)


@app.get("/health")
def root_health() -> dict[str, str]:
    return {"status": "ok", "service": "fireatlas-api"}
