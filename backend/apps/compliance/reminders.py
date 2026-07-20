"""Rate-limited reminder service for elevator compliance.

This module ports the "send_reminder + rate limit" pattern onto Riser:
a reminder about an elevator's inspection is sent only when the elevator
is actually at risk (Warning or Delinquent) and at most once per
:data:`REMINDER_COOLDOWN_DAYS`. Every sent reminder is appended to the
:class:`~apps.compliance.models.Reminder` log; every attempt suppressed
by the cooldown is appended to the
:class:`~apps.compliance.models.Escalation` trail. A reminder attempted
against a Compliant elevator is a no-op that logs nothing. None of the
logs are ever mutated, so together they form a complete, tamper-evident
history of reminder activity.
"""

import dataclasses
import datetime
import enum

from django.utils import timezone

from apps.compliance.models import Elevator, Escalation, Reminder
from apps.compliance.services import Status, calculate_due_date, calculate_status

#: Minimum number of days between successive reminders sent for the same
#: elevator. A reminder requested within this window of the most recent
#: sent reminder is suppressed and recorded as an escalation instead.
REMINDER_COOLDOWN_DAYS = 7


class ReminderOutcome(enum.Enum):
    """The disposition of an :func:`attempt_reminder` call."""

    #: A reminder was dispatched and appended to the log.
    SENT = "sent"
    #: The elevator was at risk but a reminder was sent too recently, so
    #: this attempt was suppressed and recorded as an escalation.
    RATE_LIMITED = "rate_limited"
    #: The elevator is Compliant, so no reminder was warranted; nothing
    #: was logged.
    NOT_AT_RISK = "not_at_risk"


@dataclasses.dataclass(frozen=True)
class ReminderResult:
    """The outcome of an :func:`attempt_reminder` call.

    Attributes:
        outcome: Which :class:`ReminderOutcome` occurred.
        reminder: The created :class:`~apps.compliance.models.Reminder`
            when a reminder was sent; otherwise ``None``.
        escalation: The created
            :class:`~apps.compliance.models.Escalation` when the attempt
            was rate-limited; otherwise ``None``.
        next_allowed_at: The earliest time a subsequent reminder for this
            elevator would be permitted, or ``None`` when the cooldown is
            not in play (i.e. the elevator is not at risk).
        detail: A short human-readable description of the outcome.
    """

    outcome: ReminderOutcome
    reminder: Reminder | None
    escalation: Escalation | None
    next_allowed_at: datetime.datetime | None
    detail: str

    @property
    def sent(self) -> bool:
        """Return whether a reminder was actually dispatched."""
        return self.outcome is ReminderOutcome.SENT


def attempt_reminder(elevator: Elevator, channel: str = Reminder.Channel.EMAIL) -> ReminderResult:
    """Attempt to send a reminder for an elevator, honoring risk and cooldown.

    A reminder is sent only when the elevator's computed compliance status
    is not Compliant (i.e. Warning or Delinquent). If the elevator is
    Compliant, nothing is logged. Otherwise, if the most recent sent
    reminder falls within :data:`REMINDER_COOLDOWN_DAYS` of now, the
    attempt is suppressed and an
    :class:`~apps.compliance.models.Escalation` is recorded; if not, a new
    :class:`~apps.compliance.models.Reminder` is appended to the log.

    Args:
        elevator: The elevator to remind about.
        channel: The delivery channel; one of
            :class:`~apps.compliance.models.Reminder.Channel`.

    Returns:
        A :class:`ReminderResult` describing what happened.
    """
    now = timezone.now()
    due_date = calculate_due_date(elevator.inspection_type, elevator.last_inspection_date)
    if calculate_status(due_date, now.date()) is Status.COMPLIANT:
        return ReminderResult(
            outcome=ReminderOutcome.NOT_AT_RISK,
            reminder=None,
            escalation=None,
            next_allowed_at=None,
            detail=f"Elevator is compliant (due {due_date.isoformat()}); no reminder needed.",
        )

    cooldown = datetime.timedelta(days=REMINDER_COOLDOWN_DAYS)
    last_sent = elevator.reminders.filter(status=Reminder.Status.SENT).order_by("-sent_at").first()

    if last_sent is not None and last_sent.sent_at > now - cooldown:
        next_allowed_at = last_sent.sent_at + cooldown
        reason = (
            f"Reminder suppressed: within {REMINDER_COOLDOWN_DAYS}-day cooldown "
            f"(last sent {last_sent.sent_at.isoformat()})."
        )
        escalation = Escalation.objects.create(elevator=elevator, reason=reason)
        return ReminderResult(
            outcome=ReminderOutcome.RATE_LIMITED,
            reminder=None,
            escalation=escalation,
            next_allowed_at=next_allowed_at,
            detail="Reminder rate-limited; escalation recorded.",
        )

    reminder = Reminder.objects.create(elevator=elevator, channel=channel)
    return ReminderResult(
        outcome=ReminderOutcome.SENT,
        reminder=reminder,
        escalation=None,
        next_allowed_at=reminder.sent_at + cooldown,
        detail="Reminder sent.",
    )
