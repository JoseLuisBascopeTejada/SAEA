import { create } from 'zustand';
import type { ProcessBurstResult } from '../types/attendance';

/**
 * Minimal Zustand store shell (TSK-404 scope addition — see tasks.md).
 * Binding decision: architecture.md ("State management decision").
 * Holds only queue-related state so offlineSync's queue-change seam has
 * somewhere to live. Full app UI state is explicitly out of scope.
 */
interface AttendanceStoreState {
  queuedBursts: number;
  queuedConfirms: number;
  lastResult: ProcessBurstResult | null;
  setQueueCounts: (bursts: number, confirms: number) => void;
  setLastResult: (result: ProcessBurstResult | null) => void;
}

export const useAttendanceStore = create<AttendanceStoreState>()((set) => ({
  queuedBursts: 0,
  queuedConfirms: 0,
  lastResult: null,
  setQueueCounts: (bursts, confirms) =>
    set({ queuedBursts: bursts, queuedConfirms: confirms }),
  setLastResult: (result) => set({ lastResult: result }),
}));
