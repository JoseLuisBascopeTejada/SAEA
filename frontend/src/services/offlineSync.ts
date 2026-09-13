import {
  confirmAttendance,
  processBurst,
  type ConfirmationItem,
  type ConfirmResult,
  type ProcessBurstOptions,
} from '../api/attendanceClient';
import { ProcessBurstError, type ProcessBurstResult } from '../types/attendance';
import { useAttendanceStore } from '../store/attendanceStore';

/**
 * Offline queue for RF-05 (TSK-404).
 *
 * Queue policy (approved plan):
 * - Queue ONLY on network failure (ProcessBurstError status 0). The fetch
 *   throwing means the request never got a response, which is the only
 *   reliable offline signal (navigator.onLine alone lies behind captive
 *   portals/VPN stalls).
 * - Never auto-queue 400/404/422 (request errors — retrying is wrong) or
 *   500 (ambiguous: a lost response after server-side success would
 *   double-create an attendance_sessions row on retry). Those surface to UI.
 * - Flush order is bursts-first-then-confirms (FIFO by id within a store):
 *   a confirm references a server-issued session_id, so it can only become
 *   valid after its burst has synced.
 * - Terminal (non-zero-status) failures during flush are dropped after being
 *   reported in FlushResult.failed — they can never succeed on retry.
 * - Entries are deleted from IndexedDB immediately after a successful sync
 *   (no lingering photo bytes on device).
 */

export const OFFLINE_DB_NAME = 'saea-offline';
export const BURST_STORE = 'burst_queue';
export const CONFIRM_STORE = 'confirm_queue';

export interface StoredPhoto {
  data: ArrayBuffer;
  type: string;
}

export interface QueuedBurst {
  id?: number;
  kind: 'burst';
  photos: StoredPhoto[];
  courseId: string;
  createdAt: number;
}

export interface QueuedConfirm {
  id?: number;
  kind: 'confirm';
  sessionId: string;
  confirmations: ConfirmationItem[];
  createdAt: number;
}

export interface QueueCounts {
  bursts: number;
  confirms: number;
  total: number;
}

export interface FlushFailure {
  kind: 'burst' | 'confirm';
  id: number;
  status: number;
  detail: string;
}

export interface FlushResult {
  flushedBursts: number;
  flushedConfirms: number;
  failed: FlushFailure[];
  /** True when flush stopped early because the network is still down. */
  aborted: boolean;
}

export type QueueChangeListener = (counts: QueueCounts) => void;

let dbPromise: Promise<IDBDatabase> | null = null;
const listeners = new Set<QueueChangeListener>();

function idbRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error('indexeddb-request-failed'));
  });
}

function openOfflineDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(OFFLINE_DB_NAME, 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(BURST_STORE)) {
        db.createObjectStore(BURST_STORE, { keyPath: 'id', autoIncrement: true });
      }
      if (!db.objectStoreNames.contains(CONFIRM_STORE)) {
        db.createObjectStore(CONFIRM_STORE, { keyPath: 'id', autoIncrement: true });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => {
      dbPromise = null;
      reject(request.error ?? new Error('indexeddb-open-failed'));
    };
  });
  return dbPromise;
}

/** Test hook: close the cached connection so tests can wipe the database. */
export function closeOfflineDb(): void {
  if (dbPromise) {
    void dbPromise.then((db) => db.close()).catch(() => undefined);
    dbPromise = null;
  }
}

async function putRecord(store: string, record: unknown): Promise<number> {
  const db = await openOfflineDb();
  const tx = db.transaction(store, 'readwrite');
  const key = await idbRequest(tx.objectStore(store).add(record));
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error('indexeddb-tx-failed'));
  });
  return key as number;
}

async function getAllRecords<T>(store: string): Promise<T[]> {
  const db = await openOfflineDb();
  const tx = db.transaction(store, 'readonly');
  return idbRequest<T[]>(tx.objectStore(store).getAll());
}

async function deleteRecord(store: string, id: number): Promise<void> {
  const db = await openOfflineDb();
  const tx = db.transaction(store, 'readwrite');
  await idbRequest(tx.objectStore(store).delete(id));
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error('indexeddb-tx-failed'));
  });
}

export async function getQueueCounts(): Promise<QueueCounts> {
  const db = await openOfflineDb();
  // Single multi-store transaction with BOTH requests issued synchronously:
  // IndexedDB auto-commits a transaction once control returns to the event
  // loop with no pending request on it, so awaiting one transaction's request
  // before touching a second transaction throws InvalidStateError in real
  // browsers (fake-indexeddb is lenient here and will not catch a regression).
  // Never split this into two transactions with an await between them.
  const tx = db.transaction([BURST_STORE, CONFIRM_STORE], 'readonly');
  const burstsReq = tx.objectStore(BURST_STORE).count();
  const confirmsReq = tx.objectStore(CONFIRM_STORE).count();
  const [bursts, confirms] = await Promise.all([
    idbRequest<number>(burstsReq),
    idbRequest<number>(confirmsReq),
  ]);
  return { bursts, confirms, total: bursts + confirms };
}

export function subscribeQueueChanges(listener: QueueChangeListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export async function notifyQueueChange(): Promise<QueueCounts> {
  const counts = await getQueueCounts();
  useAttendanceStore.getState().setQueueCounts(counts.bursts, counts.confirms);
  for (const listener of listeners) listener(counts);
  return counts;
}

export async function enqueueBurst(blobs: Blob[], courseId: string): Promise<number> {
  if (blobs.length !== 3) {
    throw new ProcessBurstError(400, `expected 3 photos, got ${blobs.length}`);
  }
  const photos: StoredPhoto[] = await Promise.all(
    blobs.map(async (blob) => ({ data: await blob.arrayBuffer(), type: blob.type })),
  );
  const id = await putRecord(BURST_STORE, {
    kind: 'burst',
    photos,
    courseId,
    createdAt: Date.now(),
  });
  await notifyQueueChange();
  return id;
}

export async function enqueueConfirm(
  sessionId: string,
  confirmations: ConfirmationItem[],
): Promise<number> {
  if (confirmations.length === 0) {
    throw new ProcessBurstError(422, 'confirmations must not be empty');
  }
  const id = await putRecord(CONFIRM_STORE, {
    kind: 'confirm',
    sessionId,
    confirmations,
    createdAt: Date.now(),
  });
  await notifyQueueChange();
  return id;
}

/**
 * Online-first burst submit: tries the real POST, queues on network failure.
 * Resolves with the burst result when online; throws
 * ProcessBurstError(0, 'queued-offline') after queueing when offline.
 */
export async function submitBurstOfflineAware(
  blobs: Blob[],
  courseId: string,
  options?: ProcessBurstOptions,
): Promise<ProcessBurstResult> {
  try {
    const result = await processBurst(blobs, courseId, options);
    useAttendanceStore.getState().setLastResult(result);
    return result;
  } catch (err) {
    if (err instanceof ProcessBurstError && err.status === 0) {
      await enqueueBurst(blobs, courseId);
      throw new ProcessBurstError(0, 'queued-offline');
    }
    throw err;
  }
}

/** Online-first confirm submit: same offline treatment as bursts. */
export async function submitConfirmOfflineAware(
  sessionId: string,
  confirmations: ConfirmationItem[],
  options?: ProcessBurstOptions,
): Promise<ConfirmResult> {
  try {
    return await confirmAttendance(sessionId, confirmations, options);
  } catch (err) {
    if (err instanceof ProcessBurstError && err.status === 0) {
      await enqueueConfirm(sessionId, confirmations);
      throw new ProcessBurstError(0, 'queued-offline');
    }
    throw err;
  }
}

function isNetworkFailure(err: unknown): boolean {
  return err instanceof ProcessBurstError && err.status === 0;
}

/** Drain the queue: bursts first (FIFO), then confirms (FIFO). */
export async function flushQueue(options?: ProcessBurstOptions): Promise<FlushResult> {
  const result: FlushResult = { flushedBursts: 0, flushedConfirms: 0, failed: [], aborted: false };

  const bursts = (await getAllRecords<QueuedBurst>(BURST_STORE)).sort(
    (a, b) => (a.id ?? 0) - (b.id ?? 0),
  );
  for (const item of bursts) {
    try {
      const blobs = item.photos.map((photo) => new Blob([photo.data], { type: photo.type }));
      const burstResult = await processBurst(blobs, item.courseId, options);
      await deleteRecord(BURST_STORE, item.id ?? -1);
      result.flushedBursts += 1;
      useAttendanceStore.getState().setLastResult(burstResult);
    } catch (err) {
      if (isNetworkFailure(err)) {
        result.aborted = true;
        break;
      }
      await deleteRecord(BURST_STORE, item.id ?? -1);
      const failure = err as ProcessBurstError;
      result.failed.push({
        kind: 'burst',
        id: item.id ?? -1,
        status: failure.status ?? -1,
        detail: failure.detail ?? 'unknown',
      });
    }
  }

  if (!result.aborted) {
    const confirms = (await getAllRecords<QueuedConfirm>(CONFIRM_STORE)).sort(
      (a, b) => (a.id ?? 0) - (b.id ?? 0),
    );
    for (const item of confirms) {
      try {
        await confirmAttendance(item.sessionId, item.confirmations, options);
        await deleteRecord(CONFIRM_STORE, item.id ?? -1);
        result.flushedConfirms += 1;
      } catch (err) {
        if (isNetworkFailure(err)) {
          result.aborted = true;
          break;
        }
        await deleteRecord(CONFIRM_STORE, item.id ?? -1);
        const failure = err as ProcessBurstError;
        result.failed.push({
          kind: 'confirm',
          id: item.id ?? -1,
          status: failure.status ?? -1,
          detail: failure.detail ?? 'unknown',
        });
      }
    }
  }

  await notifyQueueChange();
  return result;
}

/**
 * Wire window connectivity events to automatic retry (RF-05).
 * Returns a cleanup function. Safe to call outside a browser (no-op).
 */
export function initOfflineSync(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const onOnline = () => {
    void flushQueue().catch(() => undefined);
  };
  const onOffline = () => {
    void notifyQueueChange().catch(() => undefined);
  };
  window.addEventListener('online', onOnline);
  window.addEventListener('offline', onOffline);
  return () => {
    window.removeEventListener('online', onOnline);
    window.removeEventListener('offline', onOffline);
  };
}
