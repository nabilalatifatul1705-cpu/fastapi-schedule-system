"""Integrasi dengan Modul KRS.

Modul KRS aslinya layanan terpisah; di sini disimulasikan lewat tabel
`krs_enrollments`. Aturan invalidasi:

- Saat jadwal berubah (hari/jam/ruangan/dosen/mata kuliah): semua KRS dengan
  status APPROVED atau SUBMITTED untuk jadwal itu dikembalikan ke REVISION.
- Saat terjadi bentrok antar dua jadwal: mahasiswa yang mengambil KEDUA mata
  kuliah tersebut dikembalikan ke REVISION (mereka tidak mungkin menghadiri keduanya).
- Saat jadwal dihapus: seluruh KRS terkait menjadi REVISION dan kehilangan referensi jadwal.
- Status DRAFT dibiarkan DRAFT (belum final), tetapi mahasiswanya tetap diberi notifikasi.
"""
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    KRS_APPROVED,
    KRS_REVISION,
    KRS_STATUSES,
    KRS_SUBMITTED,
    KRSEnrollment,
    Schedule,
)
from app.services import CapacityError, ConflictError, NotFoundError, ServiceError
from app.services.conflict_detector import LECTURER_CONFLICT, ROOM_CONFLICT, TIME_OVERLAP

INVALIDATABLE_STATUSES = (KRS_APPROVED, KRS_SUBMITTED)
PAIR_CONFLICT_TYPES = (ROOM_CONFLICT, LECTURER_CONFLICT, TIME_OVERLAP)


class KRSIntegration:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------- CRUD ringan
    def enroll(
        self, *, student_nim: str, student_name: str, student_email: str, schedule_id: int
    ) -> KRSEnrollment:
        schedule = self.db.get(Schedule, schedule_id)
        if schedule is None:
            raise NotFoundError(f"Jadwal {schedule_id} tidak ditemukan")

        duplicate = self.db.scalar(
            select(KRSEnrollment).where(
                KRSEnrollment.student_nim == student_nim,
                KRSEnrollment.course_code == schedule.course_code,
                KRSEnrollment.semester == schedule.semester,
            )
        )
        if duplicate is not None:
            raise ConflictError(
                f"Mahasiswa {student_nim} sudah mengambil {schedule.course_code} "
                f"pada semester {schedule.semester}"
            )
        if schedule.enrolled_count + 1 > schedule.room.capacity:
            raise CapacityError(
                f"Kapasitas ruangan {schedule.room.code} ({schedule.room.capacity}) sudah penuh"
            )

        row = KRSEnrollment(
            student_nim=student_nim,
            student_name=student_name,
            student_email=student_email,
            semester=schedule.semester,
            course_code=schedule.course_code,
            schedule_id=schedule.id,
        )
        schedule.enrolled_count += 1
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get(self, krs_id: int) -> KRSEnrollment:
        row = self.db.get(KRSEnrollment, krs_id)
        if row is None:
            raise NotFoundError(f"KRS {krs_id} tidak ditemukan")
        return row

    def list(
        self,
        nim: Optional[str] = None,
        status: Optional[str] = None,
        schedule_id: Optional[int] = None,
    ) -> List[KRSEnrollment]:
        stmt = select(KRSEnrollment).order_by(KRSEnrollment.id)
        if nim:
            stmt = stmt.where(KRSEnrollment.student_nim == nim)
        if status:
            stmt = stmt.where(KRSEnrollment.status == status)
        if schedule_id is not None:
            stmt = stmt.where(KRSEnrollment.schedule_id == schedule_id)
        return list(self.db.scalars(stmt).all())

    def update_status(self, krs_id: int, status: str) -> KRSEnrollment:
        if status not in KRS_STATUSES:
            raise ServiceError(f"Status KRS tidak valid: {status}")
        row = self.get(krs_id)
        row.status = status
        self.db.commit()
        self.db.refresh(row)
        return row

    # ------------------------------------------------------------- invalidasi
    def students_for_schedule(self, schedule_id: int) -> List[Dict[str, Any]]:
        rows = self.list(schedule_id=schedule_id)
        return [
            {
                "krs_id": r.id,
                "nim": r.student_nim,
                "name": r.student_name,
                "email": r.student_email,
                "krs_status": r.status,
            }
            for r in rows
        ]

    def _invalidate_rows(
        self, rows: Sequence[KRSEnrollment], reason: str, new_status: str = KRS_REVISION
    ) -> List[Dict[str, Any]]:
        changed: List[Dict[str, Any]] = []
        for row in rows:
            if row.status in INVALIDATABLE_STATUSES:
                previous = row.status
                row.status = new_status
                row.note = reason
                changed.append({
                    "krs_id": row.id,
                    "nim": row.student_nim,
                    "name": row.student_name,
                    "email": row.student_email,
                    "course_code": row.course_code,
                    "previous_status": previous,
                    "new_status": new_status,
                })
        if changed:
            self.db.flush()
        return changed

    def invalidate_for_schedule(self, schedule_id: int, reason: str) -> List[Dict[str, Any]]:
        """APPROVED/SUBMITTED -> REVISION untuk semua KRS pada jadwal ini."""
        return self._invalidate_rows(self.list(schedule_id=schedule_id), reason)

    def invalidate_for_conflicts(
        self, conflicts: Sequence[Dict[str, Any]], reason: str
    ) -> List[Dict[str, Any]]:
        """Invalidate KRS mahasiswa yang mengambil kedua jadwal dalam satu konflik."""
        changed: List[Dict[str, Any]] = []
        seen = set()
        for conflict in conflicts:
            if conflict.get("type") not in PAIR_CONFLICT_TYPES:
                continue
            ids = [i for i in conflict.get("schedule_ids", []) if i is not None]
            if len(set(ids)) < 2:
                continue
            rows = list(
                self.db.scalars(
                    select(KRSEnrollment).where(KRSEnrollment.schedule_id.in_(ids))
                ).all()
            )
            per_student: Dict[str, set] = defaultdict(set)
            for row in rows:
                per_student[row.student_nim].add(row.schedule_id)
            in_both = {nim for nim, sched in per_student.items() if len(sched) >= 2}
            targets = [row for row in rows if row.student_nim in in_both]
            for item in self._invalidate_rows(targets, reason):
                if item["krs_id"] not in seen:
                    seen.add(item["krs_id"])
                    changed.append(item)
        return changed

    def detach_schedule(self, schedule_id: int, reason: str) -> List[Dict[str, Any]]:
        """Dipakai saat jadwal dihapus: semua KRS terkait -> REVISION, tanpa referensi jadwal."""
        rows = self.list(schedule_id=schedule_id)
        affected: List[Dict[str, Any]] = []
        for row in rows:
            previous = row.status
            row.status = KRS_REVISION
            row.note = reason
            row.schedule_id = None
            affected.append({
                "krs_id": row.id,
                "nim": row.student_nim,
                "name": row.student_name,
                "email": row.student_email,
                "course_code": row.course_code,
                "previous_status": previous,
                "new_status": KRS_REVISION,
            })
        if affected:
            self.db.flush()
        return affected
