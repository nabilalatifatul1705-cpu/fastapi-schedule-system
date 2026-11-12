"""Subscriber untuk Admin Akademik."""
from typing import Sequence

from app.observers.subject import (
    ACTION_LABEL,
    BaseObserver,
    ScheduleEvent,
    build_change_summary,
)


class AcademicAdminObserver(BaseObserver):
    """Mengirim ringkasan operasional (konflik, KRS ter-invalidate) ke admin akademik."""

    name = "AcademicAdminObserver"

    def __init__(
        self, admin_email: str = "akademik@istn.ac.id", channels: Sequence[str] = ("email", "push")
    ) -> None:
        super().__init__(channels)
        self.admin_email = admin_email

    def handle(self, event: ScheduleEvent) -> None:
        data = event.data
        schedule = data["schedule"]
        action = data.get("action", "UPDATED")
        conflicts = data.get("conflicts", [])
        students = data.get("affected_students", [])
        invalidated = data.get("krs_invalidated", 0)

        subject = f"[Admin] {ACTION_LABEL.get(action, action)} {schedule['course_code']}"
        body = (
            f"{build_change_summary(data)} "
            f"Mahasiswa terdampak: {len(students)}. KRS di-invalidate: {invalidated}. "
            f"Konflik terdeteksi: {len(conflicts)}."
        )
        if conflicts:
            types = ", ".join(sorted({c['type'] for c in conflicts}))
            body += f" Jenis konflik: {types}. Buka dashboard konflik untuk saran jadwal alternatif."

        for channel in self.channels:
            self.deliver(channel, self.admin_email, subject, body, event)
