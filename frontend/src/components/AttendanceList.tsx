import { useCallback, useState } from 'react';
import type {
  AttendanceStatus,
  DetectedStudent,
  ProcessBurstResult,
} from '../types/attendance';

const STATUS_CYCLE: AttendanceStatus[] = ['PRESENT', 'ABSENT', 'LATE'];

function nextStatus(current: AttendanceStatus): AttendanceStatus {
  const index = STATUS_CYCLE.indexOf(current);
  return STATUS_CYCLE[(index + 1) % STATUS_CYCLE.length] as AttendanceStatus;
}

interface AttendanceListProps {
  result: ProcessBurstResult;
  onStatusesChange?: (statuses: Record<string, AttendanceStatus>) => void;
}

/**
 * Presentational list of detected students (RF-04 adjustments only).
 * Toggles are local state — this component never POSTs /attendance/confirm.
 */
export function AttendanceList({ result, onStatusesChange }: AttendanceListProps) {
  const [overrides, setOverrides] = useState<Record<string, AttendanceStatus>>({});

  const statusOf = useCallback(
    (student: DetectedStudent): AttendanceStatus =>
      overrides[student.student_id] ?? student.suggested_status,
    [overrides],
  );

  const handleToggle = useCallback(
    (student: DetectedStudent) => {
      setOverrides((prev) => {
        const current = prev[student.student_id] ?? student.suggested_status;
        const updated = { ...prev, [student.student_id]: nextStatus(current) };
        onStatusesChange?.(updated);
        return updated;
      });
    },
    [onStatusesChange],
  );

  if (result.detected_students.length === 0) {
    return (
      <div>
        <p>No students recognized.</p>
        <p>Unrecognized faces: {result.unrecognized_count}</p>
      </div>
    );
  }

  return (
    <div>
      <ul>
        {result.detected_students.map((student) => (
          <li key={student.student_id}>
            <span>{student.name}</span>
            <span>{student.confidence.toFixed(2)}</span>
            <button type="button" onClick={() => handleToggle(student)}>
              {statusOf(student)}
            </button>
          </li>
        ))}
      </ul>
      <p>Unrecognized faces: {result.unrecognized_count}</p>
      <p>Processing time: {result.processing_time_ms}ms</p>
    </div>
  );
}
