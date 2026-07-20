"""Shared pytest fixtures for the compliance app's test suite."""

import datetime

import pytest
from rest_framework.test import APIClient

from apps.compliance.models import Building, Elevator


@pytest.fixture
def api_client() -> APIClient:
    """Return a DRF :class:`APIClient` for exercising the API in tests."""
    return APIClient()


@pytest.fixture
def building(db: None) -> Building:
    """Create and return a persisted :class:`Building`."""
    return Building.objects.create(
        name="10 Riser Plaza",
        address="10 Riser Plaza, New York, NY 10001",
    )


@pytest.fixture
def elevator(db: None, building: Building) -> Elevator:
    """Create and return a persisted :class:`Elevator` belonging to ``building``.

    Its CAT1 last inspection is dated 2026-01-01, so its next inspection
    is due 2027-01-01 — comfortably **Compliant** at the mid-2026 dates the
    reminder tests freeze the clock to.
    """
    return Elevator.objects.create(
        building=building,
        device_identifier="EL-001",
        inspection_type="CAT1",
        last_inspection_date=datetime.date(2026, 1, 1),
    )


@pytest.fixture
def at_risk_elevator(db: None, building: Building) -> Elevator:
    """Create and return a persisted, **Delinquent** :class:`Elevator`.

    Its CAT1 last inspection is dated 2025-01-01, so its next inspection
    was due 2026-01-01 — already overdue at the mid-2026 dates the reminder
    tests freeze the clock to, making it a valid reminder target.
    """
    return Elevator.objects.create(
        building=building,
        device_identifier="EL-RISK",
        inspection_type="CAT1",
        last_inspection_date=datetime.date(2025, 1, 1),
    )
