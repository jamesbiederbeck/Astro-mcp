"""Tests for astro_mcp using Skyfield's bundled test ephemeris data.

All tests use the small de430-2015-03-02.bsp test kernel (covers 2015-02-18
through 2015-03-06) so that no network access is required.
"""

from __future__ import annotations

import math
import os
from unittest.mock import patch

import pytest

# Path to Skyfield's bundled test data
_TEST_BSP = os.path.join(
    os.path.dirname(__file__),
    "..",
    "src",
    "astro_mcp",
    "_test_data",
    "de430-2015-03-02.bsp",
)

# Canonical test datetime within the test-BSP window
_TEST_DT = "2015-03-02T12:00:00Z"


# ---------------------------------------------------------------------------
# Helpers – patch the global ephemeris so tests never hit the network
# ---------------------------------------------------------------------------


def _load_test_eph():
    """Load the tiny test kernel shipped with Skyfield."""
    from skyfield.api import load_file

    skyfield_test_data = os.path.join(
        os.path.dirname(
            __import__("skyfield").__file__
        ),
        "tests",
        "data",
        "de430-2015-03-02.bsp",
    )
    return load_file(skyfield_test_data)


@pytest.fixture(autouse=True)
def patch_ephemeris(monkeypatch):
    """Replace _get_eph() in the server with the small test kernel."""
    import astro_mcp.server as srv

    test_eph = _load_test_eph()
    monkeypatch.setattr(srv, "_eph", test_eph)
    monkeypatch.setattr(srv, "_get_eph", lambda: test_eph)
    yield


# ---------------------------------------------------------------------------
# phases tool tests
# ---------------------------------------------------------------------------


class TestPhases:
    def test_moon_phase_degrees(self):
        from astro_mcp.server import phases

        result = phases(bodies=["moon"], format="degrees", datetime=_TEST_DT)
        assert "bodies" in result
        assert len(result["bodies"]) == 1
        body = result["bodies"][0]
        assert body["name"] == "moon"
        phase = body["phase"]
        assert isinstance(phase, float)
        assert 0.0 <= phase < 360.0

    def test_moon_phase_radians(self):
        from astro_mcp.server import phases

        result = phases(bodies=["moon"], format="radians", datetime=_TEST_DT)
        phase = result["bodies"][0]["phase"]
        assert isinstance(phase, float)
        assert 0.0 <= phase < 2 * math.pi

    def test_moon_phase_natural(self):
        from astro_mcp.server import phases

        result = phases(bodies=["moon"], format="natural", datetime=_TEST_DT)
        phase = result["bodies"][0]["phase"]
        expected_names = {
            "New Moon",
            "Waxing Crescent",
            "First Quarter",
            "Waxing Gibbous",
            "Full Moon",
            "Waning Gibbous",
            "Last Quarter",
            "Waning Crescent",
        }
        assert phase in expected_names

    def test_planet_phase_degrees(self):
        from astro_mcp.server import phases

        result = phases(bodies=["mars"], format="degrees", datetime=_TEST_DT)
        body = result["bodies"][0]
        assert body["name"] == "mars"
        assert isinstance(body["phase"], float)
        assert 0.0 <= body["phase"] <= 180.0
        assert 0.0 <= body["fraction_illuminated"] <= 1.0

    def test_planet_phase_radians(self):
        from astro_mcp.server import phases

        result = phases(bodies=["mars"], format="radians", datetime=_TEST_DT)
        pa = result["bodies"][0]["phase"]
        assert isinstance(pa, float)
        assert 0.0 <= pa <= math.pi

    def test_planet_phase_natural(self):
        from astro_mcp.server import phases

        result = phases(bodies=["mars"], format="natural", datetime=_TEST_DT)
        phase = result["bodies"][0]["phase"]
        assert "illuminated" in phase

    def test_multiple_bodies(self):
        from astro_mcp.server import phases

        result = phases(bodies=["moon", "mars"], format="degrees", datetime=_TEST_DT)
        assert len(result["bodies"]) == 2
        names = [b["name"] for b in result["bodies"]]
        assert "moon" in names
        assert "mars" in names

    def test_unknown_body_raises(self):
        from astro_mcp.server import phases

        with pytest.raises(ValueError, match="Unknown body"):
            phases(bodies=["krypton"], format="degrees", datetime=_TEST_DT)

    def test_default_time_uses_now(self, monkeypatch):
        """When datetime=None the server calls _ts.now(); patch it to stay in BSP range."""
        import astro_mcp.server as srv
        from astro_mcp.server import phases

        fixed_t = srv._ts.tt_jd(2457083.5)  # 2015-03-02
        monkeypatch.setattr(srv._ts, "now", lambda: fixed_t)

        result = phases(bodies=["moon"], format="degrees")
        assert len(result["bodies"]) == 1

    def test_moon_phase_name_mapping(self):
        """All 8 sectors of the phase-name wheel should be reachable."""
        from astro_mcp.server import _moon_phase_name

        expected = [
            (0.0, "New Moon"),
            (45.0, "Waxing Crescent"),
            (90.0, "First Quarter"),
            (135.0, "Waxing Gibbous"),
            (180.0, "Full Moon"),
            (225.0, "Waning Gibbous"),
            (270.0, "Last Quarter"),
            (315.0, "Waning Crescent"),
        ]
        for angle, name in expected:
            assert _moon_phase_name(angle) == name, f"angle={angle}"

    def test_moon_phase_boundary(self):
        """The 22.5° boundary between New Moon and Waxing Crescent."""
        from astro_mcp.server import _moon_phase_name

        # Just below 22.5° → New Moon
        assert _moon_phase_name(22.4) == "New Moon"
        # At 22.5° → first sector ends; Waxing Crescent begins
        assert _moon_phase_name(22.5) == "Waxing Crescent"
        # Wrap-around: 337.5° is the boundary between Waning Crescent and New Moon → New Moon
        assert _moon_phase_name(337.5) == "New Moon"


# ---------------------------------------------------------------------------
# positions tool tests
# ---------------------------------------------------------------------------


class TestPositions:
    # ------- altaz_topocentric -------

    def test_altaz_moon(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["moon"],
            datetime=_TEST_DT,
            coordinate_system="altaz_topocentric",
            latitude=40.7128,
            longitude=-74.006,
            elevation_m=10.0,
        )
        assert len(result) == 1
        r = result[0]
        assert r["name"] == "moon"
        assert r["coordinate_system"] == "altaz_topocentric"
        assert -90.0 <= r["altitude_deg"] <= 90.0
        assert 0.0 <= r["azimuth_deg"] < 360.0
        assert r["distance_km"] > 300_000  # Moon is ~384,400 km away

    def test_altaz_requires_lat_lon(self):
        from astro_mcp.server import positions

        with pytest.raises(ValueError, match="latitude and longitude are required"):
            positions(
                bodies=["moon"],
                datetime=_TEST_DT,
                coordinate_system="altaz_topocentric",
            )

    def test_altaz_mars(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["mars"],
            datetime=_TEST_DT,
            coordinate_system="altaz_topocentric",
            latitude=51.5,
            longitude=-0.12,
        )
        r = result[0]
        assert r["name"] == "mars"
        assert -90.0 <= r["altitude_deg"] <= 90.0

    # ------- radec_apparent -------

    def test_radec_moon(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["moon"],
            datetime=_TEST_DT,
            coordinate_system="radec_apparent",
        )
        r = result[0]
        assert r["coordinate_system"] == "radec_apparent"
        assert 0.0 <= r["right_ascension_hours"] < 24.0
        assert -90.0 <= r["declination_deg"] <= 90.0
        assert r["distance_au"] > 0

    def test_radec_mars(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["mars"],
            datetime=_TEST_DT,
            coordinate_system="radec_apparent",
        )
        r = result[0]
        assert 0.0 <= r["right_ascension_hours"] < 24.0

    # ------- heliocentric_ecliptic_xyz -------

    def test_helio_ecliptic_mars(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["mars"],
            datetime=_TEST_DT,
            coordinate_system="heliocentric_ecliptic_xyz",
        )
        r = result[0]
        assert r["coordinate_system"] == "heliocentric_ecliptic_xyz"
        # Mars is roughly 1.5 AU from the Sun
        dist_au = math.sqrt(r["x_au"] ** 2 + r["y_au"] ** 2 + r["z_au"] ** 2)
        assert 1.0 < dist_au < 2.0

    def test_helio_ecliptic_moon(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["moon"],
            datetime=_TEST_DT,
            coordinate_system="heliocentric_ecliptic_xyz",
        )
        r = result[0]
        # Moon is ~1 AU from the Sun
        dist_au = math.sqrt(r["x_au"] ** 2 + r["y_au"] ** 2 + r["z_au"] ** 2)
        assert 0.98 < dist_au < 1.02

    # ------- barycentric_xyz -------

    def test_barycentric_mars(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["mars"],
            datetime=_TEST_DT,
            coordinate_system="barycentric_xyz",
        )
        r = result[0]
        assert r["coordinate_system"] == "barycentric_xyz"
        dist_au = math.sqrt(r["x_au"] ** 2 + r["y_au"] ** 2 + r["z_au"] ** 2)
        assert 1.0 < dist_au < 2.5

    def test_barycentric_moon(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["moon"],
            datetime=_TEST_DT,
            coordinate_system="barycentric_xyz",
        )
        r = result[0]
        dist_au = math.sqrt(r["x_au"] ** 2 + r["y_au"] ** 2 + r["z_au"] ** 2)
        assert 0.98 < dist_au < 1.02

    # ------- multiple bodies -------

    def test_multiple_bodies_radec(self):
        from astro_mcp.server import positions

        result = positions(
            bodies=["moon", "mars", "venus"],
            datetime=_TEST_DT,
            coordinate_system="radec_apparent",
        )
        assert len(result) == 3
        names = [r["name"] for r in result]
        assert "moon" in names
        assert "mars" in names
        assert "venus" in names

    def test_unknown_body_raises(self):
        from astro_mcp.server import positions

        with pytest.raises(ValueError, match="Unknown body"):
            positions(
                bodies=["nibiru"],
                datetime=_TEST_DT,
                coordinate_system="radec_apparent",
            )

    def test_default_time_and_frame(self, monkeypatch):
        """Calling with only bodies and observer location should work."""
        import astro_mcp.server as srv
        from astro_mcp.server import positions

        fixed_t = srv._ts.tt_jd(2457083.5)  # 2015-03-02
        monkeypatch.setattr(srv._ts, "now", lambda: fixed_t)

        result = positions(
            bodies=["moon"],
            coordinate_system="altaz_topocentric",
            latitude=0.0,
            longitude=0.0,
        )
        assert len(result) == 1
        assert "altitude_deg" in result[0]
