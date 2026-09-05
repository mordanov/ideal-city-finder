import asyncio
import math
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.config import settings
from app.models import City, PoiCache

# Max concurrent Google Places API calls to avoid quota exhaustion
_SEMAPHORE = asyncio.Semaphore(5)

CACHE_TTL_DAYS = 30
GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"


@dataclass
class PoiSearchResult:
    found: bool
    count: int
    nearest_distance_km: Optional[float]
    confidence_note: Optional[str] = None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _extract_city_coords(city: City) -> tuple[float, float]:
    """Extract lat/lon from the city's Geography column."""
    from geoalchemy2.shape import to_shape

    point = to_shape(city.location)
    return point.y, point.x  # lat, lon


async def _get_cached(session: AsyncSession, poi_query: str, city_id: int) -> Optional[PoiCache]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
    result = await session.execute(
        select(PoiCache).where(
            and_(PoiCache.query == poi_query, PoiCache.city_id == city_id, PoiCache.fetched_at >= cutoff)
        )
    )
    return result.scalar_one_or_none()


async def find_poi_near_city(
    session: AsyncSession,
    city: City,
    poi_query: str,
    radius_km: float,
    min_count: int = 1,
) -> PoiSearchResult:
    cached = await _get_cached(session, poi_query, city.id)
    if cached is not None:
        return PoiSearchResult(
            found=cached.found,
            count=cached.count or 0,
            nearest_distance_km=float(cached.distance_km) if cached.distance_km else None,
        )

    lat, lon = _extract_city_coords(city)
    confidence_note: Optional[str] = None

    async with _SEMAPHORE:
        async with httpx.AsyncClient() as client:
            payload = {
                "textQuery": poi_query,
                "locationBias": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lon},
                        "radius": radius_km * 1000,
                    }
                },
                "maxResultCount": 20,
            }
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": settings.google_maps_api_key,
                "X-Goog-FieldMask": "places.displayName,places.location,places.types,places.name",
            }
            response = await client.post(GOOGLE_PLACES_URL, json=payload, headers=headers, timeout=15.0)
            response.raise_for_status()
            data = response.json()

    places = data.get("places", [])

    # For "private schools" the Google Places API type=school doesn't distinguish
    # public vs private. We use name/type heuristic as a temporary approximation.
    # TODO: cross-reference with Ministerio de Educación registry
    # (data.gob.es, Registro Estatal de Centros Docentes, field "titularidad")
    # to get authoritative public/private classification.
    if (
        "privado" in poi_query.lower()
        or "private school" in poi_query.lower()
        or "colegio privado" in poi_query.lower()
    ):
        places = [
            p
            for p in places
            if any(
                kw
                in (
                    p.get("displayName", {}).get("text", "") + " ".join(p.get("types", []))
                ).lower()
                for kw in ["privado", "private", "colegio", "ikastola"]
            )
        ]
        confidence_note = (
            "Private/public school distinction based on name/type heuristic; "
            "cross-reference with Ministerio de Educación registry pending."
        )

    distances = []
    for place in places:
        loc = place.get("location", {})
        if loc.get("latitude") and loc.get("longitude"):
            d = _haversine_km(lat, lon, loc["latitude"], loc["longitude"])
            if d <= radius_km:
                distances.append(d)

    count = len(distances)
    found = count >= min_count
    nearest = min(distances) if distances else None

    # Upsert cache entry (insert or update on unique constraint)
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(PoiCache).values(
        query=poi_query,
        city_id=city.id,
        found=found,
        count=count,
        distance_km=nearest,
        raw_response={"places_count": len(places), "query": poi_query},
        fetched_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        constraint="uq_poi_cache_query_city",
        set_={
            "found": found,
            "count": count,
            "distance_km": nearest,
            "fetched_at": datetime.now(timezone.utc),
        },
    )
    await session.execute(stmt)
    await session.commit()

    return PoiSearchResult(found=found, count=count, nearest_distance_km=nearest, confidence_note=confidence_note)
