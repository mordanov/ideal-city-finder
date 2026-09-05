"""Unit tests for criteria_parser — OpenAI calls are mocked, no real network."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.criteria_parser import (
    AirportProximityCriterion,
    PoiProximityCriterion,
    RentPriceCriterion,
    SunnyDaysCriterion,
    parse_criteria,
)

_EXAMPLE_QUERY = (
    "find cities in Spain where within a 20 km radius there is definitely a "
    "Conservatorio de Musica (Basico and Profesional levels), there are 2 or more "
    "private schools, there is an airport within 100 km, more sunny days than the "
    "Spain average, and average rental housing cost no more than 10 euros per square meter"
)

# The JSON the mocked OpenAI API would return for the example query
_EXPECTED_RESPONSE_JSON = json.dumps(
    {
        "criteria": [
            {
                "type": "poi_proximity",
                "poi_query": "Conservatorio de Musica",
                "radius_km": 20.0,
                "min_count": 1,
            },
            {
                "type": "poi_proximity",
                "poi_query": "private school",
                "radius_km": 20.0,
                "min_count": 2,
            },
            {
                "type": "airport_proximity",
                "radius_km": 100.0,
            },
            {
                "type": "sunny_days_above_average",
            },
            {
                "type": "rent_price_per_sqm",
                "comparison": "lte",
                "value": 10.0,
            },
        ]
    }
)


def _build_mock_client(response_json: str) -> MagicMock:
    """Construct a mock AsyncOpenAI client whose chat.completions.create returns response_json."""
    message = MagicMock()
    message.content = response_json

    choice = MagicMock()
    choice.message = message

    completion = MagicMock()
    completion.choices = [choice]

    mock_completions = MagicMock()
    mock_completions.create = AsyncMock(return_value=completion)

    mock_chat = MagicMock()
    mock_chat.completions = mock_completions

    mock_client_instance = MagicMock()
    mock_client_instance.chat = mock_chat

    mock_client_class = MagicMock(return_value=mock_client_instance)
    return mock_client_class


@pytest.mark.asyncio
async def test_parse_criteria_example_query():
    mock_client_class = _build_mock_client(_EXPECTED_RESPONSE_JSON)

    with patch("app.services.criteria_parser.AsyncOpenAI", mock_client_class):
        result = await parse_criteria(_EXAMPLE_QUERY, language="en")

    assert len(result) == 5

    # Criterion 1: Conservatorio poi_proximity, radius=20, min_count=1
    c1 = result[0]
    assert isinstance(c1, PoiProximityCriterion)
    assert "conservatorio" in c1.poi_query.lower()
    assert c1.radius_km == 20.0
    assert c1.min_count == 1

    # Criterion 2: private schools poi_proximity, radius=20, min_count=2
    c2 = result[1]
    assert isinstance(c2, PoiProximityCriterion)
    assert "private" in c2.poi_query.lower() or "school" in c2.poi_query.lower()
    assert c2.radius_km == 20.0
    assert c2.min_count == 2

    # Criterion 3: airport_proximity, radius=100
    c3 = result[2]
    assert isinstance(c3, AirportProximityCriterion)
    assert c3.radius_km == 100.0

    # Criterion 4: sunny_days_above_average
    c4 = result[3]
    assert isinstance(c4, SunnyDaysCriterion)

    # Criterion 5: rent_price_per_sqm lte 10
    c5 = result[4]
    assert isinstance(c5, RentPriceCriterion)
    assert c5.comparison == "lte"
    assert c5.value == 10.0


@pytest.mark.asyncio
async def test_parse_criteria_passes_text_to_openai():
    """Verify the user text is forwarded as-is to the OpenAI API."""
    mock_client_class = _build_mock_client(_EXPECTED_RESPONSE_JSON)

    with patch("app.services.criteria_parser.AsyncOpenAI", mock_client_class):
        await parse_criteria(_EXAMPLE_QUERY, language="ru")

    # The user content in the messages list should match the original text
    call_kwargs = mock_client_class.return_value.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
    user_messages = [m for m in messages if m["role"] == "user"]
    assert user_messages[0]["content"] == _EXAMPLE_QUERY
