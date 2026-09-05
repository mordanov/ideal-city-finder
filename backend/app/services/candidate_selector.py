from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Airport, City

# Minimum population for cities expected to have urban infrastructure like
# conservatories or private schools. Below this threshold such infrastructure
# is extremely unlikely.
URBAN_INFRASTRUCTURE_MIN_POPULATION = 5000

# Criterion type strings that imply urban infrastructure.
URBAN_INFRASTRUCTURE_TYPES = {"poi_proximity"}


def _requires_urban_infrastructure(parsed_criteria: list[dict]) -> bool:
    """Return True if any criterion implies urban infrastructure."""
    return any(c.get("type") in URBAN_INFRASTRUCTURE_TYPES for c in parsed_criteria)


async def get_candidate_cities(
    session: AsyncSession,
    parsed_criteria: list[dict],
    min_population: int | None = None,
) -> list[City]:
    """
    Returns candidate cities filtered by population when the search implies
    urban infrastructure. min_population overrides the default constant.
    """
    stmt = select(City)

    if _requires_urban_infrastructure(parsed_criteria):
        threshold = min_population if min_population is not None else URBAN_INFRASTRUCTURE_MIN_POPULATION
        stmt = stmt.where(City.population >= threshold)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def filter_by_airport_proximity(
    session: AsyncSession,
    cities: list[City],
    radius_km: float,
) -> list[tuple[City, float]]:
    """
    Filter cities to those within radius_km of any Spanish airport.
    Uses PostGIS ST_DWithin in a single SQL query (no Python-level distance loop).
    Returns (city, nearest_airport_distance_km) tuples for each passing city.
    """
    if not cities:
        return []

    city_ids = [c.id for c in cities]
    radius_m = radius_km * 1000

    # Single query: for each city find nearest airport distance, filter by radius.
    # ST_DWithin on Geography uses meters; ST_Distance on Geography also returns meters.
    stmt = text(
        """
        SELECT
            c.id AS city_id,
            MIN(ST_Distance(c.location, a.location)) / 1000.0 AS nearest_km
        FROM cities c
        JOIN airports a
          ON ST_DWithin(c.location, a.location, :radius_m)
        WHERE c.id = ANY(:city_ids)
        GROUP BY c.id
        """
    )

    rows = (
        await session.execute(stmt, {"radius_m": radius_m, "city_ids": city_ids})
    ).fetchall()

    distance_by_city_id = {row.city_id: float(row.nearest_km) for row in rows}

    city_by_id = {c.id: c for c in cities}
    return [
        (city_by_id[city_id], dist)
        for city_id, dist in distance_by_city_id.items()
    ]
