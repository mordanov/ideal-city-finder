import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import City, SearchResult, SearchRun, SearchRunStatus
from app.services.auth import get_current_user
from app.services.criteria_parser import parse_criteria

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    tolerance: float = 0.0
    compare_to_run_id: Optional[str] = None
    language: str = "en"


@router.post("", response_model=dict)
async def start_search(
    req: SearchRequest,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    parsed = await parse_criteria(req.query, language=req.language)
    parsed_dicts = [c.model_dump() for c in parsed]

    compared_id = uuid.UUID(req.compare_to_run_id) if req.compare_to_run_id else None
    run = SearchRun(
        user_id=current_user,
        user_query=req.query,
        language=req.language,
        parsed_criteria=parsed_dicts,
        tolerance=req.tolerance,
        compared_to_run_id=compared_id,
        status=SearchRunStatus.pending,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    # Enqueue in arq; fall back to direct execution if Redis is unavailable (dev mode)
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from app.config import settings as s

        pool = await create_pool(RedisSettings.from_dsn(s.redis_url))
        await pool.enqueue_job("run_search", str(run.id))
        await pool.close()
    except Exception:
        # Dev fallback: run synchronously when Redis is not available
        from app.services.search_orchestrator import run_search

        await run_search(str(run.id))

    return {"run_id": str(run.id)}


@router.get("/history", response_model=list[dict])
async def get_history(
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SearchRun)
        .where(SearchRun.user_id == current_user)
        .order_by(SearchRun.created_at.desc())
        .limit(50)
    )
    runs = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "user_query": r.user_query,
            "created_at": r.created_at.isoformat(),
            "status": r.status.value,
        }
        for r in runs
    ]


@router.get("/{run_id}", response_model=dict)
async def get_run(
    run_id: str,
    current_user: str = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    run = await session.get(SearchRun, uuid.UUID(run_id))
    if not run or run.user_id != current_user:
        raise HTTPException(status_code=404, detail="Run not found")

    out: dict = {
        "run_id": str(run.id),
        "status": run.status.value,
        "user_query": run.user_query,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "comparison_summary": run.comparison_summary,
    }

    if run.status == SearchRunStatus.done:
        results_q = await session.execute(
            select(SearchResult, City)
            .join(City, SearchResult.city_id == City.id)
            .where(SearchResult.run_id == run.id)
            .order_by(SearchResult.overall_confidence.desc())
        )
        results = []
        for sr, city in results_q.all():
            from geoalchemy2.shape import to_shape

            point = to_shape(city.location) if city.location else None
            results.append(
                {
                    "city_id": city.id,
                    "city_name": city.name,
                    "province": city.province,
                    "lat": point.y if point else None,
                    "lon": point.x if point else None,
                    "overall_confidence": float(sr.overall_confidence),
                    "criteria_breakdown": sr.criteria_breakdown,
                }
            )
        out["results"] = results

    return out
