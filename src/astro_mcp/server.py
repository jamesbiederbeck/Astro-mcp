"""Astro-MCP server: FastMCP service for celestial body positions and moon phases.

Tools:
    phases    – Returns the phase of one or more celestial bodies.
    positions – Returns the position of one or more celestial bodies.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import Field
from skyfield import almanac
from skyfield.api import Loader, load_file, wgs84
from skyfield.framelib import ecliptic_J2000_frame

# ---------------------------------------------------------------------------
# Ephemeris setup
# ---------------------------------------------------------------------------

_loader = Loader("~/.skyfield")
_ts = _loader.timescale()

# The ephemeris is loaded lazily so the server starts without network access.
_eph: object | None = None


def _get_eph():
    global _eph
    if _eph is None:
        _eph = _loader("de421.bsp")
    return _eph


# ---------------------------------------------------------------------------
# Body name normalisation
# ---------------------------------------------------------------------------

# Map common lowercase body names to the keys used in de421.bsp / Skyfield.
_BODY_ALIASES: dict[str, str] = {
    "sun": "sun",
    "mercury": "mercury",
    "venus": "venus",
    "earth": "earth",
    "moon": "moon",
    "mars": "mars barycenter",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
    "pluto": "pluto barycenter",
    # accept barycenter spellings as well
    "mercury barycenter": "mercury barycenter",
    "venus barycenter": "venus barycenter",
    "mars barycenter": "mars barycenter",
    "jupiter barycenter": "jupiter barycenter",
    "saturn barycenter": "saturn barycenter",
    "uranus barycenter": "uranus barycenter",
    "neptune barycenter": "neptune barycenter",
    "pluto barycenter": "pluto barycenter",
}


def _resolve_body(name: str):
    """Return the Skyfield body object for a given common name."""
    eph = _get_eph()
    key = _BODY_ALIASES.get(name.lower())
    if key is None:
        raise ValueError(
            f"Unknown body '{name}'. Supported bodies: "
            + ", ".join(sorted({k for k in _BODY_ALIASES if "barycenter" not in k}))
        )
    return eph[key]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _parse_time(dt_str: str | None):
    """Parse an ISO 8601 datetime string or return the current time."""
    if dt_str is None:
        return _ts.now()
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _ts.from_datetime(dt)


# ---------------------------------------------------------------------------
# Moon phase helpers
# ---------------------------------------------------------------------------

_PHASE_NAMES = [
    "New Moon",
    "Waxing Crescent",
    "First Quarter",
    "Waxing Gibbous",
    "Full Moon",
    "Waning Gibbous",
    "Last Quarter",
    "Waning Crescent",
]


def _moon_phase_name(angle_deg: float) -> str:
    """Map a moon phase angle (0–360°) to a natural-language phase name.

    The phase angle returned by ``almanac.moon_phase()`` is the difference
    between the Moon's and the Sun's ecliptic longitude:
        0°   → New Moon
        180° → Full Moon
    """
    # 8 equal sectors of 45° each, centred on the canonical angles
    # (0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°).
    sector = int((angle_deg + 22.5) % 360 // 45)
    return _PHASE_NAMES[sector]


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="astro-mcp",
    instructions=(
        "Provides celestial mechanics tools powered by Skyfield and the "
        "JPL DE421 planetary ephemeris.  Use 'phases' to query moon/planet "
        "phases and 'positions' to get body coordinates in various frames."
    ),
)


# ---------------------------------------------------------------------------
# Tool: phases
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "Return the current phase of one or more celestial bodies.  "
        "For the Moon the phase angle tracks the full 0–360° lunation cycle "
        "(0° = New Moon, 180° = Full Moon).  For other bodies the phase angle "
        "is the Sun–Body–Observer angle and the illuminated fraction is also "
        "included.  'natural' format returns named phases for the Moon and a "
        "percentage illuminated description for planets."
    )
)
def phases(
    bodies: Annotated[
        list[str],
        Field(
            description=(
                "List of body names to query, e.g. ['moon', 'venus', 'mars']. "
                "Supported: sun, mercury, venus, earth, moon, mars, jupiter, "
                "saturn, uranus, neptune, pluto."
            )
        ),
    ],
    format: Annotated[
        Literal["radians", "degrees", "natural"],
        Field(
            default="degrees",
            description=(
                "Output format for the phase value.  "
                "'radians' and 'degrees' return the raw phase angle.  "
                "'natural' returns a human-readable description "
                "(e.g. 'Full Moon', 'Waxing Gibbous', '97.5% illuminated')."
            ),
        ),
    ] = "degrees",
    datetime: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "ISO 8601 datetime string (e.g. '2025-01-15T20:00:00Z').  "
                "Defaults to the current UTC time."
            ),
        ),
    ] = None,
) -> dict:
    """Return the phase of each requested body at the given time."""
    eph = _get_eph()
    t = _parse_time(datetime)
    results = []

    for name in bodies:
        name_lower = name.lower()

        if name_lower == "moon":
            # Moon phase: 0–360° lunation angle
            angle = almanac.moon_phase(eph, t)
            if format == "radians":
                phase_value = round(angle.radians, 6)
            elif format == "degrees":
                phase_value = round(angle.degrees, 4)
            else:
                phase_value = _moon_phase_name(angle.degrees)

            results.append({"name": "moon", "phase": phase_value})

        else:
            # Planets and other bodies: phase angle (Sun–Body–Earth)
            body = _resolve_body(name)
            earth = eph["earth"]
            sun = eph["sun"]

            pos = earth.at(t).observe(body)
            pa = pos.phase_angle(sun)
            fi = pos.fraction_illuminated(sun)

            if format == "radians":
                phase_value = round(pa.radians, 6)
            elif format == "degrees":
                phase_value = round(pa.degrees, 4)
            else:
                pct = round(fi * 100, 1)
                phase_value = f"{pct}% illuminated"

            results.append(
                {
                    "name": name,
                    "phase": phase_value,
                    "fraction_illuminated": round(fi, 6),
                }
            )

    return {"bodies": results}


# ---------------------------------------------------------------------------
# Tool: positions
# ---------------------------------------------------------------------------

CoordinateSystem = Literal[
    "altaz_topocentric",
    "radec_apparent",
    "heliocentric_ecliptic_xyz",
    "barycentric_xyz",
]


@mcp.tool(
    description=(
        "Return the position of one or more celestial bodies in a chosen "
        "coordinate frame.  Four frames are supported:\n"
        "  • altaz_topocentric (default) – altitude/azimuth as seen from a "
        "point on Earth's surface; requires latitude and longitude.\n"
        "  • radec_apparent – apparent geocentric right ascension & "
        "declination (J2000 epoch).\n"
        "  • heliocentric_ecliptic_xyz – X/Y/Z in AU in the J2000 ecliptic "
        "frame centred on the Sun.\n"
        "  • barycentric_xyz – X/Y/Z in AU in the ICRF centred on the Solar "
        "System Barycentre."
    )
)
def positions(
    bodies: Annotated[
        list[str],
        Field(
            description=(
                "List of body names to query, e.g. ['moon', 'mars', 'jupiter']. "
                "Supported: sun, mercury, venus, earth, moon, mars, jupiter, "
                "saturn, uranus, neptune, pluto."
            )
        ),
    ],
    datetime: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "ISO 8601 datetime string (e.g. '2025-06-21T12:00:00Z').  "
                "Defaults to the current UTC time."
            ),
        ),
    ] = None,
    coordinate_system: Annotated[
        CoordinateSystem,
        Field(
            default="altaz_topocentric",
            description=(
                "Coordinate frame for the output positions.  "
                "One of: altaz_topocentric, radec_apparent, "
                "heliocentric_ecliptic_xyz, barycentric_xyz."
            ),
        ),
    ] = "altaz_topocentric",
    latitude: Annotated[
        float | None,
        Field(
            default=None,
            description=(
                "Observer geodetic latitude in decimal degrees (−90 to +90).  "
                "Required for altaz_topocentric."
            ),
        ),
    ] = None,
    longitude: Annotated[
        float | None,
        Field(
            default=None,
            description=(
                "Observer geodetic longitude in decimal degrees (−180 to +180).  "
                "Required for altaz_topocentric."
            ),
        ),
    ] = None,
    elevation_m: Annotated[
        float,
        Field(
            default=0.0,
            description="Observer elevation above sea level in metres.  Defaults to 0.",
        ),
    ] = 0.0,
) -> list[dict]:
    """Return positions of the requested bodies in the specified coordinate frame."""
    eph = _get_eph()
    t = _parse_time(datetime)
    earth = eph["earth"]
    sun = eph["sun"]

    if coordinate_system == "altaz_topocentric":
        if latitude is None or longitude is None:
            raise ValueError(
                "latitude and longitude are required for altaz_topocentric."
            )
        location = wgs84.latlon(latitude, longitude, elevation_m=elevation_m)
        observer = earth + location

    results = []

    for name in bodies:
        body = _resolve_body(name)

        if coordinate_system == "altaz_topocentric":
            pos = observer.at(t).observe(body).apparent()
            alt, az, dist = pos.altaz()
            results.append(
                {
                    "name": name,
                    "coordinate_system": "altaz_topocentric",
                    "altitude_deg": round(alt.degrees, 6),
                    "azimuth_deg": round(az.degrees, 6),
                    "distance_km": round(dist.km, 3),
                }
            )

        elif coordinate_system == "radec_apparent":
            pos = earth.at(t).observe(body).apparent()
            ra, dec, dist = pos.radec()
            results.append(
                {
                    "name": name,
                    "coordinate_system": "radec_apparent",
                    "right_ascension_hours": round(ra.hours, 8),
                    "declination_deg": round(dec.degrees, 8),
                    "distance_au": round(dist.au, 10),
                }
            )

        elif coordinate_system == "heliocentric_ecliptic_xyz":
            pos = sun.at(t).observe(body)
            xyz = pos.frame_xyz(ecliptic_J2000_frame).au
            results.append(
                {
                    "name": name,
                    "coordinate_system": "heliocentric_ecliptic_xyz",
                    "x_au": round(float(xyz[0]), 10),
                    "y_au": round(float(xyz[1]), 10),
                    "z_au": round(float(xyz[2]), 10),
                }
            )

        elif coordinate_system == "barycentric_xyz":
            pos = body.at(t)
            xyz = pos.position.au
            results.append(
                {
                    "name": name,
                    "coordinate_system": "barycentric_xyz",
                    "x_au": round(float(xyz[0]), 10),
                    "y_au": round(float(xyz[1]), 10),
                    "z_au": round(float(xyz[2]), 10),
                }
            )

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the MCP server using stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
