import enum
import uuid
from datetime import datetime
from typing import Optional

from geoalchemy2 import Geography
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SearchRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    province: Mapped[str] = mapped_column(String(100), nullable=False)
    population: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    location: Mapped[object] = mapped_column(Geography("POINT", srid=4326), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="INE")

    poi_caches: Mapped[list["PoiCache"]] = relationship("PoiCache", back_populates="city")
    weather_normals: Mapped[list["WeatherNormals"]] = relationship("WeatherNormals", back_populates="city")
    rent_prices: Mapped[list["RentPriceIndex"]] = relationship("RentPriceIndex", back_populates="city")
    search_results: Mapped[list["SearchResult"]] = relationship("SearchResult", back_populates="city")

    __table_args__ = (UniqueConstraint("name", "province", name="uq_city_name_province"),)


class Airport(Base):
    __tablename__ = "airports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    iata_code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    location: Mapped[object] = mapped_column(Geography("POINT", srid=4326), nullable=False)


class PoiCache(Base):
    __tablename__ = "poi_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    city_id: Mapped[int] = mapped_column(Integer, ForeignKey("cities.id"), nullable=False)
    found: Mapped[bool] = mapped_column(Boolean, nullable=False)
    distance_km: Mapped[Optional[float]] = mapped_column(Numeric(8, 3), nullable=True)
    count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    city: Mapped["City"] = relationship("City", back_populates="poi_caches")

    __table_args__ = (
        UniqueConstraint("query", "city_id", name="uq_poi_cache_query_city"),
        Index("ix_poi_cache_fetched_at", "fetched_at"),
    )


class WeatherNormals(Base):
    __tablename__ = "weather_normals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # city_id=NULL means "national average for Spain"
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cities.id"), nullable=True)
    avg_sunny_days_year: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    city: Mapped[Optional["City"]] = relationship("City", back_populates="weather_normals")


class RentPriceIndex(Base):
    __tablename__ = "rent_price_index"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cities.id"), nullable=True)
    # province fallback when city-level data is not available
    province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    price_per_sqm: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    city: Mapped[Optional["City"]] = relationship("City", back_populates="rent_prices")


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # "user1" or "user2" — derived from which env credential pair matched (no separate users table)
    user_id: Mapped[str] = mapped_column(String(10), nullable=False)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    parsed_criteria: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tolerance: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    status: Mapped[SearchRunStatus] = mapped_column(
        Enum(SearchRunStatus), nullable=False, default=SearchRunStatus.pending
    )
    compared_to_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("search_runs.id"), nullable=True
    )
    comparison_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    results: Mapped[list["SearchResult"]] = relationship("SearchResult", back_populates="run")
    compared_to: Mapped[Optional["SearchRun"]] = relationship("SearchRun", remote_side="SearchRun.id")


class SearchResult(Base):
    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("search_runs.id"), nullable=False)
    city_id: Mapped[int] = mapped_column(Integer, ForeignKey("cities.id"), nullable=False)
    overall_confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    # Per-criterion confidence + raw values; used by frontend for tooltips and
    # client-side confidence recompute when the tolerance slider moves.
    criteria_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False)

    run: Mapped["SearchRun"] = relationship("SearchRun", back_populates="results")
    city: Mapped["City"] = relationship("City", back_populates="search_results")

    __table_args__ = (UniqueConstraint("run_id", "city_id", name="uq_search_result_run_city"),)
