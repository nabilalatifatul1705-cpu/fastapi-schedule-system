"""AI-Powered Rescheduling Assistant (Constraint Satisfaction Problem).

Pendekatan
----------
Masalah dimodelkan sebagai CSP:

* Variabel : (hari, jam_mulai, ruangan) untuk jadwal yang bermasalah.
* Domain   : hari kerja x jam mulai tiap 30 menit x seluruh ruangan.
* Hard constraint (kandidat yang melanggar dibuang):
    1. kapasitas ruangan >= jumlah mahasiswa enrolled,
    2. ruangan bebas (tidak beririsan dengan jadwal lain di ruangan tsb),
    3. dosen bebas (tidak mengajar kelas lain pada jam tsb),
    4. selesai sebelum jam akhir operasional dan tidak menabrak sholat Jumat,
    5. bukan slot asli yang sedang bermasalah.
* Soft constraint (menjadi skor penalti, makin kecil makin baik):
    prioritas pagi > siang > sore, hindari jam istirahat, minim pergeseran
    hari/jam dari jadwal asal, ruangan sama bila memungkinkan, ruangan tidak
    terlalu longgar, dan tidak bentrok dengan mata kuliah lain milik mahasiswa
    yang terdaftar (dari data KRS).

Solver bersifat deterministik (pencarian penuh atas domain kecil + ranking),
sehingga hasilnya dapat dijelaskan dan diuji. Setiap saran disertai `reason`.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DAYS, settings
from app.models import KRSEnrollment, Room, Schedule
from app.services import NotFoundError
from app.services.conflict_detector import (
    DAY_INDEX,
    Slot,
    intervals_overlap,
    minutes_to_str,
    time_to_minutes,
    to_slot,
)


@dataclass(frozen=True)
class RoomInfo:
    id: int
    code: str
    capacity: int


def _room_info(room: Any) -> RoomInfo:
    if isinstance(room, RoomInfo):
        return room
    if isinstance(room, Mapping):
        return RoomInfo(id=room["id"], code=room["code"], capacity=room["capacity"])
    return RoomInfo(id=room.id, code=room.code, capacity=room.capacity)


def _time_band(start: int) -> str:
    if start < 12 * 60:
        return "pagi"
    if start < 15 * 60:
        return "siang"
    return "sore"


_BAND_PENALTY = {"pagi": 0.0, "siang": 10.0, "sore": 30.0}


def _candidate_starts(duration: int, day_start: int, day_end: int, step: int):
    start = day_start
    while start + duration <= day_end:
        yield start
        start += step


def _score(
    day: str, start: int, end: int, room: RoomInfo, enrolled: int, target: Slot, clash: int
) -> float:
    penalty = _BAND_PENALTY[_time_band(start)]
    if start < 8 * 60:
        penalty += 5.0  # terlalu pagi
    if intervals_overlap(start, end, settings.lunch_start, settings.lunch_end):
        penalty += 8.0  # menabrak jam istirahat
    penalty += 3.0 * abs(DAY_INDEX[day] - DAY_INDEX.get(target.day, DAY_INDEX[day]))
    penalty += min(abs(start - target.start) / 30.0, 10.0)
    if room.id != target.room_id:
        penalty += 2.0
    penalty += (room.capacity - enrolled) / max(room.capacity, 1) * 5.0
    penalty += clash * 15.0
    return penalty


def _build_reason(
    day: str,
    start: int,
    end: int,
    room: RoomInfo,
    enrolled: int,
    target: Slot,
    clash: int,
    student_count: int,
    lecturer_label: str,
) -> str:
    parts = [
        f"Slot {_time_band(start)} ({day} {minutes_to_str(start)}-{minutes_to_str(end)})",
        f"ruangan {room.code} berkapasitas {room.capacity} untuk {enrolled} mahasiswa",
        f"{lecturer_label} bebas pada jam tersebut",
        "tidak ada bentrok ruangan",
    ]
    if day == target.day:
        parts.append("hari sama dengan jadwal awal sehingga gangguan minimal")
    else:
        shift = abs(DAY_INDEX[day] - DAY_INDEX.get(target.day, DAY_INDEX[day]))
        parts.append(f"bergeser {shift} hari dari jadwal awal")
    if student_count:
        if clash == 0:
            parts.append(f"tidak bentrok dengan KRS {student_count} mahasiswa terdaftar")
        else:
            parts.append(f"{clash} dari {student_count} mahasiswa berpotensi bentrok dengan mata kuliah lain")
    return "; ".join(parts) + "."


def suggest_alternatives(
    target: Any,
    existing: Sequence[Any],
    rooms: Sequence[Any],
    student_busy: Optional[Mapping[str, Sequence[Any]]] = None,
    limit: Optional[int] = None,
    days: Optional[Sequence[str]] = None,
    lecturer_label: str = "dosen",
) -> List[Dict[str, str]]:
    """Merekomendasikan jadwal alternatif bebas bentrok.

    Args:
        target: jadwal bermasalah (dict/ORM/Slot).
        existing: seluruh jadwal lain (target otomatis diabaikan bila id sama).
        rooms: daftar ruangan (dict/ORM) dengan id, code, capacity.
        student_busy: (opsional) peta NIM -> jadwal lain milik mahasiswa itu.
        limit: jumlah saran (default 3).
        days: hari yang boleh dipakai (default settings.scheduling_days).

    Returns:
        List dict `{hari, jam_mulai, jam_selesai, ruangan, reason}` terurut dari terbaik.
    """
    limit = limit or settings.max_suggestions
    days = tuple(days or settings.scheduling_days)
    tgt = to_slot(target)
    duration = tgt.end - tgt.start
    enrolled = tgt.enrolled

    others = [
        s
        for s in (to_slot(e) for e in existing)
        if (tgt.id is None or s.id != tgt.id) and s.semester == tgt.semester
    ]
    by_day: Dict[str, List[Slot]] = {}
    for slot in others:
        by_day.setdefault(slot.day, []).append(slot)

    eligible = [r for r in (_room_info(x) for x in rooms) if r.capacity >= enrolled]

    busy_by_student: Dict[str, Dict[str, List[Slot]]] = {}
    for nim, slots in (student_busy or {}).items():
        per_day: Dict[str, List[Slot]] = {}
        for item in slots:
            slot = to_slot(item)
            per_day.setdefault(slot.day, []).append(slot)
        busy_by_student[nim] = per_day
    student_count = len(busy_by_student)

    candidates: List[Tuple[float, int, int, str, Dict[str, Any]]] = []
    for day in days:
        day_slots = by_day.get(day, [])
        lecturer_slots = [
            s for s in day_slots if tgt.lecturer_id is not None and s.lecturer_id == tgt.lecturer_id
        ]
        for start in _candidate_starts(
            duration, settings.day_start_minute, settings.day_end_minute, settings.slot_step_minutes
        ):
            end = start + duration
            if day == "Jumat" and intervals_overlap(
                start, end, settings.friday_prayer_start, settings.friday_prayer_end
            ):
                continue  # hard constraint: sholat Jumat
            if any(intervals_overlap(start, end, s.start, s.end) for s in lecturer_slots):
                continue  # hard constraint: dosen bentrok
            busy_rooms = {
                s.room_id for s in day_slots if intervals_overlap(start, end, s.start, s.end)
            }
            clash = sum(
                1
                for per_day in busy_by_student.values()
                if any(intervals_overlap(start, end, s.start, s.end) for s in per_day.get(day, []))
            )
            for room in eligible:
                if room.id in busy_rooms:
                    continue  # hard constraint: ruangan terpakai
                if day == tgt.day and start == tgt.start and room.id == tgt.room_id:
                    continue  # slot asli yang bermasalah
                score = _score(day, start, end, room, enrolled, tgt, clash)
                suggestion = {
                    "hari": day,
                    "jam_mulai": minutes_to_str(start),
                    "jam_selesai": minutes_to_str(end),
                    "ruangan": room.code,
                    "reason": _build_reason(
                        day, start, end, room, enrolled, tgt, clash, student_count, lecturer_label
                    ),
                }
                candidates.append((round(score, 6), DAY_INDEX[day], start, room.code, suggestion))

    candidates.sort(key=lambda item: item[:4])

    chosen: List[Dict[str, str]] = []
    used_slots = set()
    for _, _, _, _, suggestion in candidates:  # utamakan variasi (hari, jam)
        key = (suggestion["hari"], suggestion["jam_mulai"])
        if key in used_slots:
            continue
        used_slots.add(key)
        chosen.append(suggestion)
        if len(chosen) >= limit:
            return chosen
    for _, _, _, _, suggestion in candidates:  # isi sisa dengan opsi ruangan lain
        if suggestion not in chosen:
            chosen.append(suggestion)
            if len(chosen) >= limit:
                break
    return chosen


class AIRescheduler:
    """Pembungkus yang memuat data dari database lalu memanggil solver CSP."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def suggest(self, schedule_id: int, limit: Optional[int] = None) -> List[Dict[str, str]]:
        schedule = self.db.get(Schedule, schedule_id)
        if schedule is None:
            raise NotFoundError(f"Jadwal {schedule_id} tidak ditemukan")

        same_semester = self.db.scalars(
            select(Schedule).where(Schedule.semester == schedule.semester)
        ).all()
        rooms = self.db.scalars(select(Room).order_by(Room.code)).all()

        nims = set(
            self.db.scalars(
                select(KRSEnrollment.student_nim).where(KRSEnrollment.schedule_id == schedule_id)
            ).all()
        )
        busy: Dict[str, List[Slot]] = {nim: [] for nim in nims}
        if nims:
            stmt = (
                select(KRSEnrollment.student_nim, Schedule)
                .join(Schedule, Schedule.id == KRSEnrollment.schedule_id)
                .where(
                    KRSEnrollment.student_nim.in_(nims),
                    KRSEnrollment.schedule_id != schedule_id,
                    Schedule.semester == schedule.semester,
                )
            )
            for nim, other in self.db.execute(stmt).all():
                busy[nim].append(to_slot(other))

        return suggest_alternatives(
            target=schedule,
            existing=same_semester,
            rooms=rooms,
            student_busy=busy,
            limit=limit,
            lecturer_label=f"dosen {schedule.lecturer.name}",
        )
