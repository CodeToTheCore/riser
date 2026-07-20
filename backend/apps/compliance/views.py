"""DRF views for the compliance app."""

from collections.abc import Sequence
from typing import Any

from django.db.models import QuerySet
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.compliance.models import Building, Elevator, Reminder
from apps.compliance.reminders import attempt_reminder
from apps.compliance.serializers import (
    BuildingSerializer,
    ElevatorSerializer,
    EscalationSerializer,
    LedgerEntrySerializer,
    ReminderSerializer,
)
from apps.compliance.services import Status, calculate_due_date, calculate_status

#: Sort priority for each status, most urgent first. Used as the primary
#: sort key for the ledger endpoint.
_STATUS_RANK = {
    Status.DELINQUENT: 0,
    Status.WARNING: 1,
    Status.COMPLIANT: 2,
}


class BuildingViewSet(viewsets.ModelViewSet[Building]):
    """CRUD API for :class:`Building` records."""

    queryset = Building.objects.all()
    serializer_class = BuildingSerializer


class ElevatorViewSet(viewsets.ModelViewSet[Elevator]):
    """CRUD API for :class:`Elevator` records.

    Supports filtering the list endpoint by building via the
    ``?building=<id>`` query parameter.
    """

    serializer_class = ElevatorSerializer

    def get_queryset(self) -> QuerySet[Elevator]:
        """Return elevators, optionally filtered by the ``building`` query parameter.

        Returns:
            All elevators, or only those belonging to the building whose
            id is given in ``?building=<id>`` if that parameter is present.
        """
        queryset = Elevator.objects.select_related("building").all()
        building_id = self.request.query_params.get("building")
        if building_id is not None:
            queryset = queryset.filter(building_id=building_id)
        return queryset

    @action(detail=True, methods=["post"])
    def remind(self, request: Request, pk: str | None = None) -> Response:
        """Send a rate-limited compliance reminder for a single elevator.

        Accepts an optional ``channel`` in the request body (one of
        ``"email"`` or ``"sms"``, defaulting to ``"email"``). Delegates
        to :func:`apps.compliance.reminders.attempt_reminder`, which
        suppresses reminders inside the cooldown window.

        Args:
            request: The incoming DRF request; may carry ``channel``.
            pk: The primary key of the elevator, from the URL.

        Returns:
            ``201 Created`` with the logged reminder when one is sent,
            ``429 Too Many Requests`` with the recorded escalation when the
            attempt is rate-limited, or ``400 Bad Request`` if ``channel``
            is not a recognized value.
        """
        elevator = self.get_object()
        channel = request.data.get("channel", Reminder.Channel.EMAIL)
        if channel not in Reminder.Channel.values:
            valid = ", ".join(Reminder.Channel.values)
            return Response(
                {"channel": [f"Unrecognized channel {channel!r}; expected one of: {valid}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = attempt_reminder(elevator, channel=channel)
        body = {
            "sent": result.sent,
            "detail": result.detail,
            "next_allowed_at": result.next_allowed_at.isoformat(),
            "reminder": (
                ReminderSerializer(result.reminder).data if result.reminder is not None else None
            ),
            "escalation": (
                EscalationSerializer(result.escalation).data
                if result.escalation is not None
                else None
            ),
        }
        response_status = (
            status.HTTP_201_CREATED if result.sent else status.HTTP_429_TOO_MANY_REQUESTS
        )
        return Response(body, status=response_status)


class LedgerListView(generics.ListAPIView[Elevator]):
    """The P0 risk-triage ledger: every elevator, ranked by urgency.

    Read-only. Rows are sorted with the most urgent status first
    (Delinquent > Warning > Compliant), and within each status tier by
    ascending computed due date.

    The ordering depends on ``due_date`` and ``status``, which are
    computed rather than stored, so it cannot be expressed as a
    ``QuerySet.order_by(...)`` clause. Sorting is therefore done in
    Python within :meth:`list`, rather than via ``get_queryset``, so
    that this view's queryset-typed methods keep their normal DRF
    signatures.
    """

    queryset = Elevator.objects.select_related("building").all()
    serializer_class = LedgerEntrySerializer

    def _sorted_elevators(self) -> Sequence[Elevator]:
        """Return all elevators sorted by urgency then due date.

        Returns:
            Elevators ordered by status rank (Delinquent, then Warning,
            then Compliant) and, within each tier, by ascending due date.
        """
        elevators = list(self.filter_queryset(self.get_queryset()))

        def sort_key(elevator: Elevator) -> tuple[int, str]:
            due_date = calculate_due_date(elevator.inspection_type, elevator.last_inspection_date)
            rank = _STATUS_RANK[calculate_status(due_date)]
            return (rank, due_date.isoformat())

        return sorted(elevators, key=sort_key)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Return the ranked ledger as a plain (unpaginated) JSON list.

        Args:
            request: The incoming DRF request.
            *args: Unused positional arguments from the URL dispatcher.
            **kwargs: Unused keyword arguments from the URL dispatcher.

        Returns:
            A ``Response`` wrapping the serialized, urgency-sorted ledger.
        """
        serializer = self.get_serializer(self._sorted_elevators(), many=True)
        return Response(serializer.data)
