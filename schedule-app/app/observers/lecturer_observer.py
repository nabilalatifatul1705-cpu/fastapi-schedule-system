"""Subscriber untuk dosen pengampu."""
from typing import Sequence

from app.observers.subject import (
    ACTION_LABEL,
    BaseObserver,
    ScheduleEvent,
    build_change_summary,
)


class LecturerObserver(BaseObserver):
    """Memberi tahu dosen pengampu (dan dosen lama bila dosen diganti)."""

    name = "LecturerObserver"

    def __init__(self, channels: Sequence[str] = ("email",)) -> None:
        super().__init__(channels)

    def handle(self, event: ScheduleEvent) -> None:
        data = event.data
        schedule = data["schedule"]
        previous = data.get("previous")
        action = data.get("action", "UPDATED")
        subject = f"[Jadwal] {ACTION_LABEL.get(action, action)} {schedule['course_code']}"
        summary = build_change_summary(data)

        recipients = {schedule["lecturer"]["email"]: schedule["lecturer"]["name"]}
        if previous and previous.get("lecturer"):
            old = previous["lecturer"]
            recipients.setdefault(old["email"], old["name"])

        for email, name in recipients.items():
            body = f"Yth. {name}. {summary}"
            if email != schedule["lecturer"]["email"]:
                body += " Anda tidak lagi menjadi pengampu jadwal ini."
            for channel in self.channels:
                self.deliver(channel, email, subject, body, event)
