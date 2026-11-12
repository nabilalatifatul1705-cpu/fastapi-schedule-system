"""Publisher (ScheduleSubject), kontrak Observer, dan base class subscriber.

Notifikasi dikirim secara simulasi: dicatat lewat logger `schedule.notifications`
dan disimpan di `outbox` tiap observer (mudah diperiksa saat testing).
"""
import copy
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Sequence

logger = logging.getLogger("schedule.notifications")

SCHEDULE_CHANGED = "SCHEDULE_CHANGED"

ACTION_LABEL = {
    "CREATED": "Jadwal Baru",
    "UPDATED": "Perubahan Jadwal",
    "DELETED": "Pembatalan Jadwal",
}


@dataclass
class ScheduleEvent:
    """Event yang dikirim Publisher ke seluruh Observer."""

    event_type: str
    data: Dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Observer(ABC):
    """Kontrak Subscriber: cukup mengimplementasikan update(event)."""

    @abstractmethod
    def update(self, event: ScheduleEvent) -> None:
        ...


class ScheduleSubject:
    """Publisher: menyimpan daftar observer dan memberi tahu mereka saat ada event."""

    def __init__(self) -> None:
        self._observers: List[Observer] = []
        self._lock = threading.RLock()

    @property
    def observers(self) -> List[Observer]:
        with self._lock:
            return list(self._observers)

    def attach(self, observer: Observer) -> None:
        """Mendaftarkan observer (idempoten: tidak akan terdaftar dua kali)."""
        with self._lock:
            if observer not in self._observers:
                self._observers.append(observer)

    def detach(self, observer: Observer) -> None:
        """Melepas observer (aman dipanggil walau observer belum terdaftar)."""
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)

    def notify(self, event_type: str, schedule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Mengirim event ke semua observer.

        Kegagalan satu observer tidak boleh menghentikan observer lain,
        sehingga error ditangkap per observer dan dilaporkan di hasil.
        """
        event = ScheduleEvent(event_type=event_type, data=copy.deepcopy(schedule_data))
        delivered = 0
        failed: List[Dict[str, str]] = []
        for observer in self.observers:
            try:
                observer.update(event)
                delivered += 1
            except Exception as exc:  # noqa: BLE001 - isolasi kegagalan observer
                logger.exception("Observer %s gagal memproses event", type(observer).__name__)
                failed.append({"observer": type(observer).__name__, "error": str(exc)})
        return {"event_id": event.event_id, "delivered": delivered, "failed": failed}


def describe_schedule(schedule: Dict[str, Any]) -> str:
    room = schedule.get("room", {}).get("code", "-")
    return (
        f"{schedule['course_code']} - {schedule['course_name']} "
        f"({schedule['day']} {schedule['start_time']}-{schedule['end_time']}, ruang {room})"
    )


def build_change_summary(data: Dict[str, Any]) -> str:
    """Ringkasan perubahan dalam bahasa Indonesia untuk isi notifikasi."""
    action = data.get("action", "UPDATED")
    schedule = data["schedule"]
    previous = data.get("previous")
    if action == "CREATED":
        return f"Jadwal baru ditetapkan: {describe_schedule(schedule)}."
    if action == "DELETED":
        return f"Jadwal dibatalkan: {describe_schedule(schedule)}."
    if previous:
        return (
            f"Jadwal berubah dari {describe_schedule(previous)} "
            f"menjadi {describe_schedule(schedule)}."
        )
    return f"Jadwal diperbarui: {describe_schedule(schedule)}."


class BaseObserver(Observer):
    """Base class subscriber: filter event, kirim notifikasi simulasi, simpan outbox."""

    name = "BaseObserver"
    supported_events: Sequence[str] = (SCHEDULE_CHANGED,)

    def __init__(self, channels: Sequence[str] = ("email",)) -> None:
        self.channels = tuple(channels)
        self.outbox: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def update(self, event: ScheduleEvent) -> None:
        if event.event_type not in self.supported_events:
            return
        self.handle(event)

    @abstractmethod
    def handle(self, event: ScheduleEvent) -> None:
        ...

    def deliver(
        self, channel: str, recipient: str, subject: str, body: str, event: ScheduleEvent
    ) -> Dict[str, Any]:
        """Mengirim notifikasi (simulasi): dicatat di log dan outbox."""
        record = {
            "observer": self.name,
            "channel": channel,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "event_type": event.event_type,
            "event_id": event.event_id,
            "timestamp": event.timestamp,
        }
        with self._lock:
            self.outbox.append(record)
        logger.info("[%s][%s] to=%s | %s | %s", self.name, channel.upper(), recipient, subject, body)
        return record

    def clear(self) -> None:
        with self._lock:
            self.outbox.clear()
