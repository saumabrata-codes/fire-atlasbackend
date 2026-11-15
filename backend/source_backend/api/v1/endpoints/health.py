
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check():
    """
    Check whether the FIRE ATLAS API v1 is responding.
    """
    return {
        "status": "healthy",
        "message": "FIRE ATLAS API v1 is running."
    }
