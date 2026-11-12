"""Endpoint REST untuk jadwal, ruangan, dosen, konflik, saran AI, KRS, dan notifikasi."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.observers import ScheduleSubject, build_default_subject
from app.observers.subject import BaseObserver
from app.schemas import (
    ConflictDashboard,
    KRSCreate,
    KRSRead,
    KRSStatusUpdate,
    LecturerCreate,
    LecturerRead,
    RoomCreate,
    RoomRead,
    RoomUpdate,
    ScheduleCreate,
    ScheduleMutationResult,
    ScheduleRead,
    ScheduleUpdate,
    SuggestionRead,
)
from app.services.krs_integration import KRSIntegration
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/api", tags=["schedule"])

_default_subject = build_default_subject()


def get_subject() -> ScheduleSubject:
    """Dependency: Publisher singleton (dapat di-override saat testing)."""
    return _default_subject


def get_service(
    db: Session = Depends(get_db), subject: ScheduleSubject = Depends(get_subject)
) -> ScheduleService:
    return ScheduleService(db, subject)


# ------------------------------------------------------------------ Ruangan
@router.post("/rooms", response_model=RoomRead, status_code=201)
def create_room(payload: RoomCreate, service: ScheduleService = Depends(get_service)):
    return service.create_room(payload.model_dump())


@router.get("/rooms", response_model=List[RoomRead])
def list_rooms(service: ScheduleService = Depends(get_service)):
    return service.list_rooms()


@router.get("/rooms/{room_id}", response_model=RoomRead)
def get_room(room_id: int, service: ScheduleService = Depends(get_service)):
    return service.get_room(room_id)


@router.put("/rooms/{room_id}", response_model=RoomRead)
def update_room(room_id: int, payload: RoomUpdate, service: ScheduleService = Depends(get_service)):
    return service.update_room(room_id, payload.model_dump(exclude_unset=True))


@router.delete("/rooms/{room_id}", status_code=204)
def delete_room(room_id: int, service: ScheduleService = Depends(get_service)):
    service.delete_room(room_id)


# --------------------------------------------------------------------- Dosen
@router.post("/lecturers", response_model=LecturerRead, status_code=201)
def create_lecturer(payload: LecturerCreate, service: ScheduleService = Depends(get_service)):
    return service.create_lecturer(payload.model_dump())


@router.get("/lecturers", response_model=List[LecturerRead])
def list_lecturers(service: ScheduleService = Depends(get_service)):
    return service.list_lecturers()


@router.get("/lecturers/{lecturer_id}", response_model=LecturerRead)
def get_lecturer(lecturer_id: int, service: ScheduleService = Depends(get_service)):
    return service.get_lecturer(lecturer_id)


# -------------------------------------------------------------------- Jadwal
@router.post("/schedules", response_model=ScheduleMutationResult, status_code=201)
def create_schedule(
    payload: ScheduleCreate,
    force: bool = Query(False, description="Tetap simpan walau bentrok"),
    service: ScheduleService = Depends(get_service),
):
    return service.create_schedule(payload.model_dump(), force=force)


@router.get("/schedules", response_model=List[ScheduleRead])
def list_schedules(
    day: Optional[str] = None,
    room_id: Optional[int] = None,
    lecturer_id: Optional[int] = None,
    semester: Optional[str] = None,
    course_code: Optional[str] = None,
    service: ScheduleService = Depends(get_service),
):
    return service.list_schedules(day, room_id, lecturer_id, semester, course_code)


@router.get("/schedules/{schedule_id}", response_model=ScheduleRead)
def get_schedule(schedule_id: int, service: ScheduleService = Depends(get_service)):
    return service.get_schedule(schedule_id)


@router.put("/schedules/{schedule_id}", response_model=ScheduleMutationResult)
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    force: bool = Query(False, description="Tetap simpan walau bentrok"),
    service: ScheduleService = Depends(get_service),
):
    return service.update_schedule(schedule_id, payload.model_dump(exclude_unset=True), force=force)


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, service: ScheduleService = Depends(get_service)) -> Dict[str, Any]:
    return service.delete_schedule(schedule_id)


# ------------------------------------------------- Conflict Resolver (Admin)
@router.get("/conflicts", response_model=ConflictDashboard)
def conflict_dashboard(
    semester: Optional[str] = None, service: ScheduleService = Depends(get_service)
):
    """Dashboard admin: seluruh bentrok (ruangan, dosen, waktu, kapasitas)."""
    return service.conflict_dashboard(semester)


@router.get("/schedules/{schedule_id}/suggestions", response_model=List[SuggestionRead])
def schedule_suggestions(schedule_id: int, service: ScheduleService = Depends(get_service)):
    """AI Rescheduler: 3 alternatif jadwal bebas bentrok."""
    return service.suggest(schedule_id)


# ----------------------------------------------------------------------- KRS
@router.post("/krs", response_model=KRSRead, status_code=201)
def enroll_krs(payload: KRSCreate, db: Session = Depends(get_db)):
    return KRSIntegration(db).enroll(**payload.model_dump())


@router.get("/krs", response_model=List[KRSRead])
def list_krs(
    nim: Optional[str] = None,
    status: Optional[str] = None,
    schedule_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return KRSIntegration(db).list(nim=nim, status=status, schedule_id=schedule_id)


@router.patch("/krs/{krs_id}/status", response_model=KRSRead)
def update_krs_status(krs_id: int, payload: KRSStatusUpdate, db: Session = Depends(get_db)):
    return KRSIntegration(db).update_status(krs_id, payload.status)


# ------------------------------------------------------------- Notifikasi
@router.get("/notifications")
def list_notifications(subject: ScheduleSubject = Depends(get_subject)) -> List[Dict[str, Any]]:
    """Seluruh notifikasi simulasi yang pernah dikirim oleh para observer."""
    records: List[Dict[str, Any]] = []
    for observer in subject.observers:
        if isinstance(observer, BaseObserver):
            records.extend(observer.outbox)
    return sorted(records, key=lambda r: r["timestamp"])
