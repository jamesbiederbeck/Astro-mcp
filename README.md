# Astro-MCP

A [FastMCP](https://github.com/PrefectHQ/fastmcp) service that returns celestial body positions and moon phases, powered by [Skyfield](https://rhodesmill.org/skyfield/) and the JPL DE421 planetary ephemeris.

---

## Tools

### `phases`

Returns the phase of one or more celestial bodies at a given time.

**Inputs**

| Parameter  | Type                                   | Default    | Description |
|------------|----------------------------------------|------------|-------------|
| `bodies`   | `list[str]`                            | required   | Body names, e.g. `["moon", "venus", "mars"]` |
| `format`   | `"radians"` \| `"degrees"` \| `"natural"` | `"degrees"` | Output format for the phase value |
| `datetime` | ISO 8601 string \| `null`              | current UTC | Reference time |

**Output**

```json
{
  "bodies": [
    {"name": "moon", "phase": "Waxing Gibbous"},
    {"name": "mars", "phase": 18.15, "fraction_illuminated": 0.975}
  ]
}
```

- **Moon** — `format="natural"` returns one of the eight named lunar phases:
  *New Moon, Waxing Crescent, First Quarter, Waxing Gibbous, Full Moon, Waning Gibbous, Last Quarter, Waning Crescent*.
  `format="degrees"` or `"radians"` returns the raw 0–360° lunation angle.

- **Other bodies** — `format="natural"` returns `"97.5% illuminated"`.
  `format="degrees"` or `"radians"` returns the Sun–Body–Observer phase angle.
  The response also includes `fraction_illuminated` (0–1).

---

### `positions`

Returns the position of one or more celestial bodies in one of four coordinate frames.

**Inputs**

| Parameter           | Type              | Default               | Description |
|---------------------|-------------------|-----------------------|-------------|
| `bodies`            | `list[str]`       | required              | Body names |
| `datetime`          | ISO 8601 \| `null`| current UTC           | Reference time |
| `coordinate_system` | see below         | `"altaz_topocentric"` | Coordinate frame |
| `latitude`          | `float` \| `null` | `null`                | Observer latitude (°), required for `altaz_topocentric` |
| `longitude`         | `float` \| `null` | `null`                | Observer longitude (°), required for `altaz_topocentric` |
| `elevation_m`       | `float`           | `0.0`                 | Observer elevation (m) |

**Coordinate systems**

| Value                      | Description | Output fields |
|----------------------------|-------------|---------------|
| `altaz_topocentric`        | Altitude/azimuth from a surface location (requires `latitude` + `longitude`) | `altitude_deg`, `azimuth_deg`, `distance_km` |
| `radec_apparent`           | Geocentric apparent RA/Dec (J2000) | `right_ascension_hours`, `declination_deg`, `distance_au` |
| `heliocentric_ecliptic_xyz`| Heliocentric J2000 ecliptic Cartesian (AU) | `x_au`, `y_au`, `z_au` |
| `barycentric_xyz`          | Solar System Barycentre ICRF Cartesian (AU) | `x_au`, `y_au`, `z_au` |

**Output** — a list of position dicts, one per body:

```json
[
  {
    "name": "moon",
    "coordinate_system": "altaz_topocentric",
    "altitude_deg": 49.11,
    "azimuth_deg": 118.43,
    "distance_km": 397749.8
  }
]
```

---

## Supported Bodies

`sun`, `mercury`, `venus`, `earth`, `moon`, `mars`, `jupiter`, `saturn`, `uranus`, `neptune`, `pluto`

---

## Installation & Running

```bash
pip install -e .
```

On first use the server downloads `de421.bsp` (~17 MB) from NASA into `~/.skyfield/`.

Run with stdio transport (default for MCP clients):

```bash
astro-mcp
```

Or run directly:

```bash
python -m astro_mcp.server
```

---

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests use Skyfield's bundled test ephemeris and require no network access.

---

## Example (Skyfield)

```python
from skyfield.api import load

ts = load.timescale()
t = ts.now()

planets = load('de421.bsp')
earth, mars = planets['earth'], planets['mars barycenter']

pos = earth.at(t).observe(mars).apparent()
print(pos.altaz())
```
