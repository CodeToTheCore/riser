"""Models for the compliance app: Building and Elevator.

Due dates and compliance statuses are intentionally not stored on
:class:`Elevator` — they are always computed on read via
:mod:`apps.compliance.services` so that editing ``last_inspection_date``
is reflected instantly with no risk of stale cached values.
"""

from django.db import models


class Building(models.Model):
    """A commercial property containing one or more elevators."""

    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata for Building."""

        ordering = ["name"]

    def __str__(self) -> str:
        """Return the building's name."""
        return self.name


class InspectionType(models.TextChoices):
    """NYC DOB elevator inspection categories tracked by Riser."""

    CAT1 = "CAT1", "Category 1 (Annual)"
    CAT5 = "CAT5", "Category 5 (Five-Year)"


class Elevator(models.Model):
    """A single elevator device belonging to a Building.

    Tracks the device's identifier, which statutory inspection category
    applies to it, and the date it was last inspected. The next due date
    and current compliance status are derived, not stored — see
    :mod:`apps.compliance.services`.
    """

    building = models.ForeignKey(Building, related_name="elevators", on_delete=models.CASCADE)
    device_identifier = models.CharField(max_length=100)
    inspection_type = models.CharField(max_length=4, choices=InspectionType.choices)
    last_inspection_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata for Elevator."""

        ordering = ["device_identifier"]

    def __str__(self) -> str:
        """Return a human-readable identifier including the device ID and building."""
        return f"{self.device_identifier} ({self.building.name})"


class Reminder(models.Model):
    """An append-only record of a compliance reminder sent for an elevator.

    Reminders are never mutated after creation: each row is a permanent
    audit-trail entry stating that, at ``sent_at``, a reminder about this
    elevator's upcoming or overdue inspection was dispatched on
    ``channel``. Rate limiting (see :mod:`apps.compliance.reminders`)
    reads this log to decide whether a fresh reminder is allowed.
    """

    class Channel(models.TextChoices):
        """The delivery channel a reminder was sent over."""

        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        """Delivery status of a reminder. Only sent reminders are logged."""

        SENT = "sent", "Sent"

    elevator = models.ForeignKey(Elevator, related_name="reminders", on_delete=models.CASCADE)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.EMAIL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SENT)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Model metadata for Reminder."""

        ordering = ["-sent_at"]

    def __str__(self) -> str:
        """Return a human-readable summary of the reminder."""
        return (
            f"Reminder for {self.elevator.device_identifier} "
            f"via {self.channel} at {self.sent_at:%Y-%m-%d %H:%M}"
        )


class Escalation(models.Model):
    """An append-only audit entry recording a suppressed reminder attempt.

    When a reminder is requested for an elevator that is still inside its
    cooldown window, no reminder is sent; instead an ``Escalation`` row is
    written explaining why. This trail is the state store backing the
    reminder rate limit and, like :class:`Reminder`, is never overwritten.
    """

    elevator = models.ForeignKey(Elevator, related_name="escalations", on_delete=models.CASCADE)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Model metadata for Escalation."""

        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return a human-readable summary of the escalation."""
        return (
            f"Escalation for {self.elevator.device_identifier} at {self.created_at:%Y-%m-%d %H:%M}"
        )
