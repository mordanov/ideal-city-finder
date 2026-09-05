from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import City, WeatherNormals

CACHE_TTL_DAYS = 30
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
SUNNY_DAY_THRESHOLD_SECONDS = 6 * 3600  # 6h of sunshine = "sunny day"


async def _get_cached_normal(session: AsyncSession, city_id: Optional[int]) -> Optional[WeatherNormals]:
    """Retrieve cached weather normal; city_id=None means national average."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
    query = select(WeatherNormals).where(
        and_(WeatherNormals.city_id == city_id, WeatherNormals.fetched_at >= cutoff)
    )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def _fetch_open_meteo_sunny_days(lat: float, lon: float) -> float:
    """Fetch ~3-year average sunny days/year from Open-Meteo for given coordinates."""
    end = datetime.now() - timedelta(days=30)  # avoid incomplete recent month
    start = end - timedelta(days=3 * 365)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(OPEN_METEO_URL, params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "daily": "sunshine_duration",
            "timezone": "Europe/Madrid",
        })
        resp.raise_for_status()
        data = resp.json()

    sunshine_seconds = data["daily"]["sunshine_duration"]
    total_days = len(sunshine_seconds)
    sunny_days = sum(1 for s in sunshine_seconds if s >= SUNNY_DAY_THRESHOLD_SECONDS)
    years = total_days / 365.25
    return sunny_days / years


async def _save_normal(session: AsyncSession, city_id: Optional[int], avg_days: float) -> None:
    normal = WeatherNormals(
        city_id=city_id,
        avg_sunny_days_year=avg_days,
        source="OpenMeteo",
        fetched_at=datetime.now(timezone.utc),
    )
    session.add(normal)
    await session.commit()


async def get_national_average_sunny_days(session: AsyncSession) -> float:
    """
    Spain-wide average sunny days per year.
    Represented in WeatherNormals with city_id=NULL (national average).
    Uses the geographic center of Spain (Madrid coordinates) as the national proxy —
    a reasonable approximation given Spain's climatic diversity.
    """
    cached = await _get_cached_normal(session, city_id=None)
    if cached:
        return float(cached.avg_sunny_days_year)

    avg = await _fetch_open_meteo_sunny_days(lat=40.4168, lon=-3.7038)
    await _save_normal(session, city_id=None, avg_days=avg)
    return avg


async def get_city_sunny_days(session: AsyncSession, city: City) -> float:
    """Sunny days per year for a specific city, using its coordinates."""
    cached = await _get_cached_normal(session, city_id=city.id)
    if cached:
        return float(cached.avg_sunny_days_year)

    from geoalchemy2.shape import to_shape
    point = to_shape(city.location)
    lat, lon = point.y, point.x

    avg = await _fetch_open_meteo_sunny_days(lat=lat, lon=lon)
    await _save_normal(session, city_id=city.id, avg_days=avg)
    return avg
