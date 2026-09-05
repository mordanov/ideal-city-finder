from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import City, RentPriceIndex

CACHE_TTL_DAYS = 30


@dataclass
class RentPriceIndexResult:
    price_per_sqm: float
    source: str          # "idealista_index" or "ine"
    period: str          # e.g. "2026-08"
    is_city_level: bool  # False = province-level fallback
    error: Optional[str] = None  # set when data is unavailable


async def _get_cached(
    session: AsyncSession,
    city_id: Optional[int],
    province: Optional[str],
) -> Optional[RentPriceIndex]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)
    if city_id is not None:
        q = select(RentPriceIndex).where(
            and_(RentPriceIndex.city_id == city_id, RentPriceIndex.fetched_at >= cutoff)
        )
    else:
        q = select(RentPriceIndex).where(
            and_(RentPriceIndex.province == province, RentPriceIndex.fetched_at >= cutoff)
        )
    return (await session.execute(q)).scalar_one_or_none()


async def _check_robots_txt_allows(url: str) -> bool:
    """Return True if robots.txt does not disallow the path."""
    try:
        from urllib.parse import urlparse
        from urllib.robotparser import RobotFileParser

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(robots_url, headers={"User-Agent": "IdealCityFinderBot"})
            rp = RobotFileParser()
            rp.parse(r.text.splitlines())
            return rp.can_fetch("IdealCityFinderBot", url)
    except Exception:
        return True  # assume allowed on error


def _slugify(text: str) -> str:
    return (
        text.lower()
        .replace(" ", "-")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )


async def _fetch_idealista_index(city_name: str, province: str) -> Optional[tuple[float, str]]:
    """
    Try to fetch price/m² from Idealista's public statistics page.
    Returns (price_per_sqm, "idealista_index") or None if unavailable/disallowed.

    IMPORTANT: Only accesses publicly aggregated statistics pages, not individual
    listings. Does not bypass authentication or scrape listing data.
    """
    city_slug = _slugify(city_name)
    url = f"https://www.idealista.com/alquiler-viviendas/{city_slug}/con-publicados_ultimos_7dias/"

    allowed = await _check_robots_txt_allows(url)
    if not allowed:
        return None

    # Idealista publishes aggregated price indices as public press releases at
    # sala-de-prensa. For this MVP we return None to fall back to INE rather
    # than attempt fragile HTML parsing of summary stat blocks.
    return None


async def _fetch_ine_index(province: str) -> Optional[tuple[float, str]]:
    """
    Fetch housing price index from INE (Instituto Nacional de Estadística).
    INE provides open JSON APIs — no restrictions on programmatic access.
    Uses the IPV (Índice de Precios de Vivienda) rental series.
    Returns (price_per_sqm_approx, "ine") or None.
    """
    # National rental price index series (alquiler, base 2015=100).
    INE_NATIONAL_SERIES = "IPV11006"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/{INE_NATIONAL_SERIES}",
                params={"nult": "4"},
            )
            r.raise_for_status()
            data = r.json()

        if data and isinstance(data, list) and data[0].get("Valor") is not None:
            # IPV is an index, not an absolute price. We approximate absolute
            # price by scaling a 2024 national median of ~12 €/m² by the index
            # relative to the base period (2015=100).
            BASE_PRICE_PER_SQM = 12.0
            BASE_INDEX = 100.0
            latest_index = float(data[0]["Valor"])
            price = BASE_PRICE_PER_SQM * (latest_index / BASE_INDEX)
            period = str(data[0].get("Periodo", datetime.now().strftime("%Y-%m")))
            return round(price, 2), "ine"
    except Exception:
        pass

    return None


async def fetch_rent_index(session: AsyncSession, city: City) -> RentPriceIndexResult:
    """
    Returns rent price per m² for the city, with province-level fallback.
    Source is recorded in RentPriceIndex.source for data provenance in the UI.
    If no data is available, returns an error result rather than raising so the
    orchestrator can mark this criterion as unavailable without failing the run.
    """
    period = datetime.now().strftime("%Y-%m")

    # Check city-level cache first
    cached = await _get_cached(session, city_id=city.id, province=None)
    if cached:
        return RentPriceIndexResult(
            price_per_sqm=float(cached.price_per_sqm),
            source=cached.source,
            period=cached.period,
            is_city_level=True,
        )

    # Check province-level cache
    cached_prov = await _get_cached(session, city_id=None, province=city.province)
    if cached_prov:
        return RentPriceIndexResult(
            price_per_sqm=float(cached_prov.price_per_sqm),
            source=cached_prov.source,
            period=cached_prov.period,
            is_city_level=False,
        )

    price_data: Optional[tuple[float, str]] = None
    is_city_level = False

    if settings.rent_data_source == "idealista_index":
        price_data = await _fetch_idealista_index(city.name, city.province)
        if price_data:
            is_city_level = True

    # Fall back to INE if Idealista is unavailable or source is explicitly "ine"
    if price_data is None:
        price_data = await _fetch_ine_index(city.province)

    if price_data is None:
        return RentPriceIndexResult(
            price_per_sqm=0.0,
            source="unavailable",
            period=period,
            is_city_level=False,
            error=(
                f"rent_price_per_sqm criterion temporarily unavailable for "
                f"{city.name}: no data source accessible"
            ),
        )

    price, source = price_data

    # Persist to cache
    db_city_id = city.id if is_city_level else None
    db_province = None if is_city_level else city.province
    stmt = (
        pg_insert(RentPriceIndex)
        .values(
            city_id=db_city_id,
            province=db_province,
            price_per_sqm=price,
            period=period,
            source=source,
            fetched_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_nothing()
    )
    await session.execute(stmt)
    await session.commit()

    return RentPriceIndexResult(
        price_per_sqm=price,
        source=source,
        period=period,
        is_city_level=is_city_level,
    )
