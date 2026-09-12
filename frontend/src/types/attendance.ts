/** Shared TypeScript interfaces mirroring backend/app/models/schemas.py (TSK-301). */

export type AttendanceStatus = 'PRESENT' | 'ABSENT' | 'LATE';

export type SuggestedStatus = 'PRESENT';

export interface DetectedStudent {
  student_id: string;
  name: string;
  confidence: number;
  suggested_status: SuggestedStatus;
}

export interface ProcessBurstResult {
  session_id: string;
  detected_students: DetectedStudent[];
  unrecognized_count: number;
  processing_time_ms: number;
}

export interface ProcessBurstErrorShape {
  status: number;
  detail: string;
}

export class ProcessBurstError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ProcessBurstError';
    this.status = status;
    this.detail = detail;
  }
}
