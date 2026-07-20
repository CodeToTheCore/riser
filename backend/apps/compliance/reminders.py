"""Rate-limited reminder service for elevator compliance.

This module ports the "send_reminder + rate limit" pattern onto Riser:
a reminder about an elevator's inspection can be dispatched at most once
per :data:`REMINDER_COOLDOWN_DAYS`. Every sent reminder is appended to
the :class:`~apps.compliance.models.Reminder` log; every attempt that is
suppressed by the cooldown is appended to the
:class:`~apps.compliance.models.Escalation` trail. Neither log is ever
mutated, so the two tables together form a complete, tamper-evident
history of reminder activity.
"""

import dataclasses
import datetime

from django.utils import timezone

from apps.compliance.models import Elevator, Escalation, Reminder

#: Minimum number of days between successive reminders sent for the same
#: elevator. A reminder requested within this window of the most recent
#: sent reminder is suppressed and recorded as an escalation instead.
REMINDER_COOLDOWN_DAYS = 7


@dataclasses.dataclass(frozen=True)
class ReminderResult:
    """The outcome of an :func:`attempt_reminder` call.

    Attributes:
        sent: ``True`` if a reminder was dispatched, ``False`` if the
            attempt was suppressed by the cooldown.
        reminder: The created :class:`~apps.compliance.models.Reminder`
            when ``sent`` is ``True``; otherwise ``None``.
        escalation: The created
            :class:`~apps.compliance.models.Escalation` when ``sent`` is
            ``False``; otherwise ``None``.
        next_allowed_at: The earliest time a subsequent reminder for this
            elevator would be permitted.
        detail: A short human-readable description of the outcome.
    """

    sent: bool
    reminder: Reminder | None
    escalation: Escalation | None
    next_allowed_at: datetime.datetime
    detail: str


def attempt_reminder(elevator: Elevator, channel: str = Reminder.Channel.EMAIL) -> ReminderResult:
    """Attempt to send a reminder for an elevator, honoring the cooldown.

    If the most recent sent reminder for ``elevator`` falls within
    :data:`REMINDER_COOLDOWN_DAYS` of now, the attempt is suppressed: an
    :class:`~apps.compliance.models.Escalation` is recorded and no
    reminder is sent. Otherwise a new
    :class:`~apps.compliance.models.Reminder` is appended to the log.

    Args:
        elevator: The elevator to remind about.
        channel: The delivery channel; one of
            :class:`~apps.compliance.models.Reminder.Channel`.

    Returns:
        A :class:`ReminderResult` describing what happened.
    """
    now = timezone.now()
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
            sent=False,
            reminder=None,
            escalation=escalation,
            next_allowed_at=next_allowed_at,
            detail="Reminder rate-limited; escalation recorded.",
        )

    reminder = Reminder.objects.create(elevator=elevator, channel=channel)
    return ReminderResult(
        sent=True,
        reminder=reminder,
        escalation=None,
        next_allowed_at=reminder.sent_at + cooldown,
        detail="Reminder sent.",
    )
