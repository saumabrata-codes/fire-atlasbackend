
from fastapi import Depends

from source_backend.api.v1.schemas.filters import DataFilter


def get_validated_data_filter(
    filters: DataFilter = Depends(),
) -> DataFilter:
    """
    Provide a validated FIRE ATLAS data filter
    to API endpoints.
    """
    return filters
