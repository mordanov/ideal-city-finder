"""
Seed reference data: Spanish municipalities (cities) and AENA airports.

Usage:
    python -m app.scripts.seed_reference_data --all
    python -m app.scripts.seed_reference_data --cities
    python -m app.scripts.seed_reference_data --airports
"""

import asyncio
import csv
import sys
from pathlib import Path

import typer
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session_factory
from app.models import Airport, City

DATA_DIR = Path(__file__).parent.parent / "data"
MUNICIPIOS_CSV = DATA_DIR / "municipios_es.csv"

# Complete list of Spanish commercial AENA airports.
# Source: AENA network — static data, essentially never changes.
SPANISH_AIRPORTS = [
    {"name": "Adolfo Suárez Madrid-Barajas", "iata_code": "MAD", "lat": 40.4936, "lon": -3.5668},
    {"name": "Barcelona-El Prat Josep Tarradellas", "iata_code": "BCN", "lat": 41.2971, "lon": 2.0785},
    {"name": "Málaga-Costa del Sol", "iata_code": "AGP", "lat": 36.6749, "lon": -4.4991},
    {"name": "Palma de Mallorca", "iata_code": "PMI", "lat": 39.5517, "lon": 2.7388},
    {"name": "Alicante-Elche Miguel Hernández", "iata_code": "ALC", "lat": 38.2822, "lon": -0.5582},
    {"name": "Valencia", "iata_code": "VLC", "lat": 39.4893, "lon": -0.4816},
    {"name": "Sevilla", "iata_code": "SVQ", "lat": 37.4180, "lon": -5.8931},
    {"name": "Bilbao", "iata_code": "BIO", "lat": 43.3011, "lon": -2.9106},
    {"name": "Gran Canaria", "iata_code": "LPA", "lat": 27.9319, "lon": -15.3866},
    {"name": "Tenerife Sur", "iata_code": "TFS", "lat": 28.0445, "lon": -16.5725},
    {"name": "Tenerife Norte-Ciudad de La Laguna", "iata_code": "TFN", "lat": 28.4827, "lon": -16.3415},
    {"name": "Lanzarote-César Manrique", "iata_code": "ACE", "lat": 28.9455, "lon": -13.6052},
    {"name": "Fuerteventura", "iata_code": "FUE", "lat": 28.4527, "lon": -13.8638},
    {"name": "Ibiza", "iata_code": "IBZ", "lat": 38.8729, "lon": 1.3731},
    {"name": "Menorca", "iata_code": "MAH", "lat": 39.8626, "lon": 4.2186},
    {"name": "Santiago de Compostela", "iata_code": "SCQ", "lat": 42.8963, "lon": -8.4151},
    {"name": "Asturias", "iata_code": "OVD", "lat": 43.5636, "lon": -6.0346},
    {"name": "Santander", "iata_code": "SDR", "lat": 43.4271, "lon": -3.8200},
    {"name": "San Sebastián", "iata_code": "EAS", "lat": 43.3565, "lon": -1.7906},
    {"name": "Pamplona", "iata_code": "PNA", "lat": 42.7700, "lon": -1.6463},
    {"name": "Zaragoza", "iata_code": "ZAZ", "lat": 41.6662, "lon": -1.0415},
    {"name": "Girona-Costa Brava", "iata_code": "GRO", "lat": 41.9010, "lon": 2.7605},
    {"name": "Reus", "iata_code": "REU", "lat": 41.1474, "lon": 1.1672},
    {"name": "Vigo", "iata_code": "VGO", "lat": 42.2318, "lon": -8.6268},
    {"name": "Murcia-Región de Murcia Internacional", "iata_code": "RMU", "lat": 37.8030, "lon": -1.1253},
    {"name": "Granada-Federico García Lorca", "iata_code": "GRX", "lat": 37.1887, "lon": -3.7775},
    {"name": "Almería", "iata_code": "LEI", "lat": 36.8439, "lon": -2.3701},
    {"name": "Jerez de la Frontera", "iata_code": "XRY", "lat": 36.7446, "lon": -6.0601},
    {"name": "La Palma", "iata_code": "SPC", "lat": 28.6265, "lon": -17.7556},
    {"name": "El Hierro", "iata_code": "VDE", "lat": 27.8148, "lon": -17.8871},
    {"name": "La Gomera", "iata_code": "GMZ", "lat": 28.0296, "lon": -17.2147},
    {"name": "Melilla", "iata_code": "MLN", "lat": 35.2799, "lon": -2.9563},
    {"name": "Ceuta – Helipuerto", "iata_code": "JCU", "lat": 35.8899, "lon": -5.3269},
    {"name": "Murcia-San Javier (cierra 2024)", "iata_code": "MJV", "lat": 37.7750, "lon": -0.8124},
    {"name": "Vitoria", "iata_code": "VIT", "lat": 42.8828, "lon": -2.7245},
    {"name": "Valladolid", "iata_code": "VLL", "lat": 41.7061, "lon": -4.8519},
    {"name": "Salamanca", "iata_code": "SLM", "lat": 40.9521, "lon": -5.5019},
    {"name": "León", "iata_code": "LEN", "lat": 42.5890, "lon": -5.6556},
    {"name": "Burgos", "iata_code": "RGS", "lat": 42.3576, "lon": -3.6208},
    {"name": "Badajoz", "iata_code": "BJZ", "lat": 38.8913, "lon": -6.8213},
    {"name": "Corvera (Murcia Internacional)", "iata_code": "RMU", "lat": 37.8030, "lon": -1.1253},
    {"name": "Huesca-Pirineos", "iata_code": "HSK", "lat": 42.0761, "lon": -0.3166},
    {"name": "Lleida-Alguaire", "iata_code": "ILD", "lat": 41.7282, "lon": 0.5352},
    {"name": "Castellón-Costa Azahar", "iata_code": "CDT", "lat": 40.2139, "lon": 0.0731},
    {"name": "Algeciras-Helipuerto", "iata_code": "AEI", "lat": 36.1335, "lon": -5.4428},
    {"name": "Ibiza (alternative code)", "iata_code": "IBZ", "lat": 38.8729, "lon": 1.3731},
]

# Deduplicate by iata_code (keep first occurrence)
_seen: set[str] = set()
_deduped: list[dict] = []
for _ap in SPANISH_AIRPORTS:
    if _ap["iata_code"] not in _seen:
        _seen.add(_ap["iata_code"])
        _deduped.append(_ap)
SPANISH_AIRPORTS = _deduped


app = typer.Typer(help="Seed reference data into the ideal_city database.")


async def _seed_cities() -> int:
    if not MUNICIPIOS_CSV.exists():
        typer.echo(f"CSV not found: {MUNICIPIOS_CSV}", err=True)
        raise SystemExit(1)

    rows = []
    with MUNICIPIOS_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = float(row["lat"])
            lon = float(row["lon"])
            point = from_shape(Point(lon, lat), srid=4326)
            rows.append(
                {
                    "name": row["name"].strip(),
                    "province": row["province"].strip(),
                    "population": int(row["population"]) if row["population"] else None,
                    "location": point,
                    "source": "INE",
                }
            )

    async with async_session_factory() as session:
        stmt = (
            pg_insert(City)
            .values(rows)
            .on_conflict_do_update(
                constraint="uq_city_name_province",
                set_={
                    "population": pg_insert(City).excluded.population,
                    "location": pg_insert(City).excluded.location,
                    "source": pg_insert(City).excluded.source,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()

    typer.echo(f"Upserted {len(rows)} cities.")
    return len(rows)


async def _seed_airports() -> int:
    rows = [
        {
            "name": ap["name"],
            "iata_code": ap["iata_code"],
            "location": from_shape(Point(ap["lon"], ap["lat"]), srid=4326),
        }
        for ap in SPANISH_AIRPORTS
    ]

    async with async_session_factory() as session:
        stmt = (
            pg_insert(Airport)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["iata_code"],
                set_={
                    "name": pg_insert(Airport).excluded.name,
                    "location": pg_insert(Airport).excluded.location,
                },
            )
        )
        await session.execute(stmt)
        await session.commit()

    typer.echo(f"Upserted {len(rows)} airports.")
    return len(rows)


@app.command()
def seed(
    all: bool = typer.Option(False, "--all", help="Seed cities and airports."),
    cities: bool = typer.Option(False, "--cities", help="Seed cities only."),
    airports: bool = typer.Option(False, "--airports", help="Seed airports only."),
) -> None:
    if not any([all, cities, airports]):
        typer.echo("Specify at least one of --all, --cities, --airports.", err=True)
        raise typer.Exit(1)

    if all or cities:
        asyncio.run(_seed_cities())
    if all or airports:
        asyncio.run(_seed_airports())


if __name__ == "__main__":
    app()
