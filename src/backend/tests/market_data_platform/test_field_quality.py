"""Shared typed field-quality policy contracts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.services.market_data.field_quality import (
    FIELD_QUALITY_POLICY_VERSION,
    FieldQualityValueError,
    is_usable_field_value,
    normalize_date_field_value,
    normalize_datetime_field_value,
    normalize_numeric_field_value,
    normalize_provider_fields,
)


@pytest.mark.parametrize(
    "value",
    [
        "--",
        "N/A",
        "  ",
        True,
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
        "not-a-number",
    ],
)
def test_known_numeric_fields_reject_placeholders_and_non_numeric_values(value: object) -> None:
    """A known price field must not treat text sentinels as a usable observation."""
    with pytest.raises(FieldQualityValueError) as rejected:
        normalize_numeric_field_value(value, field_name="close")

    assert rejected.value.field_name == "close"
    assert not is_usable_field_value("close", value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" 10.50 ", "10.50"),
        (Decimal("12.34"), "12.34"),
        (10, 10),
        (10.25, 10.25),
    ],
)
def test_known_numeric_fields_have_one_json_safe_canonical_form(
    value: object,
    expected: object,
) -> None:
    """Provider and offline snapshots share an exact-safe numeric representation."""
    normalized = normalize_numeric_field_value(value, field_name="close")

    assert normalized == expected
    assert is_usable_field_value("close", normalized)


def test_provider_field_normalization_quarantines_only_invalid_known_numeric_values() -> None:
    """Raw source evidence can retain text elsewhere while quote metrics become unavailable."""
    normalized = normalize_provider_fields(
        {
            "close": "--",
            "volume": Decimal("1000.00"),
            "source_label": "N/A",
        }
    )

    assert FIELD_QUALITY_POLICY_VERSION == "typed-field-quality-v2"
    assert normalized == {"close": None, "volume": "1000.00", "source_label": "N/A"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" 2027-12-31 ", "2027-12-31"),
        (date(2027, 12, 31), "2027-12-31"),
    ],
)
def test_known_date_fields_have_one_json_safe_canonical_form(
    value: object,
    expected: str,
) -> None:
    """Declared date fields reject text sentinels instead of becoming generic strings."""
    assert normalize_date_field_value(value, field_name="maturity_date") == expected
    assert is_usable_field_value("maturity_date", value)


@pytest.mark.parametrize("value", ("--", "N/A", "  ", "not-a-date"))
def test_known_date_fields_reject_placeholders_and_invalid_dates(value: object) -> None:
    """The date side of the typed policy is as strict as numeric observations."""
    with pytest.raises(FieldQualityValueError) as rejected:
        normalize_date_field_value(value, field_name="maturity_date")

    assert rejected.value.field_name == "maturity_date"
    assert not is_usable_field_value("maturity_date", value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" 2027-12-31T09:15:00+08:00 ", "2027-12-31T01:15:00+00:00"),
        (datetime(2027, 12, 31, 1, 15, tzinfo=timezone.utc), "2027-12-31T01:15:00+00:00"),
    ],
)
def test_known_datetime_fields_have_one_utc_json_safe_canonical_form(
    value: object,
    expected: str,
) -> None:
    """A quote timestamp must not become an unchecked generic string."""
    assert normalize_datetime_field_value(value, field_name="update_time") == expected
    assert is_usable_field_value("update_time", value)


@pytest.mark.parametrize(
    "value",
    ("--", "N/A", "  ", "not-a-time", "2027-12-31", "2027-12-31T09:15:00"),
)
def test_known_datetime_fields_reject_unavailable_or_ambiguous_values(value: object) -> None:
    """Date-only and timezone-free quote times cannot satisfy a typed field."""
    with pytest.raises(FieldQualityValueError) as rejected:
        normalize_datetime_field_value(value, field_name="update_time")

    assert rejected.value.field_name == "update_time"
    assert not is_usable_field_value("update_time", value)
