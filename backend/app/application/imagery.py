from datetime import date
from urllib.parse import urlencode


IMAGERY_LAYERS = [
    {"sensor": "MODIS", "satellite": "Terra",
     "layer": "MODIS_Terra_CorrectedReflectance_TrueColor"},
    {"sensor": "MODIS", "satellite": "Aqua",
     "layer": "MODIS_Aqua_CorrectedReflectance_TrueColor"},
    {"sensor": "VIIRS", "satellite": "Suomi-NPP",
     "layer": "VIIRS_SNPP_CorrectedReflectance_TrueColor"},
    {"sensor": "VIIRS", "satellite": "NOAA-20",
     "layer": "VIIRS_NOAA20_CorrectedReflectance_TrueColor"},
    {"sensor": "VIIRS", "satellite": "NOAA-21",
     "layer": "VIIRS_NOAA21_CorrectedReflectance_TrueColor"},
]
LAYERS = [item["layer"] for item in IMAGERY_LAYERS]


def build_worldview_url(day: date, bounds: tuple[float, float, float, float]) -> str:
    return "https://worldview.earthdata.nasa.gov/?" + urlencode({
        "l": ",".join(LAYERS), "lg": "true",
        "t": f"{day.isoformat()}-T23:59:59Z",
        "v": ",".join(str(value) for value in bounds),
    })


def build_gibs_image_url(day: date, bounds: tuple[float, float, float, float],
                         layer: str, width: int = 1024, height: int = 768) -> str:
    """Build a direct NASA GIBS WMS GetMap URL for one layer and region/date."""
    if layer not in LAYERS:
        raise ValueError("Unsupported NASA GIBS layer")
    west, south, east, north = bounds
    params = {
        "SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.1.1",
        "LAYERS": layer, "STYLES": "", "SRS": "EPSG:4326",
        "BBOX": f"{west},{south},{east},{north}",
        "WIDTH": width, "HEIGHT": height, "FORMAT": "image/png",
        "TRANSPARENT": "TRUE", "TIME": day.isoformat(),
    }
    return "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?" + urlencode(params)


def build_region_imagery(day: date, bounds: tuple[float, float, float, float]) -> list[dict]:
    return [{**item, "image_url": build_gibs_image_url(day, bounds, item["layer"])}
            for item in IMAGERY_LAYERS]
