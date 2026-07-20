"""Tests for the compliance app's DRF API: buildings, elevators, and the ledger."""

import datetime

import pytest
import time_machine
from dateutil.relativedelta import relativedelta
from rest_framework import status
from rest_framework.test import APIClient

from apps.compliance.models import Building, Elevator

pytestmark = pytest.mark.django_db


class TestBuildingAPI:
    """CRUD tests for ``/api/buildings/``."""

    def test_list_buildings(self, api_client: APIClient, building: Building) -> None:
        """GET /api/buildings/ returns all buildings."""
        response = api_client.get("/api/buildings/")
        assert response.status_code == status.HTTP_200_OK
        names = [b["name"] for b in response.data]
        assert building.name in names

    def test_create_building(self, api_client: APIClient) -> None:
        """POST /api/buildings/ creates a new building."""
        payload = {"name": "20 Riser Ave", "address": "20 Riser Ave, New York, NY"}
        response = api_client.post("/api/buildings/", payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Building.objects.filter(name="20 Riser Ave").exists()

    def test_retrieve_building(self, api_client: APIClient, building: Building) -> None:
        """GET /api/buildings/<id>/ returns the requested building."""
        response = api_client.get(f"/api/buildings/{building.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == building.name

    def test_update_building(self, api_client: APIClient, building: Building) -> None:
        """PATCH /api/buildings/<id>/ updates the building."""
        response = api_client.patch(
            f"/api/buildings/{building.pk}/", {"name": "Renamed"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        building.refresh_from_db()
        assert building.name == "Renamed"

    def test_delete_building(self, api_client: APIClient, building: Building) -> None:
        """DELETE /api/buildings/<id>/ removes the building."""
        response = api_client.delete(f"/api/buildings/{building.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Building.objects.filter(pk=building.pk).exists()


class TestElevatorAPI:
    """CRUD tests for ``/api/elevators/``."""

    def test_list_elevators(self, api_client: APIClient, elevator: Elevator) -> None:
        """GET /api/elevators/ returns all elevators."""
        response = api_client.get("/api/elevators/")
        assert response.status_code == status.HTTP_200_OK
        ids = [e["id"] for e in response.data]
        assert elevator.pk in ids

    def test_filter_elevators_by_building(
        self, api_client: APIClient, building: Building, elevator: Elevator
    ) -> None:
        """GET /api/elevators/?building=<id> returns only that building's elevators."""
        other_building = Building.objects.create(name="Other", address="Other Ave")
        Elevator.objects.create(
            building=other_building,
            device_identifier="EL-OTHER",
            inspection_type="CAT1",
            last_inspection_date=datetime.date(2026, 1, 1),
        )
        response = api_client.get(f"/api/elevators/?building={building.pk}")
        assert response.status_code == status.HTTP_200_OK
        ids = [e["id"] for e in response.data]
        assert ids == [elevator.pk]

    def test_create_elevator(self, api_client: APIClient, building: Building) -> None:
        """POST /api/elevators/ creates a new elevator."""
        payload = {
            "building": building.pk,
            "device_identifier": "EL-999",
            "inspection_type": "CAT5",
            "last_inspection_date": "2025-06-01",
        }
        response = api_client.post("/api/elevators/", payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert Elevator.objects.filter(device_identifier="EL-999").exists()

    def test_retrieve_elevator(self, api_client: APIClient, elevator: Elevator) -> None:
        """GET /api/elevators/<id>/ returns the requested elevator."""
        response = api_client.get(f"/api/elevators/{elevator.pk}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["device_identifier"] == elevator.device_identifier

    def test_update_elevator(self, api_client: APIClient, elevator: Elevator) -> None:
        """PATCH /api/elevators/<id>/ updates the elevator's last inspection date."""
        response = api_client.patch(
            f"/api/elevators/{elevator.pk}/",
            {"last_inspection_date": "2026-05-01"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        elevator.refresh_from_db()
        assert elevator.last_inspection_date == datetime.date(2026, 5, 1)

    def test_delete_elevator(self, api_client: APIClient, elevator: Elevator) -> None:
        """DELETE /api/elevators/<id>/ removes the elevator."""
        response = api_client.delete(f"/api/elevators/{elevator.pk}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Elevator.objects.filter(pk=elevator.pk).exists()


class TestLedgerAPI:
    """Tests for the P0 ``/api/ledger/`` risk-triage endpoint."""

    def test_ledger_is_read_only(self, api_client: APIClient) -> None:
        """POST /api/ledger/ is not allowed; the ledger is a derived, read-only view."""
        response = api_client.post("/api/ledger/", {}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    @time_machine.travel(datetime.date(2026, 6, 1))
    def test_ledger_includes_computed_fields(
        self, api_client: APIClient, building: Building
    ) -> None:
        """Each ledger row includes building_name, computed due_date, and computed status."""
        last_inspection = (
            datetime.date(2026, 6, 1) - relativedelta(years=1) + datetime.timedelta(days=10)
        )
        Elevator.objects.create(
            building=building,
            device_identifier="EL-100",
            inspection_type="CAT1",
            last_inspection_date=last_inspection,
        )
        response = api_client.get("/api/ledger/")
        assert response.status_code == status.HTTP_200_OK
        row = next(r for r in response.data if r["device_identifier"] == "EL-100")
        assert row["building_name"] == building.name
        assert row["due_date"] == "2026-06-11"
        assert row["status"] == "Warning"

    @time_machine.travel(datetime.date(2026, 6, 1))
    def test_ledger_sort_order_delinquent_warning_compliant(
        self, api_client: APIClient, building: Building
    ) -> None:
        """Ledger rows are sorted Delinquent > Warning > Compliant, then due_date ascending."""
        today = datetime.date(2026, 6, 1)

        def make(device_identifier: str, due_date: datetime.date) -> Elevator:
            last_inspection = due_date - relativedelta(years=1)
            return Elevator.objects.create(
                building=building,
                device_identifier=device_identifier,
                inspection_type="CAT1",
                last_inspection_date=last_inspection,
            )

        # Intentionally created out of expected final order.
        compliant = make("COMPLIANT-1", today + datetime.timedelta(days=100))
        warning_later = make("WARNING-LATER", today + datetime.timedelta(days=20))
        delinquent_less_overdue = make("DELINQUENT-LESS", today - datetime.timedelta(days=10))
        warning_sooner = make("WARNING-SOONER", today + datetime.timedelta(days=5))
        delinquent_more_overdue = make("DELINQUENT-MORE", today - datetime.timedelta(days=50))

        response = api_client.get("/api/ledger/")
        assert response.status_code == status.HTTP_200_OK

        device_ids = [row["device_identifier"] for row in response.data]
        expected_order = [
            delinquent_more_overdue.device_identifier,
            delinquent_less_overdue.device_identifier,
            warning_sooner.device_identifier,
            warning_later.device_identifier,
            compliant.device_identifier,
        ]
        assert device_ids == expected_order

        statuses = [row["status"] for row in response.data]
        assert statuses == ["Delinquent", "Delinquent", "Warning", "Warning", "Compliant"]


class TestRemindAPI:
    """Tests for ``POST /api/elevators/<id>/remind/``."""

    @time_machine.travel(datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC))
    def test_remind_sends_and_logs(self, api_client: APIClient, at_risk_elevator: Elevator) -> None:
        """POST remind on an at-risk elevator sends a reminder (201) and logs it."""
        response = api_client.post(
            f"/api/elevators/{at_risk_elevator.pk}/remind/", {}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["sent"] is True
        assert at_risk_elevator.reminders.count() == 1

    @time_machine.travel(datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC))
    def test_remind_within_cooldown_is_rate_limited(
        self, api_client: APIClient, at_risk_elevator: Elevator
    ) -> None:
        """A second remind inside the cooldown returns 429 and logs an escalation."""
        url = f"/api/elevators/{at_risk_elevator.pk}/remind/"
        api_client.post(url, {}, format="json")
        response = api_client.post(url, {}, format="json")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.data["sent"] is False
        assert "next_allowed_at" in response.data
        assert at_risk_elevator.reminders.count() == 1
        assert at_risk_elevator.escalations.count() == 1

    @time_machine.travel(datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC))
    def test_remind_compliant_elevator_returns_422(
        self, api_client: APIClient, elevator: Elevator
    ) -> None:
        """Reminding a compliant elevator returns 422 and logs nothing."""
        response = api_client.post(f"/api/elevators/{elevator.pk}/remind/", {}, format="json")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.data["sent"] is False
        assert elevator.reminders.count() == 0
        assert elevator.escalations.count() == 0

    @time_machine.travel(datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC))
    def test_remind_rejects_unknown_channel(
        self, api_client: APIClient, at_risk_elevator: Elevator
    ) -> None:
        """An unrecognized channel is rejected with 400 and sends nothing."""
        response = api_client.post(
            f"/api/elevators/{at_risk_elevator.pk}/remind/",
            {"channel": "carrier-pigeon"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert at_risk_elevator.reminders.count() == 0

    def test_remind_unknown_elevator_returns_404(self, api_client: APIClient) -> None:
        """Reminding a nonexistent elevator returns 404."""
        response = api_client.post("/api/elevators/999999/remind/", {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
