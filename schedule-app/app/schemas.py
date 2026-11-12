"""Skema Pydantic v2 untuk request/response API."""
import datetime as dt
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

DayName = Literal["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
KRSStatus = Literal["DRAFT", "SUBMITTED", "APPROVED", "REVISION"]
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# ----------------------------------------------------------------- Ruangan
class RoomBase(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    capacity: int = Field(gt=0)
    building: Optional[str] = Field(default=None, max_length=100)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    capacity: Optional[int] = Field(default=None, gt=0)
    building: Optional[str] = Field(default=None, max_length=100)


class RoomRead(RoomBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ------------------------------------------------------------------- Dosen
class LecturerBase(BaseModel):
    nip: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=150)


class LecturerCreate(LecturerBase):
    pass


class LecturerRead(LecturerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ------------------------------------------------------------------ Jadwal
class ScheduleBase(BaseModel):
    course_code: str = Field(min_length=1, max_length=20)
    course_name: str = Field(min_length=1, max_length=150)
    semester: str = Field(default="2026-1", min_length=1, max_length=20)
    day: DayName
    start_time: dt.time
    end_time: dt.time
    room_id: int
    lecturer_id: int
    enrolled_count: int = Field(default=0, ge=0)


class ScheduleCreate(ScheduleBase):
    @model_validator(mode="after")
    def _check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time harus lebih besar dari start_time")
        return self


class ScheduleUpdate(BaseModel):
    course_code: Optional[str] = Field(default=None, min_length=1, max_length=20)
    course_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    semester: Optional[str] = Field(default=None, min_length=1, max_length=20)
    day: Optional[DayName] = None
    start_time: Optional[dt.time] = None
    end_time: Optional[dt.time] = None
    room_id: Optional[int] = None
    lecturer_id: Optional[int] = None
    enrolled_count: Optional[int] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_times(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time harus lebih besar dari start_time")
        return self


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_code: str
    course_name: str
    semester: str
    day: str
    start_time: dt.time
    end_time: dt.time
    enrolled_count: int
    room: RoomRead
    lecturer: LecturerRead

    @field_serializer("start_time", "end_time")
    def _fmt_time(self, value: dt.time) -> str:
        return value.strftime("%H:%M")


class ScheduleMutationResult(BaseModel):
    """Hasil create/update jadwal."""

    schedule: ScheduleRead
    conflicts: List[Dict[str, Any]] = []
    krs_invalidated: int = 0
    changed_fields: List[str] = []


# --------------------------------------------------------- Konflik & saran
class ConflictDashboard(BaseModel):
    total: int
    by_type: Dict[str, int]
    conflicts: List[Dict[str, Any]]


class SuggestionRead(BaseModel):
    hari: str
    jam_mulai: str
    jam_selesai: str
    ruangan: str
    reason: str


# --------------------------------------------------------------------- KRS
class KRSCreate(BaseModel):
    student_nim: str = Field(min_length=1, max_length=20)
    student_name: str = Field(min_length=1, max_length=100)
    student_email: str = Field(pattern=EMAIL_PATTERN, max_length=150)
    schedule_id: int


class KRSStatusUpdate(BaseModel):
    status: KRSStatus


class KRSRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_nim: str
    student_name: str
    student_email: str
    semester: str
    course_code: str
    schedule_id: Optional[int]
    status: str
    note: Optional[str]
