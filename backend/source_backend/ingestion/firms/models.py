
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Any, Mapping
import math
import ast


class ObservationValidationError(ValueError):
    """Raised when a fire observation contains invalid data."""


@dataclass
class FireObservation:
    """Standardized MODIS and VIIRS fire observation."""

    latitude: float
    longitude: float

    acquisition_date: date
    acquisition_time: Optional[str]

    satellite: str
    instrument: str
    source_dataset: str

    # MODIS brightness fields
    brightness: Optional[float] = None
    bright_t31: Optional[float] = None

    # VIIRS brightness fields
    bright_ti4: Optional[float] = None
    bright_ti5: Optional[float] = None

    # Common fields
    scan: Optional[float] = None
    track: Optional[float] = None
    confidence: Optional[str] = None
    frp: Optional[float] = None
    daynight: Optional[str] = None
    version: Optional[str] = None

    raw_properties: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self):
        if (
            not isinstance(self.acquisition_date, date)
            or isinstance(self.acquisition_date, datetime)
        ):
            raise ObservationValidationError(
                "acquisition_date must be a date object."
            )

        try:
            latitude = float(self.latitude)
            longitude = float(self.longitude)
        except (TypeError, ValueError):
            raise ObservationValidationError(
                "Latitude and longitude must be numeric."
            )

        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ObservationValidationError(
                "Latitude must be between -90 and 90."
            )

        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ObservationValidationError(
                "Longitude must be between -180 and 180."
            )

        self.latitude = latitude
        self.longitude = longitude

        if self.frp is not None:
            try:
                self.frp = float(self.frp)
            except (TypeError, ValueError):
                raise ObservationValidationError(
                    "FRP must be numeric."
                )

            if not math.isfinite(self.frp) or self.frp < 0:
                raise ObservationValidationError(
                    "FRP must be a finite, non-negative value."
                )

        if not self.source_dataset:
            raise ObservationValidationError(
                "source_dataset is required."
            )

        if not self.satellite:
            raise ObservationValidationError(
                "satellite is required."
            )

        if not self.instrument:
            raise ObservationValidationError(
                "instrument is required."
            )

        if not isinstance(self.raw_properties, dict):
            raise ObservationValidationError(
                "raw_properties must be a dictionary."
            )

    @staticmethod
    def _optional_float(
        value: Any,
        field_name: str
    ) -> Optional[float]:

        if value is None or str(value).strip() == "":
            return None

        try:
            result = float(value)

            if not math.isfinite(result):
                raise ValueError

            return result

        except (ValueError, TypeError):
            raise ObservationValidationError(
                f"Invalid numeric value for {field_name}: {value}"
            )

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:

        if value is None:
            return None

        result = str(value).strip()

        return result if result else None

    @staticmethod
    def _parse_raw_properties(value: Any) -> dict[str, Any]:
        """Safely convert serialized raw properties into a dictionary."""

        if value is None or value == "":
            return {}

        if isinstance(value, dict):
            return value.copy()

        if not isinstance(value, str):
            raise ObservationValidationError(
                "raw_properties must be a dictionary or serialized dictionary."
            )

        try:
            result = ast.literal_eval(value)

            if not isinstance(result, dict):
                raise ValueError(
                    "raw_properties must contain a dictionary."
                )

            return result

        except (ValueError, SyntaxError, TypeError) as error:
            raise ObservationValidationError(
                f"Invalid raw_properties: {error}"
            ) from error

    @classmethod
    def from_firms_row(
        cls,
        row: Mapping[str, Any],
        source_dataset: str
    ) -> "FireObservation":
        """Create an observation from a raw NASA FIRMS CSV row."""

        try:
            latitude = cls._optional_float(
                row.get("latitude"),
                "latitude"
            )

            longitude = cls._optional_float(
                row.get("longitude"),
                "longitude"
            )

            if latitude is None or longitude is None:
                raise ObservationValidationError(
                    "Latitude and longitude are required."
                )

            acquisition_date = date.fromisoformat(
                str(row["acq_date"]).strip()
            )

            return cls(
                latitude=latitude,
                longitude=longitude,
                acquisition_date=acquisition_date,

                acquisition_time=cls._optional_string(
                    row.get("acq_time")
                ),

                satellite=cls._optional_string(
                    row.get("satellite")
                ) or "UNKNOWN",

                instrument=cls._optional_string(
                    row.get("instrument")
                ) or "UNKNOWN",

                source_dataset=source_dataset,

                brightness=cls._optional_float(
                    row.get("brightness"),
                    "brightness"
                ),

                bright_t31=cls._optional_float(
                    row.get("bright_t31"),
                    "bright_t31"
                ),

                bright_ti4=cls._optional_float(
                    row.get("bright_ti4"),
                    "bright_ti4"
                ),

                bright_ti5=cls._optional_float(
                    row.get("bright_ti5"),
                    "bright_ti5"
                ),

                scan=cls._optional_float(
                    row.get("scan"),
                    "scan"
                ),

                track=cls._optional_float(
                    row.get("track"),
                    "track"
                ),

                confidence=cls._optional_string(
                    row.get("confidence")
                ),

                frp=cls._optional_float(
                    row.get("frp"),
                    "frp"
                ),

                daynight=cls._optional_string(
                    row.get("daynight")
                ),

                version=cls._optional_string(
                    row.get("version")
                ),

                raw_properties=dict(row)
            )

        except ObservationValidationError:
            raise

        except (ValueError, TypeError, KeyError) as error:
            raise ObservationValidationError(
                f"Could not convert FIRMS observation: {error}"
            ) from error

    @classmethod
    def from_processed_row(
        cls,
        row: Mapping[str, Any],
    ) -> "FireObservation":
        """Create an observation from the team's normalized CSV schema."""

        try:
            latitude = cls._optional_float(
                row.get("latitude"),
                "latitude"
            )

            longitude = cls._optional_float(
                row.get("longitude"),
                "longitude"
            )

            if latitude is None or longitude is None:
                raise ObservationValidationError(
                    "Latitude and longitude are required."
                )

            source_dataset = cls._optional_string(
                row.get("source_dataset")
            )

            if not source_dataset:
                raise ObservationValidationError(
                    "source_dataset is required."
                )

            return cls(
                latitude=latitude,
                longitude=longitude,

                acquisition_date=date.fromisoformat(
                    str(row["acquisition_date"]).strip()
                ),

                acquisition_time=cls._optional_string(
                    row.get("acquisition_time")
                ),

                satellite=cls._optional_string(
                    row.get("satellite")
                ) or "UNKNOWN",

                instrument=cls._optional_string(
                    row.get("instrument")
                ) or "UNKNOWN",

                source_dataset=source_dataset,

                brightness=cls._optional_float(
                    row.get("brightness"),
                    "brightness"
                ),

                bright_t31=cls._optional_float(
                    row.get("bright_t31"),
                    "bright_t31"
                ),

                bright_ti4=cls._optional_float(
                    row.get("bright_ti4"),
                    "bright_ti4"
                ),

                bright_ti5=cls._optional_float(
                    row.get("bright_ti5"),
                    "bright_ti5"
                ),

                scan=cls._optional_float(
                    row.get("scan"),
                    "scan"
                ),

                track=cls._optional_float(
                    row.get("track"),
                    "track"
                ),

                confidence=cls._optional_string(
                    row.get("confidence")
                ),

                frp=cls._optional_float(
                    row.get("frp"),
                    "frp"
                ),

                daynight=cls._optional_string(
                    row.get("daynight")
                ),

                version=cls._optional_string(
                    row.get("version")
                ),

                raw_properties=cls._parse_raw_properties(
                    row.get("raw_properties")
                )
            )

        except ObservationValidationError:
            raise

        except (ValueError, TypeError, KeyError) as error:
            raise ObservationValidationError(
                f"Could not convert processed observation: {error}"
            ) from error

    def to_dict(self) -> dict[str, Any]:
        """Convert observation into a serializable dictionary."""

        return {
            "latitude": self.latitude,
            "longitude": self.longitude,

            "acquisition_date": (
                self.acquisition_date.isoformat()
            ),

            "acquisition_time": self.acquisition_time,

            "satellite": self.satellite,
            "instrument": self.instrument,
            "source_dataset": self.source_dataset,

            "brightness": self.brightness,
            "bright_t31": self.bright_t31,
            "bright_ti4": self.bright_ti4,
            "bright_ti5": self.bright_ti5,

            "scan": self.scan,
            "track": self.track,

            "confidence": self.confidence,
            "frp": self.frp,
            "daynight": self.daynight,
            "version": self.version,

            "raw_properties": self.raw_properties
        }
