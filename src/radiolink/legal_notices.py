"""Attribution required by third-party terrain and map data providers.

These statements are kept in their original wording because the Copernicus
WorldDEM-30 licence prescribes the notices for adapted products. They must not
be replaced with a short generic "Copernicus" credit.
"""

COPERNICUS_LICENSE_URL = (
    "https://dataspace.copernicus.eu/explore-data/data-collections/"
    "copernicus-contributing-missions/collections-description/COP-DEM"
)

COPERNICUS_GLO30_DERIVED_CREDIT = (
    "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and "
    "© Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS "
    "by the European Union and ESA; all rights reserved"
)

COPERNICUS_GLO30_NO_LIABILITY = (
    "The organisations in charge of the Copernicus programme by law or "
    "by delegation do not incur any liability for any use of the "
    "Copernicus WorldDEM-30."
)

OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
OSM_HTML_ATTRIBUTION = (
    f'<a href="{OSM_COPYRIGHT_URL}" target="_blank" '
    'rel="noopener noreferrer">© OpenStreetMap contributors</a>'
)


def uses_copernicus_glo30(terrain_source: str | None) -> bool:
    """Only label user-provided terrain as Copernicus when its source says so."""
    return bool(terrain_source and "copernicus" in terrain_source.casefold())
