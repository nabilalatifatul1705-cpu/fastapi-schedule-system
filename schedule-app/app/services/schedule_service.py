"""Scheduling Service: CRUD jadwal & ruangan, deteksi bentrok, observer, integrasi KRS."""
from collections import Counter
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Lecturer, Room, Schedule
from app.observers.subject import SCHEDULE_CHANGED, ScheduleSubject
from app.services import (
    CapacityError,
    ConflictError,
    InvalidScheduleError,
    NotFoundError,
)
from app.services.ai_rescheduler import AIRescheduler
from app.services.conflict_detector import (
    candidate_conflicts,
    check_capacity,
    detect_schedule_conflict,
    time_to_minutes,
    to_slot,
)
from app.services.krs_integration import KRSIntegration

SCHEDULE_FIELDS = (
    "course_code",
    "course_name",
    "semester",
    "day",
    "start_time",
    "end_time",
    "room_id",
    "lecturer_id",
    "enrolled_count",
)


class ScheduleService:
    def __init__(self, db: Session, subject: Optional[ScheduleSubject] = None) -> None:
        self.db = db
        self.subject = subject
        self.krs = KRSIntegration(db)

    # ============================================================ Ruangan
    def create_room(self, data: Mapping[str, Any]) -> Room:
        if self.db.scalar(select(Room).where(Room.code == data["code"])):
            raise ConflictError(f"Kode ruangan {data['code']} sudah dipakai")
        room = Room(**data)
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return room

    def list_rooms(self) -> List[Room]:
        return list(self.db.scalars(select(Room).order_by(Room.code)).all())

    def get_room(self, room_id: int) -> Room:
        room = self.db.get(Room, room_id)
        if room is None:
            raise NotFoundError(f"Ruangan {room_id} tidak ditemukan")
        return room

    def update_room(self, room_id: int, changes: Mapping[str, Any]) -> Room:
        room = self.get_room(room_id)
        new_code = changes.get("code")
        if new_code and new_code != room.code:
            if self.db.scalar(select(Room).where(Room.code == new_code)):
                raise ConflictError(f"Kode ruangan {new_code} sudah dipakai")
        new_capacity = changes.get("capacity")
        if new_capacity is not None:
            too_big = [s for s in room.schedules if not check_capacity(s.enrolled_count, new_capacity)]
            if too_big:
                raise CapacityError(
                    f"Kapasitas baru ({new_capacity}) lebih kecil dari jumlah mahasiswa pada "
                    f"jadwal {', '.join(s.course_code for s in too_big)}"
                )
        for key, value in changes.items():
            setattr(room, key, value)
        self.db.commit()
        self.db.refresh(room)
        return room

    def delete_room(self, room_id: int) -> None:
        room = self.get_room(room_id)
        if room.schedules:
            raise ConflictError("Ruangan masih dipakai oleh jadwal dan tidak dapat dihapus")
        self.db.delete(room)
        self.db.commit()

    # ============================================================== Dosen
    def create_lecturer(self, data: Mapping[str, Any]) -> Lecturer:
        if self.db.scalar(select(Lecturer).where(Lecturer.nip == data["nip"])):
            raise ConflictError(f"NIP {data['nip']} sudah terdaftar")
        lecturer = Lecturer(**data)
        self.db.add(lecturer)
        self.db.commit()
        self.db.refresh(lecturer)
        return lecturer

    def list_lecturers(self) -> List[Lecturer]:
        return list(self.db.scalars(select(Lecturer).order_by(Lecturer.name)).all())

    def get_lecturer(self, lecturer_id: int) -> Lecturer:
        lecturer = self.db.get(Lecturer, lecturer_id)
        if lecturer is None:
            raise NotFoundError(f"Dosen {lecturer_id} tidak ditemukan")
        return lecturer

    # ============================================================== Jadwal
    @staticmethod
    def serialize(schedule: Schedule) -> Dict[str, Any]:
        return {
            "id": schedule.id,
            "course_code": schedule.course_code,
            "course_name": schedule.course_name,
            "semester": schedule.semester,
            "day": schedule.day,
            "start_time": schedule.start_time.strftime("%H:%M"),
            "end_time": schedule.end_time.strftime("%H:%M"),
            "enrolled_count": schedule.enrolled_count,
            "room": {
                "id": schedule.room.id,
                "code": schedule.room.code,
                "name": schedule.room.name,
                "capacity": schedule.room.capacity,
            },
            "lecturer": {
                "id": schedule.lecturer.id,
                "nip": schedule.lecturer.nip,
                "name": schedule.lecturer.name,
                "email": schedule.lecturer.email,
            },
        }

    def get_schedule(self, schedule_id: int) -> Schedule:
        schedule = self.db.get(Schedule, schedule_id)
        if schedule is None:
            raise NotFoundError(f"Jadwal {schedule_id} tidak ditemukan")
        return schedule

    def list_schedules(
        self,
        day: Optional[str] = None,
        room_id: Optional[int] = None,
        lecturer_id: Optional[int] = None,
        semester: Optional[str] = None,
        course_code: Optional[str] = None,
    ) -> List[Schedule]:
        stmt = select(Schedule).order_by(Schedule.id)
        if day:
            stmt = stmt.where(Schedule.day == day)
        if room_id is not None:
            stmt = stmt.where(Schedule.room_id == room_id)
        if lecturer_id is not None:
            stmt = stmt.where(Schedule.lecturer_id == lecturer_id)
        if semester:
            stmt = stmt.where(Schedule.semester == semester)
        if course_code:
            stmt = stmt.where(Schedule.course_code == course_code)
        return list(self.db.scalars(stmt).all())

    def _slots(self, semester: str, exclude_id: Optional[int] = None):
        stmt = select(Schedule).where(Schedule.semester == semester)
        if exclude_id is not None:
            stmt = stmt.where(Schedule.id != exclude_id)
        return [to_slot(s) for s in self.db.scalars(stmt).all()]

    @staticmethod
    def _validate_capacity(enrolled: int, room: Room) -> None:
        if not check_capacity(enrolled, room.capacity):
            raise CapacityError(
                f"Jumlah mahasiswa ({enrolled}) melebihi kapasitas ruangan "
                f"{room.code} ({room.capacity})"
            )

    def _publish(
        self,
        action: str,
        schedule: Dict[str, Any],
        previous: Optional[Dict[str, Any]],
        students: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
        krs_invalidated: int,
        changed_fields: List[str],
    ) -> Optional[Dict[str, Any]]:
        if self.subject is None:
            return None
        return self.subject.notify(
            SCHEDULE_CHANGED,
            {
                "action": action,
                "schedule": schedule,
                "previous": previous,
                "affected_students": students,
                "conflicts": conflicts,
                "krs_invalidated": krs_invalidated,
                "changed_fields": changed_fields,
            },
        )

    # ------------------------------------------------------------ create
    def create_schedule(self, data: Mapping[str, Any], force: bool = False) -> Dict[str, Any]:
        room = self.get_room(data["room_id"])
        lecturer = self.get_lecturer(data["lecturer_id"])
        if time_to_minutes(data["end_time"]) <= time_to_minutes(data["start_time"]):
            raise InvalidScheduleError("Jam selesai harus lebih besar dari jam mulai")
        self._validate_capacity(data["enrolled_count"], room)

        conflicts = candidate_conflicts(dict(data), self._slots(data["semester"]))
        if conflicts and not force:
            raise ConflictError(
                "Jadwal bentrok dengan jadwal lain. Gunakan force=true untuk tetap menyimpan.",
                {"conflicts": conflicts},
            )

        schedule = Schedule(**{k: data[k] for k in SCHEDULE_FIELDS if k not in ("room_id", "lecturer_id")})
        schedule.room = room
        schedule.lecturer = lecturer
        self.db.add(schedule)
        self.db.flush()

        if conflicts:  # hitung ulang agar memuat id jadwal baru
            conflicts = candidate_conflicts(to_slot(schedule), self._slots(schedule.semester, schedule.id))
        invalidated = self.krs.invalidate_for_conflicts(
            conflicts, f"Jadwal {schedule.course_code} bentrok dengan jadwal lain"
        )
        self.db.commit()
        self.db.refresh(schedule)

        serialized = self.serialize(schedule)
        self._publish(
            "CREATED", serialized, None, self._students(schedule.id, invalidated),
            conflicts, len(invalidated), [],
        )
        return {
            "schedule": schedule,
            "conflicts": conflicts,
            "krs_invalidated": len(invalidated),
            "changed_fields": [],
        }

    # ------------------------------------------------------------ update
    def update_schedule(
        self, schedule_id: int, changes: Mapping[str, Any], force: bool = False
    ) -> Dict[str, Any]:
        schedule = self.get_schedule(schedule_id)
        before = self.serialize(schedule)

        merged = {name: getattr(schedule, name) for name in SCHEDULE_FIELDS}
        merged.update(changes)
        if time_to_minutes(merged["end_time"]) <= time_to_minutes(merged["start_time"]):
            raise InvalidScheduleError("Jam selesai harus lebih besar dari jam mulai")

        room = self.get_room(merged["room_id"])
        lecturer = self.get_lecturer(merged["lecturer_id"])
        self._validate_capacity(merged["enrolled_count"], room)

        candidate = {**merged, "id": schedule.id}
        conflicts = candidate_conflicts(candidate, self._slots(merged["semester"], schedule.id))
        if conflicts and not force:
            raise ConflictError(
                "Perubahan jadwal bentrok dengan jadwal lain. Gunakan force=true untuk tetap menyimpan.",
                {"conflicts": conflicts},
            )

        for name in SCHEDULE_FIELDS:
            if name not in ("room_id", "lecturer_id"):
                setattr(schedule, name, merged[name])
        schedule.room = room
        schedule.lecturer = lecturer
        self.db.flush()

        after = self.serialize(schedule)
        changed = self._changed_fields(before, after)

        invalidated: List[Dict[str, Any]] = []
        if changed:
            invalidated += self.krs.invalidate_for_schedule(
                schedule.id, f"Jadwal {schedule.course_code} berubah ({', '.join(changed)})"
            )
        invalidated += self.krs.invalidate_for_conflicts(
            conflicts, f"Jadwal {schedule.course_code} bentrok dengan jadwal lain"
        )
        invalidated_ids = {item["krs_id"] for item in invalidated}
        self.db.commit()
        self.db.refresh(schedule)

        self._publish(
            "UPDATED", after, before, self._students(schedule.id, invalidated),
            conflicts, len(invalidated_ids), changed,
        )
        return {
            "schedule": schedule,
            "conflicts": conflicts,
            "krs_invalidated": len(invalidated_ids),
            "changed_fields": changed,
        }

    @staticmethod
    def _changed_fields(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
        changed = [k for k in ("course_code", "day", "start_time", "end_time") if before[k] != after[k]]
        if before["room"]["id"] != after["room"]["id"]:
            changed.append("room")
        if before["lecturer"]["id"] != after["lecturer"]["id"]:
            changed.append("lecturer")
        return changed

    # ------------------------------------------------------------ delete
    def delete_schedule(self, schedule_id: int) -> Dict[str, Any]:
        schedule = self.get_schedule(schedule_id)
        serialized = self.serialize(schedule)
        students = self.krs.students_for_schedule(schedule_id)
        affected = self.krs.detach_schedule(
            schedule_id, f"Jadwal {schedule.course_code} dihapus/dibatalkan"
        )
        invalidated_ids = {item["krs_id"] for item in affected}
        for student in students:
            student["krs_invalidated"] = student["krs_id"] in invalidated_ids
            student["krs_status"] = "REVISION"

        self.db.delete(schedule)
        self.db.commit()

        self._publish("DELETED", serialized, None, students, [], len(invalidated_ids), [])
        return {"deleted": True, "schedule": serialized, "krs_invalidated": len(invalidated_ids)}

    def _students(self, schedule_id: int, invalidated: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Daftar mahasiswa pada jadwal (untuk notifikasi), ditandai bila KRS-nya di-invalidate."""
        ids = {item["krs_id"] for item in invalidated}
        students = self.krs.students_for_schedule(schedule_id)
        for student in students:
            student["krs_invalidated"] = student["krs_id"] in ids
        return students

    # ============================================================ Dashboard
    def conflict_dashboard(self, semester: Optional[str] = None) -> Dict[str, Any]:
        schedules = self.list_schedules(semester=semester)
        capacities = {s.room_id: s.room.capacity for s in schedules}
        raw = detect_schedule_conflict(schedules, rooms_capacity=capacities)
        index = {s.id: s for s in schedules}

        items = []
        for conflict in raw:
            items.append({
                **conflict,
                "schedules": [
                    self.serialize(index[i]) for i in conflict["schedule_ids"] if i in index
                ],
                "suggestion_endpoints": [
                    f"/api/schedules/{i}/suggestions" for i in conflict["schedule_ids"]
                ],
            })
        return {
            "total": len(items),
            "by_type": dict(Counter(c["type"] for c in raw)),
            "conflicts": items,
        }

    def suggest(self, schedule_id: int) -> List[Dict[str, str]]:
        return AIRescheduler(self.db).suggest(schedule_id)
