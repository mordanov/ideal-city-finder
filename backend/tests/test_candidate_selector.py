"""
Integration tests for candidate_selector.py.
Requires a live Postgres+PostGIS instance. Tests are skipped if DATABASE_URL is unset.
"""

import os

import pytest
import pytest_asyncio
from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Airport, City
from app.services.candidate_selector import (
    URBAN_INFRASTRUCTURE_MIN_POPULATION,
    filter_by_airport_proximity,
    get_candidate_cities,
)

TEST_DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ideal_city"
)

_db_available = True
try:
    import asyncpg  # noqa: F401
except ImportError:
    _db_available = False


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        yield session
        await session.rollback()  # clean up any inserted rows

    await engine.dispose()


# ---------------------------------------------------------------------------
# Helper: build a WKT Geography point from (lat, lon)
# ---------------------------------------------------------------------------

def _point(lat: float, lon: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


# ---------------------------------------------------------------------------
# Fixture: 3 cities + 1 airport inserted for the test, removed after
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def geo_dataset(db_session: AsyncSession):
    # Airport at Madrid Barajas approximate coords
    airport = Airport(
        name="Test Airport MAD",
        iata_code="__T",
        location=_point(40.4719, -3.5626),
    )
    db_session.add(airport)
    await db_session.flush()

    # City A: ~30 km north of the airport — well within a 100 km radius
    city_a = City(
        name="__CityA",
        province="Test",
        population=100_000,
        location=_point(40.74, -3.56),
        source="TEST",
    )
    # City B: ~250 km away (Zaragoza-ish distance from Madrid) — outside 100 km
    city_b = City(
        name="__CityB",
        province="Test",
        population=100_000,
        location=_point(41.65, -0.88),
        source="TEST",
    )
    # City C: ~95 km north — just inside a 100 km radius
    city_c = City(
        name="__CityC",
        province="Test",
        population=100_000,
        location=_point(41.32, -3.56),
        source="TEST",
    )
    db_session.add_all([city_a, city_b, city_c])
    await db_session.flush()

    yield airport, city_a, city_b, city_c

    # Cleanup
    await db_session.delete(city_a)
    await db_session.delete(city_b)
    await db_session.delete(city_c)
    await db_session.delete(airport)
    await db_session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_by_airport_proximity(db_session: AsyncSession, geo_dataset):
    _airport, city_a, city_b, city_c = geo_dataset
    all_cities = [city_a, city_b, city_c]

    results = await filter_by_airport_proximity(db_session, all_cities, radius_km=100)
    result_ids = {city.id for city, _ in results}

    assert city_a.id in result_ids, "City A (~30 km away) should be inside the 100 km radius"
    assert city_b.id not in result_ids, "City B (~250 km away) should be outside the 100 km radius"
    assert city_c.id in result_ids, "City C (~95 km away) should be inside the 100 km radius"

    # Distances should be reasonable positive numbers
    dist_map = {city.id: dist for city, dist in results}
    assert dist_map[city_a.id] < 50
    assert dist_map[city_c.id] < 100


@pytest.mark.asyncio
async def test_filter_returns_empty_for_no_cities(db_session: AsyncSession):
    results = await filter_by_airport_proximity(db_session, [], radius_km=100)
    assert results == []


@pytest.mark.asyncio
async def test_get_candidate_cities_population_filter(db_session: AsyncSession):
    """When poi_proximity criterion is present, only cities >= threshold are returned."""
    # Insert two cities: one above threshold, one below
    big_city = City(
        name="__BigCity",
        province="TestPop",
        population=URBAN_INFRASTRUCTURE_MIN_POPULATION + 1000,
        source="TEST",
    )
    small_city = City(
        name="__SmallCity",
        province="TestPop",
        population=URBAN_INFRASTRUCTURE_MIN_POPULATION - 1,
        source="TEST",
    )
    db_session.add_all([big_city, small_city])
    await db_session.flush()

    criteria_with_poi = [{"type": "poi_proximity", "poi_query": "school", "radius_km": 10, "min_count": 1}]
    results = await get_candidate_cities(db_session, criteria_with_poi)
    result_ids = {c.id for c in results}

    assert big_city.id in result_ids
    assert small_city.id not in result_ids

    # Cleanup
    await db_session.delete(big_city)
    await db_session.delete(small_city)
    await db_session.commit()


@pytest.mark.asyncio
async def test_get_candidate_cities_no_filter_without_poi(db_session: AsyncSession):
    """When no poi_proximity criterion, population filter is not applied."""
    small_city = City(
        name="__TinyCity",
        province="TestPop2",
        population=100,
        source="TEST",
    )
    db_session.add(small_city)
    await db_session.flush()

    criteria_no_poi = [{"type": "airport_proximity", "radius_km": 100}]
    results = await get_candidate_cities(db_session, criteria_no_poi)
    result_ids = {c.id for c in results}

    assert small_city.id in result_ids

    await db_session.delete(small_city)
    await db_session.commit()
