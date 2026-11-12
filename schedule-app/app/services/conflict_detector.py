"""Deteksi bentrok jadwal 3 dimensi (waktu - ruangan - dosen).

Algoritma
---------
Mencocokkan semua pasangan jadwal secara naif berbiaya O(n^2). Di sini jadwal
dikelompokkan per (semester, hari), lalu tiap kelompok dimasukkan ke
*Interval Tree* (BST seimbang yang di-augment dengan nilai `max_end`).
Untuk setiap jadwal, query tree hanya mengunjungi interval yang benar-benar
beririsan, sehingga biaya total O(n log n + k) dengan k = jumlah pasangan
beririsan.

Dua interval [a1, a2) dan [b1, b2) dianggap beririsan bila a1 < b2 dan b1 < a2.
Jadwal yang hanya "bersentuhan" (08:00-10:00 dan 10:00-12:00) TIDAK bentrok.

Jenis konflik
-------------
- room_conflict      : hari sama + jam beririsan + ruangan sama
- lecturer_conflict  : hari sama + jam beririsan + dosen sama
- time_overlap       : hari sama + jam beririsan + kode mata kuliah sama
                       (mata kuliah yang sama dijadwalkan ganda pada waktu bersamaan)
- capacity_exceeded  : jumlah mahasiswa enrolled > kapasitas ruangan
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from app.config import DAYS

DAY_INDEX = {day: idx for idx, day in enumerate(DAYS)}

ROOM_CONFLICT = "room_conflict"
LECTURER_CONFLICT = "lecturer_conflict"
TIME_OVERLAP = "time_overlap"
CAPACITY_EXCEEDED = "capacity_exceeded"


# ---------------------------------------------------------------- utilitas waktu
def time_to_minutes(value: Any) -> int:
    """Mengubah 'HH:MM', datetime.time, atau int menit menjadi menit sejak 00:00."""
    if isinstance(value, bool):
        raise ValueError("Nilai waktu tidak valid")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        parts = value.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    return value.hour * 60 + value.minute


def minutes_to_str(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def intervals_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """True bila dua interval setengah-terbuka [start, end) beririsan."""
    return a_start < b_end and b_start < a_end


def check_capacity(enrolled: int, capacity: int) -> bool:
    """True bila jumlah mahasiswa enrolled masih <= kapasitas ruangan."""
    return enrolled <= capacity


# ---------------------------------------------------------------- representasi slot
@dataclass(frozen=True)
class Slot:
    id: Optional[int]
    course_code: str
    day: str
    start: int
    end: int
    room_id: Optional[int]
    lecturer_id: Optional[int]
    semester: str = ""
    enrolled: int = 0


_ALIASES = {
    "id": ("id",),
    "course_code": ("course_code", "kode_mk"),
    "day": ("day", "hari"),
    "start": ("start_time", "jam_mulai", "start"),
    "end": ("end_time", "jam_selesai", "end"),
    "room_id": ("room_id", "ruangan"),
    "lecturer_id": ("lecturer_id", "dosen"),
    "semester": ("semester",),
    "enrolled": ("enrolled_count", "enrolled", "jumlah_mahasiswa"),
}


def _read(obj: Any, key: str, default: Any = None) -> Any:
    for name in _ALIASES[key]:
        if isinstance(obj, Mapping):
            if name in obj and obj[name] is not None:
                return obj[name]
        elif getattr(obj, name, None) is not None:
            return getattr(obj, name)
    return default


def to_slot(obj: Any) -> Slot:
    """Mengubah dict / objek ORM / Slot menjadi Slot ternormalisasi."""
    if isinstance(obj, Slot):
        return obj
    start = time_to_minutes(_read(obj, "start"))
    end = time_to_minutes(_read(obj, "end"))
    if end <= start:
        raise ValueError("Jam selesai harus lebih besar dari jam mulai")
    return Slot(
        id=_read(obj, "id"),
        course_code=str(_read(obj, "course_code", "")),
        day=_read(obj, "day"),
        start=start,
        end=end,
        room_id=_read(obj, "room_id"),
        lecturer_id=_read(obj, "lecturer_id"),
        semester=str(_read(obj, "semester", "")),
        enrolled=int(_read(obj, "enrolled", 0)),
    )


# ---------------------------------------------------------------- interval tree
class _Node:
    __slots__ = ("start", "end", "payload", "left", "right", "max_end")

    def __init__(self, start: int, end: int, payload: Any) -> None:
        self.start = start
        self.end = end
        self.payload = payload
        self.left: Optional["_Node"] = None
        self.right: Optional["_Node"] = None
        self.max_end = end


class IntervalTree:
    """Interval tree statis (augmented BST) untuk query irisan interval.

    Dibangun dari daftar (start, end, payload) yang diurutkan sehingga tinggi
    pohon O(log n). Query mengembalikan payload semua interval yang beririsan.
    """

    def __init__(self, items: Sequence[Tuple[int, int, Any]]) -> None:
        ordered = sorted(items, key=lambda item: (item[0], item[1]))
        self.size = len(ordered)
        self._root = self._build(ordered, 0, len(ordered))

    def _build(self, items: Sequence[Tuple[int, int, Any]], lo: int, hi: int) -> Optional[_Node]:
        if lo >= hi:
            return None
        mid = (lo + hi) // 2
        start, end, payload = items[mid]
        node = _Node(start, end, payload)
        node.left = self._build(items, lo, mid)
        node.right = self._build(items, mid + 1, hi)
        for child in (node.left, node.right):
            if child is not None and child.max_end > node.max_end:
                node.max_end = child.max_end
        return node

    def query(self, start: int, end: int) -> List[Any]:
        result: List[Any] = []
        self._query(self._root, start, end, result)
        return result

    def _query(self, node: Optional[_Node], start: int, end: int, out: List[Any]) -> None:
        if node is None or node.max_end <= start:
            return
        self._query(node.left, start, end, out)
        if intervals_overlap(node.start, node.end, start, end):
            out.append(node.payload)
        if node.start < end:
            self._query(node.right, start, end, out)


# ---------------------------------------------------------------- klasifikasi konflik
def _pair_conflicts(a: Slot, b: Slot) -> List[Dict[str, Any]]:
    """Konflik antara dua slot yang SUDAH diketahui beririsan pada hari yang sama."""
    overlap_start = max(a.start, b.start)
    overlap_end = min(a.end, b.end)
    window = f"{minutes_to_str(overlap_start)}-{minutes_to_str(overlap_end)}"
    base = {
        "day": a.day,
        "semester": a.semester,
        "schedule_ids": [a.id, b.id],
        "course_codes": [a.course_code, b.course_code],
        "overlap_start": minutes_to_str(overlap_start),
        "overlap_end": minutes_to_str(overlap_end),
    }
    found: List[Dict[str, Any]] = []
    if a.room_id is not None and a.room_id == b.room_id:
        found.append({
            **base,
            "type": ROOM_CONFLICT,
            "resource_id": a.room_id,
            "detail": f"Ruangan yang sama dipakai {a.course_code} dan {b.course_code} "
                      f"pada hari {a.day} pukul {window}.",
        })
    if a.lecturer_id is not None and a.lecturer_id == b.lecturer_id:
        found.append({
            **base,
            "type": LECTURER_CONFLICT,
            "resource_id": a.lecturer_id,
            "detail": f"Dosen yang sama mengajar {a.course_code} dan {b.course_code} "
                      f"pada hari {a.day} pukul {window}.",
        })
    if a.course_code and a.course_code == b.course_code:
        found.append({
            **base,
            "type": TIME_OVERLAP,
            "resource_id": None,
            "detail": f"Mata kuliah {a.course_code} dijadwalkan ganda pada hari {a.day} "
                      f"pukul {window}.",
        })
    return found


def _sort_key(conflict: Dict[str, Any]) -> Tuple[int, str, str, str]:
    return (
        DAY_INDEX.get(conflict["day"], 99),
        conflict["overlap_start"],
        conflict["type"],
        str(conflict["schedule_ids"]),
    )


def detect_schedule_conflict(
    schedules: Sequence[Any], rooms_capacity: Optional[Mapping[int, int]] = None
) -> List[Dict[str, Any]]:
    """Mendeteksi seluruh konflik pada daftar jadwal.

    Args:
        schedules: daftar jadwal (dict, objek ORM, atau Slot). Kunci dict yang
            didukung: id, course_code, day/hari, start_time/jam_mulai,
            end_time/jam_selesai, room_id/ruangan, lecturer_id/dosen, semester,
            enrolled_count.
        rooms_capacity: (opsional) peta room_id -> kapasitas untuk cek kapasitas.

    Returns:
        List konflik. Tiap item memuat `type`, `schedule_ids` (jadwal terdampak),
        `day`, `overlap_start`, `overlap_end`, dan `detail`.
    """
    slots = [to_slot(item) for item in schedules]

    groups: Dict[Tuple[str, str], List[int]] = {}
    for index, slot in enumerate(slots):
        groups.setdefault((slot.semester, slot.day), []).append(index)

    conflicts: List[Dict[str, Any]] = []
    for indexes in groups.values():
        tree = IntervalTree([(slots[i].start, slots[i].end, i) for i in indexes])
        for i in indexes:
            a = slots[i]
            for j in sorted(tree.query(a.start, a.end)):
                if j > i:  # tiap pasangan hanya diproses sekali
                    conflicts.extend(_pair_conflicts(a, slots[j]))

    if rooms_capacity is not None:
        for slot in slots:
            capacity = rooms_capacity.get(slot.room_id)
            if capacity is not None and not check_capacity(slot.enrolled, capacity):
                conflicts.append({
                    "type": CAPACITY_EXCEEDED,
                    "day": slot.day,
                    "semester": slot.semester,
                    "schedule_ids": [slot.id],
                    "course_codes": [slot.course_code],
                    "overlap_start": minutes_to_str(slot.start),
                    "overlap_end": minutes_to_str(slot.end),
                    "resource_id": slot.room_id,
                    "detail": f"{slot.course_code} memiliki {slot.enrolled} mahasiswa, "
                              f"melebihi kapasitas ruangan ({capacity}).",
                })

    conflicts.sort(key=_sort_key)
    return conflicts


def candidate_conflicts(candidate: Any, existing: Sequence[Any]) -> List[Dict[str, Any]]:
    """Konflik antara satu jadwal kandidat dan jadwal yang sudah ada (O(n))."""
    cand = to_slot(candidate)
    found: List[Dict[str, Any]] = []
    for item in existing:
        other = to_slot(item)
        if cand.id is not None and other.id == cand.id:
            continue
        if other.day != cand.day or other.semester != cand.semester:
            continue
        if intervals_overlap(cand.start, cand.end, other.start, other.end):
            found.extend(_pair_conflicts(cand, other))
    found.sort(key=_sort_key)
    return found
