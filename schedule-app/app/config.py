"""Konfigurasi aplikasi Schedule Service.

Semua nilai dapat di-override lewat variabel lingkungan (environment variable).
"""
import os
from dataclasses import dataclass

# Urutan hari dipakai untuk pengurutan deterministik dan menghitung jarak hari.
DAYS = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Schedule Service - Modul Jadwal & Ruangan"
    app_version: str = "1.0.0"
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./schedule.db")
    auto_create_tables: bool = _env_bool("AUTO_CREATE_TABLES", True)
    admin_email: str = os.getenv("ACADEMIC_ADMIN_EMAIL", "akademik@istn.ac.id")

    # Parameter CSP / AI Rescheduler (semua dalam satuan menit sejak 00:00).
    scheduling_days: tuple = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat")
    day_start_minute: int = 7 * 60      # kuliah paling awal 07:00
    day_end_minute: int = 18 * 60       # kuliah harus selesai paling lambat 18:00
    slot_step_minutes: int = 30         # granularitas kandidat jam mulai
    lunch_start: int = 12 * 60          # jam istirahat siang (soft constraint)
    lunch_end: int = 13 * 60
    friday_prayer_start: int = 11 * 60 + 30   # sholat Jumat (hard constraint)
    friday_prayer_end: int = 13 * 60
    max_suggestions: int = 3


settings = Settings()
