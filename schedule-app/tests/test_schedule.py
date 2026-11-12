"""Unit test: deteksi bentrok, Observer, AI rescheduling, dan integrasi KRS."""
import random

from app.observers import Observer, ScheduleSubject
from app.services.ai_rescheduler import suggest_alternatives
from app.services.conflict_detector import (
    CAPACITY_EXCEEDED,
    LECTURER_CONFLICT,
    ROOM_CONFLICT,
    TIME_OVERLAP,
    IntervalTree,
    candidate_conflicts,
    detect_schedule_conflict,
)


# ----------------------------------------------------------------- helper
def slot(sid, day, start, end, room, lecturer, course=None, semester="2026-1", enrolled=0):
    return {
        "id": sid,
        "course_code": course or f"MK{sid}",
        "day": day,
        "start_time": start,
        "end_time": end,
        "room_id": room,
        "lecturer_id": lecturer,
        "semester": semester,
        "enrolled_count": enrolled,
    }


def mk_room(client, code, capacity):
    r = client.post("/api/rooms", json={"code": code, "name": f"Ruang {code}", "capacity": capacity})
    assert r.status_code == 201, r.text
    return r.json()


def mk_lecturer(client, nip, name):
    r = client.post(
        "/api/lecturers", json={"nip": nip, "name": name, "email": f"{nip}@istn.ac.id"}
    )
    assert r.status_code == 201, r.text
    return r.json()


def payload(room, lecturer, **over):
    base = {
        "course_code": "MK001",
        "course_name": "Kalkulus I",
        "semester": "2026-1",
        "day": "Senin",
        "start_time": "08:00",
        "end_time": "10:00",
        "room_id": room["id"],
        "lecturer_id": lecturer["id"],
        "enrolled_count": 0,
    }
    base.update(over)
    return base


def mk_schedule(client, room, lecturer, force=False, **over):
    r = client.post(
        f"/api/schedules?force={'true' if force else 'false'}", json=payload(room, lecturer, **over)
    )
    assert r.status_code == 201, r.text
    return r.json()["schedule"]


def enroll(client, nim, schedule_id):
    r = client.post(
        "/api/krs",
        json={
            "student_nim": nim,
            "student_name": f"Mahasiswa {nim}",
            "student_email": f"{nim}@student.istn.ac.id",
            "schedule_id": schedule_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def set_status(client, krs_id, status):
    r = client.patch(f"/api/krs/{krs_id}/status", json={"status": status})
    assert r.status_code == 200, r.text


def krs_of(client, nim):
    return client.get(f"/api/krs?nim={nim}").json()


# ============================================================ 1. Deteksi bentrok
def test_room_conflict_detected():
    result = detect_schedule_conflict([
        slot(1, "Senin", "08:00", "10:00", room=1, lecturer=1),
        slot(2, "Senin", "09:00", "11:00", room=1, lecturer=2),
    ])
    assert [c["type"] for c in result] == [ROOM_CONFLICT]
    assert result[0]["schedule_ids"] == [1, 2]


def test_lecturer_conflict_detected():
    result = detect_schedule_conflict([
        slot(1, "Senin", "08:00", "10:00", room=1, lecturer=7),
        slot(2, "Senin", "09:30", "11:00", room=2, lecturer=7),
    ])
    assert [c["type"] for c in result] == [LECTURER_CONFLICT]


def test_room_and_lecturer_conflict_both_reported():
    result = detect_schedule_conflict([
        slot(1, "Rabu", "08:00", "10:00", room=1, lecturer=1),
        slot(2, "Rabu", "08:00", "10:00", room=1, lecturer=1),
    ])
    assert {c["type"] for c in result} == {ROOM_CONFLICT, LECTURER_CONFLICT}


def test_touching_intervals_do_not_conflict():
    result = detect_schedule_conflict([
        slot(1, "Senin", "08:00", "10:00", room=1, lecturer=1),
        slot(2, "Senin", "10:00", "12:00", room=1, lecturer=1),
    ])
    assert result == []


def test_different_day_or_semester_does_not_conflict():
    assert detect_schedule_conflict([
        slot(1, "Senin", "08:00", "10:00", 1, 1),
        slot(2, "Selasa", "08:00", "10:00", 1, 1),
    ]) == []
    assert detect_schedule_conflict([
        slot(1, "Senin", "08:00", "10:00", 1, 1, semester="2026-1"),
        slot(2, "Senin", "08:00", "10:00", 1, 1, semester="2026-2"),
    ]) == []


def test_time_overlap_for_same_course_scheduled_twice():
    result = detect_schedule_conflict([
        slot(1, "Kamis", "08:00", "10:00", room=1, lecturer=1, course="MK-X"),
        slot(2, "Kamis", "09:00", "11:00", room=2, lecturer=2, course="MK-X"),
    ])
    assert [c["type"] for c in result] == [TIME_OVERLAP]


def test_capacity_exceeded_reported_with_room_capacity_map():
    result = detect_schedule_conflict(
        [slot(1, "Senin", "08:00", "10:00", room=1, lecturer=1, enrolled=40)],
        rooms_capacity={1: 30},
    )
    assert [c["type"] for c in result] == [CAPACITY_EXCEEDED]


def test_interval_tree_matches_bruteforce_on_random_data():
    rng = random.Random(24360006)
    days = ["Senin", "Selasa", "Rabu"]
    schedules = []
    for i in range(1, 81):
        start = rng.randrange(7 * 60, 16 * 60, 30)
        end = start + rng.choice([60, 90, 120, 150])
        schedules.append({
            "id": i, "course_code": f"MK{i}", "day": rng.choice(days),
            "start_time": start, "end_time": end,
            "room_id": rng.randint(1, 4), "lecturer_id": rng.randint(1, 6),
            "semester": "2026-1",
        })

    expected = set()
    for a in range(len(schedules)):
        for b in range(a + 1, len(schedules)):
            x, y = schedules[a], schedules[b]
            if x["day"] == y["day"] and x["start_time"] < y["end_time"] and y["start_time"] < x["end_time"]:
                if x["room_id"] == y["room_id"]:
                    expected.add((frozenset((x["id"], y["id"])), ROOM_CONFLICT))
                if x["lecturer_id"] == y["lecturer_id"]:
                    expected.add((frozenset((x["id"], y["id"])), LECTURER_CONFLICT))

    found = {
        (frozenset(c["schedule_ids"]), c["type"]) for c in detect_schedule_conflict(schedules)
    }
    assert found == expected
    assert len(expected) > 0


def test_interval_tree_query():
    tree = IntervalTree([(0, 10, "a"), (5, 15, "b"), (20, 30, "c")])
    assert sorted(tree.query(8, 12)) == ["a", "b"]
    assert tree.query(15, 20) == []
    assert tree.query(25, 26) == ["c"]


# ====================================================== 2. API: CRUD & kapasitas
def test_create_schedule_over_capacity_rejected(client):
    room, lec = mk_room(client, "A101", 30), mk_lecturer(client, "1001", "Dr. Budi")
    r = client.post("/api/schedules", json=payload(room, lec, enrolled_count=40))
    assert r.status_code == 422
    assert "kapasitas" in r.json()["detail"].lower()


def test_create_schedule_conflict_returns_409_and_force_saves(client):
    room, lec1, lec2 = mk_room(client, "A101", 40), mk_lecturer(client, "1001", "Budi"), mk_lecturer(client, "1002", "Sari")
    mk_schedule(client, room, lec1)

    clash = payload(room, lec2, course_code="MK002", course_name="Fisika", start_time="09:00", end_time="11:00")
    r = client.post("/api/schedules", json=clash)
    assert r.status_code == 409
    assert r.json()["conflicts"][0]["type"] == ROOM_CONFLICT

    r = client.post("/api/schedules?force=true", json=clash)
    assert r.status_code == 201
    assert r.json()["conflicts"][0]["type"] == ROOM_CONFLICT

    dashboard = client.get("/api/conflicts").json()
    assert dashboard["total"] == 1
    assert dashboard["by_type"] == {ROOM_CONFLICT: 1}
    assert len(dashboard["conflicts"][0]["schedules"]) == 2


def test_update_and_delete_schedule_and_room_protection(client):
    room, lec = mk_room(client, "A101", 40), mk_lecturer(client, "1001", "Budi")
    sched = mk_schedule(client, room, lec)

    r = client.put(f"/api/schedules/{sched['id']}", json={"start_time": "13:00", "end_time": "15:00"})
    assert r.status_code == 200
    assert r.json()["schedule"]["start_time"] == "13:00"
    assert set(r.json()["changed_fields"]) == {"start_time", "end_time"}

    assert client.delete(f"/api/rooms/{room['id']}").status_code == 409  # masih dipakai

    assert client.delete(f"/api/schedules/{sched['id']}").status_code == 200
    assert client.get(f"/api/schedules/{sched['id']}").status_code == 404
    assert client.delete(f"/api/rooms/{room['id']}").status_code == 204


def test_update_rejects_invalid_time_range(client):
    room, lec = mk_room(client, "A101", 40), mk_lecturer(client, "1001", "Budi")
    sched = mk_schedule(client, room, lec)
    r = client.put(f"/api/schedules/{sched['id']}", json={"start_time": "11:00"})
    assert r.status_code == 422  # end 10:00 <= start 11:00


# ============================================================== 3. Observer
class Recorder(Observer):
    def __init__(self):
        self.events = []

    def update(self, event):
        self.events.append(event)


class Exploding(Observer):
    def update(self, event):
        raise RuntimeError("boom")


def test_subject_attach_detach_notify():
    subject, rec = ScheduleSubject(), Recorder()
    subject.attach(rec)
    subject.attach(rec)  # idempoten
    assert len(subject.observers) == 1

    report = subject.notify("SCHEDULE_CHANGED", {"action": "CREATED"})
    assert report["delivered"] == 1
    assert rec.events[0].event_type == "SCHEDULE_CHANGED"
    assert rec.events[0].data == {"action": "CREATED"}

    subject.detach(rec)
    subject.detach(rec)  # aman walau sudah lepas
    subject.notify("SCHEDULE_CHANGED", {"action": "UPDATED"})
    assert len(rec.events) == 1


def test_failing_observer_does_not_block_others():
    subject, rec = ScheduleSubject(), Recorder()
    subject.attach(Exploding())
    subject.attach(rec)
    report = subject.notify("SCHEDULE_CHANGED", {"action": "UPDATED"})
    assert report["delivered"] == 1
    assert report["failed"][0]["observer"] == "Exploding"
    assert len(rec.events) == 1


def test_notifications_sent_on_create_update_delete(client, observers):
    room, lec = mk_room(client, "A101", 40), mk_lecturer(client, "1001", "Budi")
    student, lecturer, admin = (
        observers["StudentObserver"], observers["LecturerObserver"], observers["AcademicAdminObserver"],
    )

    sched = mk_schedule(client, room, lec)  # CREATED
    assert len(lecturer.outbox) == 1 and lecturer.outbox[0]["recipient"] == "1001@istn.ac.id"
    assert len(admin.outbox) >= 1
    assert student.outbox == []  # belum ada mahasiswa

    enroll(client, "24360001", sched["id"])
    enroll(client, "24360002", sched["id"])

    client.put(f"/api/schedules/{sched['id']}", json={"day": "Selasa"})  # UPDATED
    recipients = {m["recipient"] for m in student.outbox}
    assert recipients == {"24360001@student.istn.ac.id", "24360002@student.istn.ac.id"}
    assert {m["channel"] for m in student.outbox} == {"email", "push"}
    assert "Selasa" in student.outbox[0]["body"]
    assert len(lecturer.outbox) == 2

    before = len(student.outbox)
    client.delete(f"/api/schedules/{sched['id']}")  # DELETED
    assert len(student.outbox) == before + 4
    assert "dibatalkan" in student.outbox[-1]["body"]
    assert any("dibatalkan" in m["body"] for m in lecturer.outbox)

    log = client.get("/api/notifications").json()
    assert len(log) == len(student.outbox) + len(lecturer.outbox) + len(admin.outbox)


def test_old_lecturer_is_notified_when_replaced(client, observers):
    room = mk_room(client, "A101", 40)
    old, new = mk_lecturer(client, "1001", "Budi"), mk_lecturer(client, "1002", "Sari")
    sched = mk_schedule(client, room, old)
    client.put(f"/api/schedules/{sched['id']}", json={"lecturer_id": new["id"]})
    recipients = [m["recipient"] for m in observers["LecturerObserver"].outbox]
    assert "1002@istn.ac.id" in recipients and recipients.count("1001@istn.ac.id") == 2


# ============================================================ 4. Integrasi KRS
def test_krs_invalidated_when_schedule_changes(client, observers):
    room, lec = mk_room(client, "A101", 40), mk_lecturer(client, "1001", "Budi")
    sched = mk_schedule(client, room, lec)
    approved, draft = enroll(client, "24360001", sched["id"]), enroll(client, "24360002", sched["id"])
    set_status(client, approved["id"], "APPROVED")

    r = client.put(f"/api/schedules/{sched['id']}", json={"start_time": "13:00", "end_time": "15:00"})
    assert r.status_code == 200
    assert r.json()["krs_invalidated"] == 1

    assert krs_of(client, "24360001")[0]["status"] == "REVISION"
    assert krs_of(client, "24360002")[0]["status"] == "DRAFT"  # DRAFT tidak berubah

    msgs = [m for m in observers["StudentObserver"].outbox if m["recipient"].startswith("24360001")]
    assert msgs and "REVISION" in msgs[-1]["body"]
    msgs = [m for m in observers["StudentObserver"].outbox if m["recipient"].startswith("24360002")]
    assert msgs and "REVISION" not in msgs[-1]["body"]


def test_krs_not_touched_when_only_non_schedule_field_changes(client):
    room, lec = mk_room(client, "A101", 40), mk_lecturer(client, "1001", "Budi")
    sched = mk_schedule(client, room, lec)
    row = enroll(client, "24360001", sched["id"])
    set_status(client, row["id"], "APPROVED")
    r = client.put(f"/api/schedules/{sched['id']}", json={"course_name": "Kalkulus Dasar"})
    assert r.json()["krs_invalidated"] == 0
    assert krs_of(client, "24360001")[0]["status"] == "APPROVED"


def test_krs_invalidated_for_students_in_both_conflicting_courses(client):
    room1, room2 = mk_room(client, "A101", 40), mk_room(client, "A102", 40)
    lec = mk_lecturer(client, "1001", "Budi")
    a = mk_schedule(client, room1, lec, course_code="MK001", course_name="Kalkulus")
    b = mk_schedule(
        client, room2, lec, course_code="MK002", course_name="Fisika",
        day="Selasa", start_time="08:00", end_time="10:00",
    )
    for sched in (a, b):
        row = enroll(client, "24360001", sched["id"])
        set_status(client, row["id"], "APPROVED")

    # Pindahkan Fisika ke Senin 09:00 -> bentrok dosen dengan Kalkulus.
    move = {"day": "Senin", "start_time": "09:00", "end_time": "11:00"}
    assert client.put(f"/api/schedules/{b['id']}", json=move).status_code == 409

    r = client.put(f"/api/schedules/{b['id']}?force=true", json=move)
    assert r.status_code == 200
    assert r.json()["conflicts"][0]["type"] == LECTURER_CONFLICT
    statuses = {row["course_code"]: row["status"] for row in krs_of(client, "24360001")}
    assert statuses == {"MK001": "REVISION", "MK002": "REVISION"}


def test_krs_revision_and_detach_when_schedule_deleted(client):
    room, lec = mk_room(client, "A101", 40), mk_lecturer(client, "1001", "Budi")
    sched = mk_schedule(client, room, lec)
    row = enroll(client, "24360001", sched["id"])
    set_status(client, row["id"], "APPROVED")

    r = client.delete(f"/api/schedules/{sched['id']}")
    assert r.json()["krs_invalidated"] == 1
    krs = krs_of(client, "24360001")[0]
    assert krs["status"] == "REVISION" and krs["schedule_id"] is None


def test_krs_enroll_respects_capacity_and_duplicates(client):
    room, lec = mk_room(client, "A101", 2), mk_lecturer(client, "1001", "Budi")
    sched = mk_schedule(client, room, lec)
    enroll(client, "24360001", sched["id"])
    enroll(client, "24360002", sched["id"])
    body = {
        "student_nim": "24360003", "student_name": "C", "student_email": "c@x.id",
        "schedule_id": sched["id"],
    }
    assert client.post("/api/krs", json=body).status_code == 422  # penuh
    dup = {**body, "student_nim": "24360001"}
    assert client.post("/api/krs", json=dup).status_code == 409  # duplikat


# ======================================================= 5. AI Rescheduler (CSP)
def to_minutes(text):
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def test_ai_suggestions_are_valid_conflict_free_and_morning_first(client):
    a101, a102 = mk_room(client, "A101", 40), mk_room(client, "A102", 30)
    b201, b202 = mk_room(client, "B201", 50), mk_room(client, "B202", 45)
    dosen_kalkulus, dosen_fisika = mk_lecturer(client, "1001", "Dr. Budi"), mk_lecturer(client, "1002", "Dr. Sari")

    kalkulus = mk_schedule(client, a101, dosen_kalkulus, enrolled_count=40)
    mk_schedule(  # bentrok ruangan dengan Kalkulus
        client, a101, dosen_fisika, force=True, course_code="MK002", course_name="Fisika",
        start_time="08:00", end_time="10:00",
    )
    mk_schedule(  # dosen Kalkulus sibuk Selasa pagi
        client, b201, dosen_kalkulus, course_code="MK003", course_name="Aljabar",
        day="Selasa", start_time="08:00", end_time="10:00",
    )

    r = client.get(f"/api/schedules/{kalkulus['id']}/suggestions")
    assert r.status_code == 200
    suggestions = r.json()
    assert len(suggestions) == 3
    assert all(set(s) == {"hari", "jam_mulai", "jam_selesai", "ruangan", "reason"} for s in suggestions)

    capacity = {"A101": 40, "A102": 30, "B201": 50, "B202": 45}
    ids = {"A101": a101["id"], "A102": a102["id"], "B201": b201["id"], "B202": b202["id"]}
    existing = [
        slot(kalkulus["id"] + 1, "Senin", "08:00", "10:00", ids["A101"], dosen_fisika["id"], course="MK002"),
        slot(kalkulus["id"] + 2, "Selasa", "08:00", "10:00", ids["B201"], dosen_kalkulus["id"], course="MK003"),
    ]
    seen = set()
    for s in suggestions:
        assert capacity[s["ruangan"]] >= 40  # kapasitas cukup (A102 tidak boleh muncul)
        assert to_minutes(s["jam_mulai"]) < 12 * 60  # prioritas pagi
        assert s["reason"]
        candidate = slot(
            None, s["hari"], s["jam_mulai"], s["jam_selesai"], ids[s["ruangan"]],
            dosen_kalkulus["id"], course="MK001",
        )
        assert candidate_conflicts(candidate, existing) == []  # bebas bentrok ruangan & dosen
        seen.add((s["hari"], s["jam_mulai"], s["ruangan"]))
    assert len(seen) == 3  # alternatif berbeda satu sama lain


def test_ai_avoids_students_other_classes(client):
    a101, b201 = mk_room(client, "A101", 40), mk_room(client, "B201", 40)
    dosen_a, dosen_b = mk_lecturer(client, "1001", "Budi"), mk_lecturer(client, "1002", "Sari")
    target = mk_schedule(client, a101, dosen_a, enrolled_count=0)
    other = mk_schedule(
        client, b201, dosen_b, course_code="MK002", course_name="Fisika",
        start_time="08:00", end_time="10:00", day="Senin",
    )
    enroll(client, "24360001", target["id"])
    enroll(client, "24360001", other["id"])

    # Senin 08:00 di ruang A101 adalah slot asli; kandidat Senin 08:00-10:00 harus tidak muncul
    # untuk mahasiswa yang juga mengambil Fisika di jam yang sama.
    for s in client.get(f"/api/schedules/{target['id']}/suggestions").json():
        if s["hari"] == "Senin":
            assert not (to_minutes(s["jam_mulai"]) < 10 * 60 and to_minutes(s["jam_selesai"]) > 8 * 60)


def test_ai_never_uses_friday_prayer_time():
    target = slot(1, "Jumat", "08:00", "10:00", room=1, lecturer=1, enrolled=10)
    rooms = [{"id": 1, "code": "A101", "capacity": 40}, {"id": 2, "code": "A102", "capacity": 40}]
    result = suggest_alternatives(target, [target], rooms, days=("Jumat",), limit=50)
    assert result
    for s in result:
        start, end = to_minutes(s["jam_mulai"]), to_minutes(s["jam_selesai"])
        assert not (start < 13 * 60 and end > 11 * 60 + 30)


def test_ai_returns_empty_when_no_room_fits():
    target = slot(1, "Senin", "08:00", "10:00", room=1, lecturer=1, enrolled=100)
    rooms = [{"id": 1, "code": "A101", "capacity": 40}]
    assert suggest_alternatives(target, [target], rooms) == []


def test_ai_suggestions_unknown_schedule_returns_404(client):
    assert client.get("/api/schedules/999/suggestions").status_code == 404
