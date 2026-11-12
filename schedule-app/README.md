# Schedule Service - Modul Jadwal & Ruangan

Sistem penjadwalan kuliah dengan deteksi bentrok 3 dimensi (waktu - ruangan - dosen), notifikasi
berbasis **Observer Pattern**, **AI Rescheduler** berbasis Constraint Satisfaction Problem, dan
integrasi invalidasi **KRS**.

- Nama: Nabila Latifatul Hamdah
- NIM: 24360006
- Mata Kuliah: Dasar-dasar Komputasi Awan dan Terdistribusi
- Institusi: Institut Sains dan Teknologi Nasional (ISTN) Jakarta
- Tugas: Minggu 7-8 - Modul Jadwal & Ruangan

## Menjalankan

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

pytest                              # jalankan seluruh unit test
uvicorn app.main:app --reload       # jalankan API, dokumentasi di http://127.0.0.1:8000/docs
```

Database default: SQLite `schedule.db` (tabel dibuat otomatis saat startup). Ubah dengan
`DATABASE_URL`, mis. `postgresql+psycopg://user:pass@localhost/schedule`. Untuk memakai Alembic:
set `AUTO_CREATE_TABLES=false` lalu jalankan `alembic upgrade head`.

## Struktur

| Path | Fungsi |
|---|---|
| `app/config.py` | Konfigurasi dan parameter CSP (jam operasional, sholat Jumat, dll.) |
| `app/database.py` | Engine, session, Base SQLAlchemy 2.0 |
| `app/models.py` | Room, Lecturer, Schedule, KRSEnrollment |
| `app/schemas.py` | Skema Pydantic v2 |
| `app/observers/subject.py` | `ScheduleSubject` (Publisher), `Observer`, `BaseObserver` |
| `app/observers/*_observer.py` | Subscriber: mahasiswa, dosen, admin akademik |
| `app/services/conflict_detector.py` | Interval tree + deteksi bentrok + cek kapasitas |
| `app/services/schedule_service.py` | CRUD, validasi, notifikasi, dashboard konflik |
| `app/services/ai_rescheduler.py` | Solver CSP, 3 saran jadwal alternatif |
| `app/services/krs_integration.py` | Invalidasi KRS APPROVED -> REVISION |
| `app/routers/schedule.py` | Endpoint REST |
| `alembic/` | Migrasi database |
| `tests/` | Unit test pytest |
| `docs/AI_LOG_OPAR.md` | Log penggunaan AI |

## Endpoint utama

| Method | Path | Keterangan |
|---|---|---|
| POST/GET/PUT/DELETE | `/api/rooms`, `/api/rooms/{id}` | CRUD ruangan |
| POST/GET | `/api/lecturers`, `/api/lecturers/{id}` | Dosen |
| POST | `/api/schedules?force=false` | Buat jadwal (409 bila bentrok, 422 bila melebihi kapasitas) |
| GET | `/api/schedules` | Daftar jadwal (filter: day, room_id, lecturer_id, semester, course_code) |
| PUT/DELETE | `/api/schedules/{id}` | Ubah / hapus jadwal |
| GET | `/api/conflicts` | Dashboard admin: daftar bentrok |
| GET | `/api/schedules/{id}/suggestions` | AI Rescheduler: 3 alternatif jadwal |
| POST/GET | `/api/krs` | Simulasi pengambilan KRS |
| PATCH | `/api/krs/{id}/status` | Ubah status KRS (DRAFT/SUBMITTED/APPROVED/REVISION) |
| GET | `/api/notifications` | Log notifikasi simulasi |

## Contoh alur (curl)

```bash
curl -X POST localhost:8000/api/rooms -H "Content-Type: application/json" \
  -d '{"code":"A101","name":"Ruang A101","capacity":40}'
curl -X POST localhost:8000/api/lecturers -H "Content-Type: application/json" \
  -d '{"nip":"1001","name":"Dr. Budi","email":"budi@istn.ac.id"}'
curl -X POST localhost:8000/api/schedules -H "Content-Type: application/json" \
  -d '{"course_code":"MK001","course_name":"Kalkulus I","semester":"2026-1","day":"Senin",
       "start_time":"08:00","end_time":"10:00","room_id":1,"lecturer_id":1,"enrolled_count":40}'
curl localhost:8000/api/schedules/1/suggestions
```

Contoh respons saran AI:

```json
[
  {"hari": "Senin", "jam_mulai": "08:00", "jam_selesai": "10:00", "ruangan": "B202",
   "reason": "Slot pagi (Senin 08:00-10:00); ruangan B202 berkapasitas 45 untuk 40 mahasiswa; ..."}
]
```

## Aturan bisnis

- **Bentrok**: hari sama + jam beririsan (interval setengah-terbuka) + ruangan sama = `room_conflict`;
  dosen sama = `lecturer_conflict`; mata kuliah sama terjadwal ganda = `time_overlap`.
  Jadwal beda semester tidak dibandingkan.
- **Kapasitas**: `enrolled_count <= kapasitas ruangan`; dicek saat create, update, dan pengambilan KRS.
- **Create/Update bentrok**: ditolak (409) kecuali `force=true`; jadwal yang tersimpan dengan bentrok
  muncul di `/api/conflicts`.
- **KRS**: perubahan jadwal mengubah `APPROVED`/`SUBMITTED` menjadi `REVISION`. Pada bentrok, hanya
  mahasiswa yang mengambil kedua mata kuliah yang bentrok yang di-invalidate.

## Sequence Diagram - Observer Pattern

```mermaid
sequenceDiagram
    actor Admin
    participant API as Router (FastAPI)
    participant SVC as ScheduleService
    participant DET as ConflictDetector
    participant DB as Database
    participant KRS as KRSIntegration
    participant SUB as ScheduleSubject
    participant STU as StudentObserver
    participant LEC as LecturerObserver
    participant ADM as AcademicAdminObserver

    Admin->>API: PUT /api/schedules/{id}
    API->>SVC: update_schedule(id, changes)
    SVC->>DET: candidate_conflicts(jadwal baru)
    DET-->>SVC: daftar konflik
    SVC->>DB: simpan perubahan
    SVC->>KRS: invalidate_for_schedule / invalidate_for_conflicts
    KRS->>DB: APPROVED -> REVISION
    SVC->>DB: commit
    SVC->>SUB: notify("SCHEDULE_CHANGED", data)
    par broadcast ke semua observer
        SUB->>STU: update(event)
        STU-->>STU: email/push ke mahasiswa terdampak
    and
        SUB->>LEC: update(event)
        LEC-->>LEC: email ke dosen
    and
        SUB->>ADM: update(event)
        ADM-->>ADM: ringkasan ke admin akademik
    end
    SVC-->>API: hasil (jadwal, konflik, KRS ter-invalidate)
    API-->>Admin: 200 OK
```

## Testing

`pytest` menjalankan: deteksi bentrok ruangan/dosen/waktu/kapasitas (termasuk perbandingan interval
tree dengan brute force), Observer (attach/detach/notify, isolasi kegagalan, isi notifikasi),
integrasi invalidasi KRS, dan AI rescheduling (kapasitas, bebas bentrok, prioritas pagi, sholat Jumat).
