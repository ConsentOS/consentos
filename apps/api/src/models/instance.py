from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Instance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-deployment metadata for this ConsentOS instance.

    Holds a single row created on first boot. The ``id`` is a stable,
    anonymous UUID used as the deployment identifier in the telemetry
    heartbeat (``docs/telemetry.md``). It identifies the install, never
    a person, and is generated locally — operators never register with
    a server. ``last_telemetry_at`` records the most recent successful
    heartbeat for local audit.
    """

    __tablename__ = "instance"

    last_telemetry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
