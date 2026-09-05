"""
Parse free-form user text into structured search criteria via OpenAI Structured Outputs.

Backend is responsible only for parsing; criterion type identifiers (e.g. "poi_proximity")
remain fixed English enum values in the JSON API — they are never translated here.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Union

from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, Field

from app.config import settings


# ---------------------------------------------------------------------------
# Criterion models
# ---------------------------------------------------------------------------


class PoiProximityCriterion(BaseModel):
    type: Literal["poi_proximity"]
    poi_query: str
    radius_km: float
    min_count: int = 1


class AirportProximityCriterion(BaseModel):
    type: Literal["airport_proximity"]
    radius_km: float


class SunnyDaysCriterion(BaseModel):
    type: Literal["sunny_days_above_average"]


class RentPriceCriterion(BaseModel):
    type: Literal["rent_price_per_sqm"]
    comparison: Literal["lt", "lte", "gt", "gte"]
    value: float


class UnsupportedCriterion(BaseModel):
    type: Literal["unsupported"]
    original_text: str


AnyCriterion = Annotated[
    Union[
        PoiProximityCriterion,
        AirportProximityCriterion,
        SunnyDaysCriterion,
        RentPriceCriterion,
        UnsupportedCriterion,
    ],
    Field(discriminator="type"),
]

ParsedCriteria = list[AnyCriterion]


class CriteriaResponse(BaseModel):
    criteria: list[AnyCriterion]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are a search criteria extractor for a Spanish city finder application.

Rules:
- The search country is ALWAYS Spain. Never suggest or imply any other country.
- Extract each criterion from the user's text into one of these types:
    - poi_proximity: a place of interest within a given radius (provide poi_query, radius_km, min_count)
    - airport_proximity: an airport within a given radius (provide radius_km)
    - sunny_days_above_average: the city has more sunny days than the Spain national average (no parameters)
    - rent_price_per_sqm: a rental price constraint (provide comparison ["lt","lte","gt","gte"] and value in €/m²)
- If a criterion in the user's text does not fit any of those types, return it as type="unsupported" with the original_text field.
- Extract numeric values (km, euros) LITERALLY from the text — do not guess, round, or infer.
- Accept input in English or Russian and parse criteria correctly regardless of language.
""".strip()


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


async def parse_criteria(user_text: str, language: str = "en") -> ParsedCriteria:
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    schema = to_strict_json_schema(CriteriaResponse)

    response = await client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "criteria_response",
                "strict": True,
                "schema": schema,
            },
        },
    )

    raw_json = response.choices[0].message.content
    data = json.loads(raw_json)
    parsed = CriteriaResponse.model_validate(data)
    return parsed.criteria
