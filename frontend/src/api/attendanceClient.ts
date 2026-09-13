import {
  ProcessBurstError,
  type AttendanceStatus,
  type ProcessBurstResult,
} from '../types/attendance';

/**
 * Field names verified against
 * backend/app/api/v1/endpoints/attendance.py::process_burst:
 *   photos: list[UploadFile] = File(...)
 *   course_id: UUID = Form(...)
 */
export const PROCESS_BURST_PATH = '/attendance/process-burst';

export const EXPECTED_PHOTOS = 3;

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';
}

/** Pure FormData builder — shared by processBurst and unit tests. */
export function buildProcessBurstFormData(blobs: Blob[], courseId: string): FormData {
  if (blobs.length !== EXPECTED_PHOTOS) {
    // Mirrors backend literal: f"expected 3 photos, got {len(photos)}"
    throw new ProcessBurstError(400, `expected 3 photos, got ${blobs.length}`);
  }
  const form = new FormData();
  blobs.forEach((blob, index) => {
    form.append('photos', blob, `photo-${index + 1}.webp`);
  });
  form.append('course_id', courseId);
  return form;
}

function extractDetail(body: unknown, fallback: string): string {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    return JSON.stringify(detail);
  }
  return fallback;
}

export interface ProcessBurstOptions {
  baseUrl?: string;
}

/**
 * POSTs a 3-photo burst to the real backend and returns the typed
 * ProcessBurstResponse. Throws ProcessBurstError carrying the backend's
 * literal `detail` string for known statuses:
 *   400 "expected 3 photos, got N" / "burst exceeds 8MB total" /
 *       "bad photo payload: ..." (backend f"bad photo payload: {exc}")
 *   404 "course not found"
 *   500 "inference failed"
 *   422 validation detail passthrough
 * Network-level failure surfaces as status 0 (no backend literal exists).
 */
export async function processBurst(
  blobs: Blob[],
  courseId: string,
  options?: ProcessBurstOptions,
): Promise<ProcessBurstResult> {
  const form = buildProcessBurstFormData(blobs, courseId);
  const baseUrl = options?.baseUrl ?? getApiBaseUrl();
  let res: Response;
  try {
    res = await fetch(`${baseUrl}${PROCESS_BURST_PATH}`, {
      method: 'POST',
      body: form,
    });
  } catch {
    throw new ProcessBurstError(0, 'network-unavailable');
  }
  if (res.ok) return (await res.json()) as ProcessBurstResult;
  let detail: string;
  try {
    const parsed: unknown = await res.json();
    detail = extractDetail(parsed, `request failed: ${res.status}`);
  } catch {
    detail = `request failed: ${res.status}`;
  }
  throw new ProcessBurstError(res.status, detail);
}

export const CONFIRM_PATH = '/attendance/confirm';

export interface ConfirmationItem {
  student_id: string;
  status: AttendanceStatus;
}

export interface ConfirmResult {
  saved: boolean;
  attendance_record_ids: string[];
}

/**
 * POSTs teacher-confirmed attendance (spec.md §3 confirm shape).
 * Throws ProcessBurstError carrying the backend's literal `detail`:
 *   404 "session not found" / "student not found"
 *   409 "session already confirmed"
 *   422 validation detail passthrough (incl. empty `confirmations`)
 *   500 "inference failed" (generic message only, per spec.md §3)
 * Network-level failure surfaces as status 0.
 * Added for TSK-404 option A (offline retry of confirmed attendance, RF-05).
 */
export async function confirmAttendance(
  sessionId: string,
  confirmations: ConfirmationItem[],
  options?: ProcessBurstOptions,
): Promise<ConfirmResult> {
  if (confirmations.length === 0) {
    throw new ProcessBurstError(422, 'confirmations must not be empty');
  }
  const baseUrl = options?.baseUrl ?? getApiBaseUrl();
  let res: Response;
  try {
    res = await fetch(`${baseUrl}${CONFIRM_PATH}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, confirmations }),
    });
  } catch {
    throw new ProcessBurstError(0, 'network-unavailable');
  }
  if (res.ok) return (await res.json()) as ConfirmResult;
  let detail: string;
  try {
    const parsed: unknown = await res.json();
    detail = extractDetail(parsed, `request failed: ${res.status}`);
  } catch {
    detail = `request failed: ${res.status}`;
  }
  throw new ProcessBurstError(res.status, detail);
}
