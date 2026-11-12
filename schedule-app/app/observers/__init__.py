"""Observer Pattern untuk notifikasi perubahan jadwal."""
from app.config import settings
from app.observers.admin_observer import AcademicAdminObserver
from app.observers.lecturer_observer import LecturerObserver
from app.observers.student_observer import StudentObserver
from app.observers.subject import (
    SCHEDULE_CHANGED,
    BaseObserver,
    Observer,
    ScheduleEvent,
    ScheduleSubject,
)


def build_default_subject() -> ScheduleSubject:
    """Membuat ScheduleSubject dengan tiga subscriber bawaan."""
    subject = ScheduleSubject()
    subject.attach(StudentObserver())
    subject.attach(LecturerObserver())
    subject.attach(AcademicAdminObserver(admin_email=settings.admin_email))
    return subject


__all__ = [
    "SCHEDULE_CHANGED",
    "AcademicAdminObserver",
    "BaseObserver",
    "LecturerObserver",
    "Observer",
    "ScheduleEvent",
    "ScheduleSubject",
    "StudentObserver",
    "build_default_subject",
]
