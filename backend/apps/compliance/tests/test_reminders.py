"""Tests for the reminder/escalation models and the rate-limited reminder service.

These drive :mod:`apps.compliance.reminders` and the ``Reminder`` /
``Escalation`` models. Per the project's TDD workflow they are written
and observed failing before the implementation exists.

The reminder log and the escalation trail are both **append-only**: a
reminder attempt either records a new ``Reminder`` (sent) or a new
``Escalation`` (suppressed by the cooldown), and existing rows are never
mutated.
"""

import datetime

import pytest
import time_machine

from apps.compliance.models import Elevator, Escalation, Reminder
from apps.compliance.reminders import REMINDER_COOLDOWN_DAYS, attempt_reminder

pytestmark = pytest.mark.django_db


class TestReminderModels:
    """Tests for the :class:`Reminder` and :class:`Escalation` models."""

    def test_reminder_belongs_to_elevator(self, elevator: Elevator) -> None:
        """A Reminder is linked to its elevator via the ``reminders`` relation."""
        reminder = Reminder.objects.create(elevator=elevator, channel="email")
        assert reminder in elevator.reminders.all()
        assert reminder.status == Reminder.Status.SENT

    def test_escalation_belongs_to_elevator(self, elevator: Elevator) -> None:
        """An Escalation is linked to its elevator via the ``escalations`` relation."""
        escalation = Escalation.objects.create(elevator=elevator, reason="rate_limited")
        assert escalation in elevator.escalations.all()

    def test_reminder_str(self, elevator: Elevator) -> None:
        """A Reminder's string form names its elevator and channel."""
        reminder = Reminder.objects.create(elevator=elevator, channel="email")
        assert elevator.device_identifier in str(reminder)
        assert "email" in str(reminder)

    def test_escalation_str(self, elevator: Elevator) -> None:
        """An Escalation's string form names its elevator."""
        escalation = Escalation.objects.create(elevator=elevator, reason="rate_limited")
        assert elevator.device_identifier in str(escalation)


class TestAttemptReminder:
    """Tests for :func:`apps.compliance.reminders.attempt_reminder`."""

    @time_machine.travel(datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC))
    def test_first_reminder_is_sent_and_logged(self, elevator: Elevator) -> None:
        """The first reminder for an elevator is sent and appended to the log."""
        result = attempt_reminder(elevator, channel="email")
        assert result.sent is True
        assert result.reminder is not None
        assert result.escalation is None
        assert elevator.reminders.count() == 1
        assert elevator.escalations.count() == 0

    @time_machine.travel(datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC))
    def test_second_reminder_within_cooldown_is_suppressed(self, elevator: Elevator) -> None:
        """A second reminder inside the cooldown window is suppressed, not sent."""
        attempt_reminder(elevator, channel="email")
        result = attempt_reminder(elevator, channel="email")
        assert result.sent is False
        assert result.reminder is None
        assert result.escalation is not None
        # The log still holds exactly one sent reminder; the suppressed
        # attempt is recorded on the escalation trail instead.
        assert elevator.reminders.count() == 1
        assert elevator.escalations.count() == 1

    def test_reminder_allowed_again_after_cooldown(self, elevator: Elevator) -> None:
        """Once the cooldown elapses, a new reminder is sent again."""
        start = datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC)
        with time_machine.travel(start):
            attempt_reminder(elevator, channel="email")
        later = start + datetime.timedelta(days=REMINDER_COOLDOWN_DAYS, seconds=1)
        with time_machine.travel(later):
            result = attempt_reminder(elevator, channel="email")
        assert result.sent is True
        assert elevator.reminders.count() == 2
        assert elevator.escalations.count() == 0

    @time_machine.travel(datetime.datetime(2026, 7, 20, 12, 0, tzinfo=datetime.UTC))
    def test_next_allowed_at_reflects_cooldown(self, elevator: Elevator) -> None:
        """A sent reminder reports the next allowed time one cooldown ahead."""
        result = attempt_reminder(elevator, channel="email")
        assert result.reminder is not None
        expected = result.reminder.sent_at + datetime.timedelta(days=REMINDER_COOLDOWN_DAYS)
        assert result.next_allowed_at == expected
