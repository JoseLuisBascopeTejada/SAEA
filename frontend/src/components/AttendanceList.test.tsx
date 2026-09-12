import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ProcessBurstResult } from '../types/attendance';
import { AttendanceList } from './AttendanceList';

const RESULT: ProcessBurstResult = {
  session_id: '22222222-2222-4222-8222-222222222222',
  detected_students: [
    {
      student_id: '33333333-3333-4333-8333-333333333333',
      name: 'Jane Doe',
      confidence: 0.89,
      suggested_status: 'PRESENT',
    },
    {
      student_id: '44444444-4444-4444-8444-444444444444',
      name: 'John Smith',
      confidence: 0.71,
      suggested_status: 'PRESENT',
    },
  ],
  unrecognized_count: 2,
  processing_time_ms: 420,
};

describe('AttendanceList', () => {
  it('renders real student names, confidences, and counts from the result', () => {
    render(<AttendanceList result={RESULT} />);
    expect(screen.getByText('Jane Doe')).toBeTruthy();
    expect(screen.getByText('John Smith')).toBeTruthy();
    expect(screen.getByText('0.89')).toBeTruthy();
    expect(screen.getByText('0.71')).toBeTruthy();
    expect(screen.getByText(/unrecognized faces: 2/i)).toBeTruthy();
    expect(screen.getByText(/processing time: 420ms/i)).toBeTruthy();
  });

  it('cycles PRESENT -> ABSENT -> LATE -> PRESENT and reports the change', async () => {
    const user = userEvent.setup();
    const onStatusesChange = vi.fn();
    render(<AttendanceList result={RESULT} onStatusesChange={onStatusesChange} />);

    const toggle = screen.getAllByRole('button')[0] as HTMLButtonElement;
    expect(toggle.textContent).toBe('PRESENT');

    await user.click(toggle);
    expect(toggle.textContent).toBe('ABSENT');
    await user.click(toggle);
    expect(toggle.textContent).toBe('LATE');
    await user.click(toggle);
    expect(toggle.textContent).toBe('PRESENT');

    expect(onStatusesChange).toHaveBeenLastCalledWith({
      '33333333-3333-4333-8333-333333333333': 'PRESENT',
    });
  });

  it('renders an empty state when nobody was recognized', () => {
    render(
      <AttendanceList
        result={{ ...RESULT, detected_students: [], unrecognized_count: 3 }}
      />,
    );
    expect(screen.getByText(/no students recognized/i)).toBeTruthy();
  });
});
