# AI Usage Log (OPAR) - Modul Jadwal & Ruangan

| Item | Keterangan |
|---|---|
| Nama | Nabila Latifatul Hamdah |
| NIM | 24360006 |
| Mata Kuliah | Dasar-dasar Komputasi Awan dan Terdistribusi |
| Institusi | Institut Sains dan Teknologi Nasional (ISTN) Jakarta |
| Tugas | Minggu 7-8: Modul Jadwal & Ruangan (Scheduling System & Observer Pattern) |
| Asisten AI | Claude (Anthropic) |
| Tanggal | 10 November 2026 |

Format tiap entri: **O**bjective (tujuan), **P**rompt (instruksi ke AI), **A**ction (apa yang
dihasilkan/dilakukan), **R**esult & Reflection (hasil verifikasi dan refleksi).

---

## Entri 1 - Kerangka proyek dan arsitektur

**Objective.** Membuat struktur proyek `schedule-app/` yang lengkap (FastAPI + SQLAlchemy 2.0 +
Alembic + pytest) untuk lima deliverable Minggu 7-8.

**Prompt.** Meminta AI berperan sebagai Senior Backend Engineer/Software Architect Python,
memberikan identitas mahasiswa, daftar lima deliverable beserta bobotnya, struktur folder yang
diharapkan, dan syarat bahwa seluruh isi file harus lengkap tanpa placeholder, disajikan dalam
bentuk script `setup_project.py`.

**Action.** AI merancang arsitektur berlapis: `routers` (HTTP) -> `services` (logika bisnis) ->
`models` (database), dengan `observers` sebagai modul terpisah. Exception bisnis ditaruh di
`services/__init__.py` supaya tidak terjadi circular import, lalu dipetakan ke kode HTTP di
`main.py`.

**Result & Reflection.** Pemisahan lapisan membuat logika bentrok dan CSP berupa fungsi murni yang
mudah diuji tanpa database. Saya perlu memahami alur request -> service -> observer agar bisa
menjelaskannya saat presentasi.

---

## Entri 2 - Algoritma deteksi bentrok 3 dimensi

**Objective.** Mendeteksi `room_conflict`, `lecturer_conflict`, dan `time_overlap` secara efisien,
sesuai Step 1 pada soal.

**Prompt.** Mengikuti prompt Step 1 pada soal: input daftar jadwal, output daftar konflik beserta
tipe dan jadwal terdampak; optimasi dengan interval tree.

**Action.** AI membuat `IntervalTree` (BST yang di-augment dengan `max_end`) dan
`detect_schedule_conflict`. Jadwal dikelompokkan per (semester, hari), lalu tiap jadwal melakukan
query ke tree sehingga kompleksitas O(n log n + k), bukan O(n^2). Irisan memakai interval
setengah-terbuka sehingga 08:00-10:00 dan 10:00-12:00 tidak dianggap bentrok. Cek kapasitas
(`enrolled <= capacity`) disediakan sebagai `capacity_exceeded` dan juga ditolak saat create/update.

**Result & Reflection.** Diverifikasi dengan `test_interval_tree_matches_bruteforce_on_random_data`
yang membandingkan hasil interval tree dengan pencocokan brute-force pada 80 jadwal acak. Pelajaran
utama: definisi "bentrok" harus dibuat eksplisit (batas jam yang bersentuhan, beda semester) karena
menentukan hasil. Jenis `time_overlap` saya definisikan sebagai mata kuliah yang sama terjadwal ganda
di waktu bersamaan, karena soal tidak mendefinisikannya secara rinci.

---

## Entri 3 - Observer Pattern

**Objective.** Notifikasi otomatis ke mahasiswa, dosen, dan admin akademik saat jadwal dibuat,
diubah, atau dihapus.

**Prompt.** Mengikuti prompt Step 2: `ScheduleSubject` dengan `attach`, `detach`, `notify`; observer
konkret `StudentObserver`, `LecturerObserver`, dan `AcademicAdminObserver`.

**Action.** AI membuat `ScheduleSubject` (thread-safe, `attach` idempoten) dan base class
`BaseObserver` yang mengirim notifikasi simulasi lewat logger dan menyimpannya di `outbox`. Kegagalan
satu observer ditangkap di `notify` sehingga tidak mengganggu observer lain. `ScheduleService`
memanggil `notify('SCHEDULE_CHANGED', data)` setelah commit database berhasil, dengan `data['action']`
bernilai `CREATED`, `UPDATED`, atau `DELETED`.

**Result & Reflection.** Notifikasi dikirim setelah commit agar tidak ada pemberitahuan untuk
perubahan yang gagal disimpan. Diuji pada `test_notifications_sent_on_create_update_delete`,
`test_failing_observer_does_not_block_others`, dan `test_old_lecturer_is_notified_when_replaced`.
Sequence diagram tersedia di `README.md`.

---

## Entri 4 - AI Rescheduler (Constraint Satisfaction Problem)

**Objective.** Memberi admin 3 alternatif jadwal bebas bentrok dalam format JSON
`[{hari, jam_mulai, jam_selesai, ruangan, reason}]`.

**Prompt.** Mengikuti prompt Step 3: kapasitas ruangan cukup, tidak bentrok dengan jadwal dosen,
minim gangguan bagi mahasiswa (prioritas pagi/siang).

**Action.** AI memodelkan masalah sebagai CSP. Variabelnya (hari, jam mulai, ruangan); constraint keras
berupa kapasitas, ruangan bebas, dosen bebas, jam operasional, dan sholat Jumat. Constraint lunak
menjadi skor penalti: pagi < siang < sore, hindari jam istirahat, minim pergeseran hari/jam, ruangan
sama, tidak terlalu longgar, dan tidak bentrok dengan mata kuliah lain milik mahasiswa terdaftar
(dari data KRS). Solver memilih 3 saran terbaik dengan (hari, jam) berbeda dan menulis `reason`.

**Result & Reflection.** Penting dicatat bahwa solver ini algoritma deterministik (pencarian atas
domain kecil + ranking), bukan pemanggilan model bahasa saat runtime. Pilihan ini membuat hasilnya
dapat dijelaskan, dapat diuji, dan tidak bergantung pada API eksternal. Diverifikasi di
`test_ai_suggestions_are_valid_conflict_free_and_morning_first` (kapasitas, bebas bentrok, pagi,
alternatif berbeda), `test_ai_never_uses_friday_prayer_time`, dan
`test_ai_returns_empty_when_no_room_fits`. Bobot penalti adalah pilihan desain yang dapat disetel.

---

## Entri 5 - Integrasi invalidasi KRS

**Objective.** Saat jadwal berubah atau bentrok, KRS terdampak kembali dari `APPROVED` ke `REVISION`.

**Prompt.** Mengikuti deliverable 4 pada soal: invalidate KRS yang terpengaruh saat jadwal berubah.

**Action.** AI membuat `KRSIntegration`. Perubahan hari/jam/ruangan/dosen/mata kuliah mengubah status
KRS `APPROVED` dan `SUBMITTED` menjadi `REVISION`; `DRAFT` tetap `DRAFT` tetapi mahasiswanya tetap
diberi notifikasi. Pada bentrok, hanya mahasiswa yang mengambil kedua mata kuliah yang bentrok
yang di-invalidate. Saat jadwal dihapus, KRS menjadi `REVISION` tanpa referensi jadwal.

**Result & Reflection.** Modul KRS aslinya layanan terpisah, sehingga di sini disimulasikan dengan
tabel `krs_enrollments`. Pada sistem nyata integrasi ini berupa panggilan API/event ke layanan KRS.
Diuji di lima test pada bagian "Integrasi KRS".

---

## Verifikasi dan batasan

- Seluruh kode dijalankan dan diuji dengan `pytest` (hasil: semua test lulus).
- Bobot skor AI, definisi `time_overlap`, dan aturan invalidasi `SUBMITTED` adalah keputusan desain
  yang perlu dapat saya jelaskan dan dapat disesuaikan dengan ketentuan dosen pengampu.
- Dashboard admin disediakan sebagai API JSON (`GET /api/conflicts`) dan dokumentasi interaktif
  Swagger di `/docs`; belum berupa antarmuka web.
- Pada produksi, notifikasi perlu dikirim lewat penyedia email/SMS/push sungguhan; di sini disimulasikan
  lewat log sesuai soal.
