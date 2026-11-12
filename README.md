# Backend Sistem Penjadwalan Kuliah & Ruangan FastAPI

Repository ini berisi modul sistem penjadwalan kuliah dengan deteksi bentrok otomatis dan arsitektur *Observer Pattern*, dikembangkan untuk memenuhi tugas mata kuliah Dasar-dasar Komputasi Awan dan Terdistribusi.

## Identitas Penyusun
- **Nama:** Nabila Latifatul Hamdah
- **NIM:** 24360006
- **Institusi:** Institut Sains dan Teknologi Nasional (ISTN) Jakarta

## Fitur Utama
1. **3D Conflict Detection Algorithm:** Deteksi otomatis bentrok waktu, ruangan (*room conflict*), dosen (*lecturer conflict*), serta validasi kapasitas ruangan terhadap jumlah mahasiswa terdaftar[cite: 8].
2. **Observer Pattern (Pub-Sub Notification):** Sistem pengiriman notifikasi otomatis kepada Mahasiswa, Dosen, dan Admin Akademik ketika jadwal mengalami perubahan[cite: 8].
3. **AI-Powered Rescheduler:** Asisten rekomendasi alternatif jadwal pengganti bebas bentrok berbasis Constraint Satisfaction Problem (CSP)[cite: 8, 10].
4. **Integrasi KRS:** Otomatis melakukan invalidasi status KRS mahasiswa yang terdampak jika terjadi perubahan jadwal kuliah[cite: 8].

## Cara Menjalankan Proyek

1. **Clone repository ini:**
   ```bash
   git clone [https://github.com/username/fastapi-schedule-system.git](https://github.com/username/fastapi-schedule-system.git)
   cd fastapi-schedule-system
