"""Skema awal: rooms, lecturers, schedules, krs_enrollments

Revision ID: 0001_initial_schedule
Revises:
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schedule"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("building", sa.String(length=100), nullable=True),
    )
    op.create_index(op.f("ix_rooms_code"), "rooms", ["code"], unique=True)

    op.create_table(
        "lecturers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nip", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
    )
    op.create_index(op.f("ix_lecturers_nip"), "lecturers", ["nip"], unique=True)

    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_code", sa.String(length=20), nullable=False),
        sa.Column("course_name", sa.String(length=150), nullable=False),
        sa.Column("semester", sa.String(length=20), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("lecturer_id", sa.Integer(), sa.ForeignKey("lecturers.id"), nullable=False),
        sa.Column("enrolled_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_schedules_course_code"), "schedules", ["course_code"])
    op.create_index(op.f("ix_schedules_semester"), "schedules", ["semester"])
    op.create_index(op.f("ix_schedules_day"), "schedules", ["day"])
    op.create_index(op.f("ix_schedules_room_id"), "schedules", ["room_id"])
    op.create_index(op.f("ix_schedules_lecturer_id"), "schedules", ["lecturer_id"])

    op.create_table(
        "krs_enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_nim", sa.String(length=20), nullable=False),
        sa.Column("student_name", sa.String(length=100), nullable=False),
        sa.Column("student_email", sa.String(length=150), nullable=False),
        sa.Column("semester", sa.String(length=20), nullable=False),
        sa.Column("course_code", sa.String(length=20), nullable=False),
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "student_nim", "course_code", "semester", name="uq_krs_student_course_semester"
        ),
    )
    op.create_index(op.f("ix_krs_enrollments_student_nim"), "krs_enrollments", ["student_nim"])
    op.create_index(op.f("ix_krs_enrollments_schedule_id"), "krs_enrollments", ["schedule_id"])
    op.create_index(op.f("ix_krs_enrollments_status"), "krs_enrollments", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_krs_enrollments_status"), table_name="krs_enrollments")
    op.drop_index(op.f("ix_krs_enrollments_schedule_id"), table_name="krs_enrollments")
    op.drop_index(op.f("ix_krs_enrollments_student_nim"), table_name="krs_enrollments")
    op.drop_table("krs_enrollments")

    op.drop_index(op.f("ix_schedules_lecturer_id"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_room_id"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_day"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_semester"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_course_code"), table_name="schedules")
    op.drop_table("schedules")

    op.drop_index(op.f("ix_lecturers_nip"), table_name="lecturers")
    op.drop_table("lecturers")

    op.drop_index(op.f("ix_rooms_code"), table_name="rooms")
    op.drop_table("rooms")
