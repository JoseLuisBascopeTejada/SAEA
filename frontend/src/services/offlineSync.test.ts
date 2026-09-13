import 'fake-indexeddb/auto';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProcessBurstError } from '../types/attendance';
import { useAttendanceStore } from '../store/attendanceStore';
import {
  closeOfflineDb,
  flushQueue,
  getQueueCounts,
  initOfflineSync,
  OFFLINE_DB_NAME,
  submitBurstOfflineAware,
  submitConfirmOfflineAware,
  subscribeQueueChanges,
} from './offlineSync';

const COURSE_ID = '11111111-1111-4111-8111-111111111111';
const SESSION_ID = '22222222-2222-4222-8222-222222222222';

function webpBlobs(): Blob[] {
  return [0, 1, 2].map((i) => new Blob([`offline-frame-${i}`], { type: 'image/webp' }));
}

const BURST_RESULT = {
  session_id: SESSION_ID,
  detected_students: [
    {
      student_id: '33333333-3333-4333-8333-333333333333',
      name: 'Jane Doe',
      confidence: 0.89,
      suggested_status: 'PRESENT',
    },
  ],
  unrecognized_count: 1,
  processing_time_ms: 410,
};

async function blobTexts(blobs: Blob[]): Promise<string[]> {
  return Promise.all(blobs.map((b) => b.text()));
}

afterEach(async () => {
  vi.unstubAllGlobals();
  closeOfflineDb();
  await new Promise<void>((resolve) => {
    const req = indexedDB.deleteDatabase(OFFLINE_DB_NAME);
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
    req.onblocked = () => resolve();
  });
  useAttendanceStore.getState().setQueueCounts(0, 0);
  useAttendanceStore.getState().setLastResult(null);
});

describe('offlineSync burst queue', () => {
  it('submits online without queueing and records the result in the store', async () => {
    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify(BURST_RESULT), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await submitBurstOfflineAware(webpBlobs(), COURSE_ID, {
      baseUrl: 'http://test/api/v1',
    });

    expect(result.session_id).toBe(SESSION_ID);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(await getQueueCounts()).toEqual({ bursts: 0, confirms: 0, total: 0 });
    expect(useAttendanceStore.getState().lastResult?.session_id).toBe(SESSION_ID);
  });

  it('queues photo bytes on network failure and replays identical bytes on flush', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    const originals = webpBlobs();

    try {
      await submitBurstOfflineAware(originals, COURSE_ID, { baseUrl: 'http://test/api/v1' });
      expect.unreachable('expected queued-offline throw');
    } catch (err) {
      expect((err as ProcessBurstError).detail).toBe('queued-offline');
    }
    expect(await getQueueCounts()).toEqual({ bursts: 1, confirms: 0, total: 1 });
    expect(useAttendanceStore.getState().queuedBursts).toBe(1);

    let replayed: Blob[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        const form = init?.body as FormData;
        replayed = form.getAll('photos') as Blob[];
        return new Response(JSON.stringify(BURST_RESULT), { status: 200 });
      }),
    );
    const flush = await flushQueue({ baseUrl: 'http://test/api/v1' });

    expect(flush).toEqual({ flushedBursts: 1, flushedConfirms: 0, failed: [], aborted: false });
    expect(await blobTexts(replayed)).toEqual(await blobTexts(originals));
    expect(await getQueueCounts()).toEqual({ bursts: 0, confirms: 0, total: 0 });
    expect(useAttendanceStore.getState().queuedBursts).toBe(0);
  });

  it('auto-flushes when a mocked back-online event fires', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    await submitBurstOfflineAware(webpBlobs(), COURSE_ID, {
      baseUrl: 'http://test/api/v1',
    }).catch(() => undefined);
    expect((await getQueueCounts()).bursts).toBe(1);

    const fetchMock = vi.fn(
      async () => new Response(JSON.stringify(BURST_RESULT), { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const cleanup = initOfflineSync();
    try {
      window.dispatchEvent(new Event('online'));
      await vi.waitFor(async () => {
        expect((await getQueueCounts()).bursts).toBe(0);
      });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    } finally {
      cleanup();
    }
  });

  it('aborts flush while still offline and keeps the entry', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    await submitBurstOfflineAware(webpBlobs(), COURSE_ID, {
      baseUrl: 'http://test/api/v1',
    }).catch(() => undefined);

    const flush = await flushQueue({ baseUrl: 'http://test/api/v1' });
    expect(flush.aborted).toBe(true);
    expect(flush.flushedBursts).toBe(0);
    expect((await getQueueCounts()).bursts).toBe(1);
  });

  it('drops terminal HTTP failures with their literal detail instead of requeueing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    await submitBurstOfflineAware(webpBlobs(), COURSE_ID, {
      baseUrl: 'http://test/api/v1',
    }).catch(() => undefined);

    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () => new Response(JSON.stringify({ detail: 'course not found' }), { status: 404 }),
      ),
    );
    const flush = await flushQueue({ baseUrl: 'http://test/api/v1' });

    expect(flush.aborted).toBe(false);
    expect(flush.failed).toEqual([
      { kind: 'burst', id: expect.any(Number), status: 404, detail: 'course not found' },
    ]);
    expect(await getQueueCounts()).toEqual({ bursts: 0, confirms: 0, total: 0 });
  });
});

describe('offlineSync confirm queue', () => {
  const confirmations = [
    { student_id: '33333333-3333-4333-8333-333333333333', status: 'PRESENT' as const },
  ];

  it('queues a confirm offline and replays the exact JSON payload online', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    try {
      await submitConfirmOfflineAware(SESSION_ID, confirmations, {
        baseUrl: 'http://test/api/v1',
      });
      expect.unreachable('expected queued-offline throw');
    } catch (err) {
      expect((err as ProcessBurstError).detail).toBe('queued-offline');
    }
    expect(await getQueueCounts()).toEqual({ bursts: 0, confirms: 1, total: 1 });

    let seenUrl = '';
    let seenBody: unknown = null;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        seenUrl = url;
        seenBody = JSON.parse(init?.body as string) as unknown;
        return new Response(
          JSON.stringify({ saved: true, attendance_record_ids: ['r1'] }),
          { status: 200 },
        );
      }),
    );
    const flush = await flushQueue({ baseUrl: 'http://test/api/v1' });

    expect(flush.flushedConfirms).toBe(1);
    expect(seenUrl).toBe('http://test/api/v1/attendance/confirm');
    expect(seenBody).toEqual({ session_id: SESSION_ID, confirmations });
    expect(await getQueueCounts()).toEqual({ bursts: 0, confirms: 0, total: 0 });
  });

  it('flushes bursts before confirms', async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    await submitConfirmOfflineAware(SESSION_ID, confirmations, {
      baseUrl: 'http://test/api/v1',
    }).catch(() => undefined);
    await submitBurstOfflineAware(webpBlobs(), COURSE_ID, {
      baseUrl: 'http://test/api/v1',
    }).catch(() => undefined);

    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        urls.push(url);
        const isConfirm = url.endsWith('/attendance/confirm');
        return new Response(
          JSON.stringify(
            isConfirm
              ? { saved: true, attendance_record_ids: ['r1'] }
              : BURST_RESULT,
          ),
          { status: 200 },
        );
      }),
    );
    const flush = await flushQueue({ baseUrl: 'http://test/api/v1' });

    expect(flush.flushedBursts).toBe(1);
    expect(flush.flushedConfirms).toBe(1);
    expect(urls).toEqual([
      'http://test/api/v1/attendance/process-burst',
      'http://test/api/v1/attendance/confirm',
    ]);
  });

  it('notifies queue-change subscribers and the store on every mutation', async () => {
    const seen: Array<{ bursts: number; confirms: number; total: number }> = [];
    const unsubscribe = subscribeQueueChanges((counts) => {
      seen.push(counts);
    });
    try {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => {
          throw new TypeError('fetch failed');
        }),
      );
      await submitBurstOfflineAware(webpBlobs(), COURSE_ID, {
        baseUrl: 'http://test/api/v1',
      }).catch(() => undefined);
      expect(seen.at(-1)).toEqual({ bursts: 1, confirms: 0, total: 1 });
      expect(useAttendanceStore.getState().queuedBursts).toBe(1);
    } finally {
      unsubscribe();
    }
  });
});
