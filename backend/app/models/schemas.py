"""Pydantic request/response models for the v1 API (TSK-301)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


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
