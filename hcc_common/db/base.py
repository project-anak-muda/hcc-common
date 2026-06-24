from __future__ import annotations

import datetime as dt

from sqlalchemy import MetaData
from sqlalchemy.types import DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

# Western Indonesian Time (WIB) — fixed UTC+7, no DST. Using a fixed offset
# keeps this dependency-free (no tzdata required in minimal containers).
JAKARTA_TZ = dt.timezone(dt.timedelta(hours=7), name="WIB")

def now_jakarta() -> dt.datetime:
    """Timezone-aware 'now' in Jakarta time (WIB, UTC+7).

    Canonical source of wall-clock timestamps across the project so every
    service records and displays the same local time.
    """
    return dt.datetime.now(JAKARTA_TZ)

def ts_column(**kwargs):
    """Timezone-aware timestamp column helper."""
    return mapped_column(DateTime(timezone=True), **kwargs)