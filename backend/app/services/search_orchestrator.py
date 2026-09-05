import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory
from app.models import City, SearchResult, SearchRun, SearchRunStatus
from app.services.candidate_selector import filter_by_airport_proximity, get_candidate_cities
from app.services.confidence import criterion_confidence, overall_confidence
from app.services.google_places import find_poi_near_city
from app.services.rent_index import fetch_rent_index
from app.services.weather import get_city_sunny_days, get_national_average_sunny_days

# Max concurrent city evaluations
_CITY_SEMAPHORE_SIZE = 10


async def _evaluate_city(
    session: AsyncSession,
    city: City,
    parsed_criteria: list[dict],
    tolerance: float,
    airport_distances: dict[int, float],
) -> dict[str, Any]:
    """
    Evaluate all criteria for one city. Returns criteria_breakdown dict.
    Never raises — marks unavailable criteria with confidence=0 and a note.
    """
    breakdown: dict[str, Any] = {}
    national_avg: float | None = None

    for i, criterion in enumerate(parsed_criteria):
        key = f"{criterion['type']}_{i}"
        try:
            ctype = criterion["type"]

            if ctype == "poi_proximity":
                result = await find_poi_near_city(
                    session=session,
                    city=city,
                    poi_query=criterion["poi_query"],
                    radius_km=criterion["radius_km"],
                    min_count=criterion.get("min_count", 1),
                )
                if result.found:
                    dist = result.nearest_distance_km or 0.0
                    conf = criterion_confidence(dist, criterion["radius_km"], tolerance)
                else:
                    conf = 0.0
                breakdown[key] = {
                    "type": ctype,
                    "poi_query": criterion["poi_query"],
                    "confidence": conf,
                    "found": result.found,
                    "count": result.count,
                    "nearest_distance_km": result.nearest_distance_km,
                    "confidence_note": result.confidence_note,
                }

            elif ctype == "airport_proximity":
                dist = airport_distances.get(city.id)
                if dist is None:
                    conf = 0.0
                    breakdown[key] = {"type": ctype, "confidence": 0.0, "distance_km": None}
                else:
                    conf = criterion_confidence(dist, criterion["radius_km"], tolerance)
                    breakdown[key] = {"type": ctype, "confidence": conf, "distance_km": dist}

            elif ctype == "sunny_days_above_average":
                if national_avg is None:
                    national_avg = await get_national_average_sunny_days(session)
                city_days = await get_city_sunny_days(session, city)
                conf = 1.0 if city_days > national_avg else 0.0
                breakdown[key] = {
                    "type": ctype,
                    "confidence": conf,
                    "city_sunny_days": city_days,
                    "national_avg": national_avg,
                }

            elif ctype == "rent_price_per_sqm":
                result = await fetch_rent_index(session, city)
                if result.error:
                    conf = 0.0
                    breakdown[key] = {
                        "type": ctype,
                        "confidence": 0.0,
                        "error": result.error,
                        "source": result.source,
                    }
                else:
                    comparison = criterion["comparison"]
                    threshold = criterion["value"]
                    actual = result.price_per_sqm
                    if comparison in ("lt", "lte"):
                        conf = criterion_confidence(actual, threshold, tolerance)
                    else:  # gt, gte — city should be above threshold
                        conf = criterion_confidence(threshold, actual, tolerance)
                    breakdown[key] = {
                        "type": ctype,
                        "confidence": conf,
                        "actual_price": actual,
                        "threshold": threshold,
                        "comparison": comparison,
                        "source": result.source,
                        "period": result.period,
                    }

            elif ctype == "unsupported":
                breakdown[key] = {
                    "type": ctype,
                    "confidence": 0.0,
                    "original_text": criterion.get("original_text", ""),
                    "note": "Unsupported criterion; excluded from scoring",
                }

        except Exception as exc:
            breakdown[key] = {
                "type": criterion.get("type", "unknown"),
                "confidence": 0.0,
                "error": str(exc),
            }

    return breakdown


async def run_search(run_id: str, ctx: dict | None = None) -> None:
    """
    Main search pipeline. Registered as an arq task.
    ctx is the arq worker context (may be None when called directly in tests).
    """
    async with async_session_factory() as session:
        run = await session.get(SearchRun, uuid.UUID(run_id))
        if not run:
            return

        run.status = SearchRunStatus.running
        await session.commit()

        try:
            parsed_criteria = run.parsed_criteria or []
            tolerance = float(run.tolerance)

            # 1. Get candidate cities
            cities = await get_candidate_cities(session, parsed_criteria)

            # 2. If airport_proximity criterion present, pre-filter and capture distances
            airport_distances: dict[int, float] = {}
            airport_criteria = [c for c in parsed_criteria if c.get("type") == "airport_proximity"]
            if airport_criteria:
                max_radius = max(c["radius_km"] for c in airport_criteria)
                city_distance_pairs = await filter_by_airport_proximity(session, cities, max_radius + tolerance)
                cities = [c for c, _ in city_distance_pairs]
                airport_distances = {c.id: d for c, d in city_distance_pairs}

            # 3. Evaluate all cities in parallel (limited concurrency)
            semaphore = asyncio.Semaphore(_CITY_SEMAPHORE_SIZE)

            async def evaluate_with_semaphore(city: City):
                async with semaphore:
                    return city, await _evaluate_city(
                        session, city, parsed_criteria, tolerance, airport_distances
                    )

            city_results = await asyncio.gather(
                *[evaluate_with_semaphore(c) for c in cities],
                return_exceptions=True,
            )

            # 4. Store SearchResults
            for item in city_results:
                if isinstance(item, Exception):
                    continue
                city, breakdown = item
                scores = {k: v["confidence"] for k, v in breakdown.items() if "confidence" in v}
                oc = overall_confidence(scores)

                result = SearchResult(
                    run_id=run.id,
                    city_id=city.id,
                    overall_confidence=oc,
                    criteria_breakdown=breakdown,
                )
                session.add(result)

            await session.flush()

            # 5. Run comparison if requested
            if run.compared_to_run_id:
                old_results_q = await session.execute(
                    select(SearchResult).where(SearchResult.run_id == run.compared_to_run_id)
                )
                old_results = {r.city_id: r for r in old_results_q.scalars()}
                new_results_q = await session.execute(
                    select(SearchResult).where(SearchResult.run_id == run.id)
                )
                new_results = {r.city_id: r for r in new_results_q.scalars()}

                added = [cid for cid in new_results if cid not in old_results]
                removed = [cid for cid in old_results if cid not in new_results]
                deltas = {
                    str(cid): float(new_results[cid].overall_confidence) - float(old_results[cid].overall_confidence)
                    for cid in new_results
                    if cid in old_results
                }
                run.comparison_summary = {
                    "added_cities": added,
                    "removed_cities": removed,
                    "confidence_deltas": deltas,
                }

            run.status = SearchRunStatus.done
            run.completed_at = datetime.now(timezone.utc)
            await session.commit()

        except Exception as exc:
            run.status = SearchRunStatus.failed
            await session.commit()
            raise
