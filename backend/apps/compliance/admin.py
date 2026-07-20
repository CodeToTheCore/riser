"""Django admin registrations for the compliance app."""

from django.contrib import admin

from apps.compliance.models import Building, Elevator, Escalation, Reminder


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for :class:`Building`.

    ``ModelAdmin`` is not subscriptable at runtime in this Django
    version, so the ``type-arg`` mypy check is suppressed here rather
    than parameterizing the base class.
    """

    list_display = ["name", "address", "created_at", "updated_at"]
    search_fields = ["name", "address"]


@admin.register(Elevator)
class ElevatorAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for :class:`Elevator`."""

    list_display = [
        "device_identifier",
        "building",
        "inspection_type",
        "last_inspection_date",
        "created_at",
        "updated_at",
    ]
    list_filter = ["inspection_type", "building"]
    search_fields = ["device_identifier"]


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for :class:`Reminder` (read-only audit log)."""

    list_display = ["elevator", "channel", "status", "sent_at"]
    list_filter = ["channel", "status"]
    readonly_fields = ["elevator", "channel", "status", "sent_at"]


@admin.register(Escalation)
class EscalationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for :class:`Escalation` (read-only audit trail)."""

    list_display = ["elevator", "reason", "created_at"]
    readonly_fields = ["elevator", "reason", "created_at"]
