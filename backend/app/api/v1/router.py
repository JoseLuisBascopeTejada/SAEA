"""v1 API router aggregation (TSK-301)."""

from fastapi import APIRouter

from app.api.v1.endpoints import attendance, students

router = APIRouter(prefix="/api/v1")
router.include_router(attendance.router, tags=["attendance"])
router.include_router(students.router, tags=["students"])
