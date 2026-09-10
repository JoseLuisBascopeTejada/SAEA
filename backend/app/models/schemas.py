"""Pydantic request/response models for the v1 API (TSK-301/TSK-302)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class DetectedStudent(BaseModel):
    student_id: UUID
    name: str
    confidence: float
    suggested_status: Literal["PRESENT"]


class ProcessBurstResponse(BaseModel):
    session_id: UUID
    detected_students: list[DetectedStudent]
    unrecognized_count: int
    processing_time_ms: int


AttendanceStatus = Literal["PRESENT", "ABSENT", "LATE"]


class ConfirmationItem(BaseModel):
    student_id: UUID
    status: AttendanceStatus


class ConfirmRequest(BaseModel):
    session_id: UUID
    confirmations: list[ConfirmationItem] = Field(min_length=1)


class ConfirmResponse(BaseModel):
    saved: bool
    attendance_record_ids: list[UUID]
