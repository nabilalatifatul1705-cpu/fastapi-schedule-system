"""Subscriber untuk mahasiswa yang terdampak perubahan jadwal."""
from typing import Sequence

from app.observers.subject import (
    ACTION_LABEL,
    BaseObserver,
    ScheduleEvent,
    build_change_summary,
)


class StudentObserver(BaseObserver):
    """Mengirim email/push simulasi ke setiap mahasiswa terdampak."""

    name = "StudentObserver"

    def __init__(self, channels: Sequence[str] = ("email", "push")) -> None:
        super().__init__(channels)

    def handle(self, event: ScheduleEvent) -> None:
        data = event.data
        schedule = data["schedule"]
        action = data.get("action", "UPDATED")
        subject = f"[Jadwal] {ACTION_LABEL.get(action, action)} {schedule['course_code']}"
        summary = build_change_summary(data)

        for student in data.get("affected_students", []):
            body = f"Halo {student['name']} ({student['nim']}). {summary}"
            if student.get("krs_invalidated"):
                body += (
                    f" KRS Anda untuk {schedule['course_code']} dikembalikan ke status "
                    f"REVISION. Mohon sesuaikan ulang KRS Anda."
                )
            for channel in self.channels:
                self.deliver(channel, student["email"], subject, body, event)
