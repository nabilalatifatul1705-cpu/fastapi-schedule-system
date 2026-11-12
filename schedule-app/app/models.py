"""Model ORM (SQLAlchemy 2.0 style, Mapped & mapped_column)."""
import datetime as dt
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Status KRS (disimulasikan di modul ini karena modul KRS adalah layanan terpisah).
KRS_DRAFT = "DRAFT"
KRS_SUBMITTED = "SUBMITTED"
KRS_APPROVED = "APPROVED"
KRS_REVISION = "REVISION"
KRS_STATUSES = (KRS_DRAFT, KRS_SUBMITTED, KRS_APPROVED, KRS_REVISION)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int] = mapped_column(Integer)
    building: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    schedules: Mapped[List["Schedule"]] = relationship(back_populates="room")


class Lecturer(Base):
    __tablename__ = "lecturers"

    id: Mapped[int] = mapped_column(primary_key=True)
    nip: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150))

    schedules: Mapped[List["Schedule"]] = relationship(back_populates="lecturer")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_code: Mapped[str] = mapped_column(String(20), index=True)
    course_name: Mapped[str] = mapped_column(String(150))
    semester: Mapped[str] = mapped_column(String(20), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    start_time: Mapped[dt.time] = mapped_column(Time)
    end_time: Mapped[dt.time] = mapped_column(Time)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    lecturer_id: Mapped[int] = mapped_column(ForeignKey("lecturers.id"), index=True)
    enrolled_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    room: Mapped["Room"] = relationship(back_populates="schedules", lazy="joined")
    lecturer: Mapped["Lecturer"] = relationship(back_populates="schedules", lazy="joined")


class KRSEnrollment(Base):
    """Satu baris = satu mata kuliah yang diambil seorang mahasiswa di KRS-nya."""

    __tablename__ = "krs_enrollments"
    __table_args__ = (
        UniqueConstraint(
            "student_nim", "course_code", "semester", name="uq_krs_student_course_semester"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_nim: Mapped[str] = mapped_column(String(20), index=True)
    student_name: Mapped[str] = mapped_column(String(100))
    student_email: Mapped[str] = mapped_column(String(150))
    semester: Mapped[str] = mapped_column(String(20))
    course_code: Mapped[str] = mapped_column(String(20))
    schedule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=KRS_DRAFT, index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
