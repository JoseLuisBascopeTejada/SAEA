import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProcessBurstError } from '../types/attendance';
import { buildProcessBurstFormData, processBurst } from './attendanceClient';

function webpBlob(seed: string): Blob {
  return new Blob([`fake-webp-${seed}`], { type: 'image/webp' });
}

const COURSE_ID = '11111111-1111-4111-8111-111111111111';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('buildProcessBurstFormData', () => {
  it('builds multipart fields photos x3 + course_id', () => {
    const form = buildProcessBurstFormData(
      [webpBlob('a'), webpBlob('b'), webpBlob('c')],
      COURSE_ID,
    );
    expect(form.getAll('photos')).toHaveLength(3);
    expect(form.get('course_id')).toBe(COURSE_ID);
  });

  it('rejects a wrong photo count with the backend literal before fetching', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    expect(() => buildProcessBurstFormData([webpBlob('a')], COURSE_ID)).toThrowError(
      'expected 3 photos, got 1',
    );
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe('processBurst', () => {
  it('POSTs to /attendance/process-burst and returns typed spec-shaped data', async () => {
    const payload = {
      session_id: '22222222-2222-4222-8222-222222222222',
      detected_students: [
        {
          student_id: '33333333-3333-4333-8333-333333333333',
          name: 'Jane Doe',
          confidence: 0.89,
          suggested_status: 'PRESENT',
        },
      ],
      unrecognized_count: 2,
      processing_time_ms: 420,
    };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await processBurst([webpBlob('a'), webpBlob('b'), webpBlob('c')], COURSE_ID, {
      baseUrl: 'http://test/api/v1',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('http://test/api/v1/attendance/process-burst');
    expect(init.method).toBe('POST');
    const body = init.body as FormData;
    expect(body.getAll('photos')).toHaveLength(3);
    expect(body.get('course_id')).toBe(COURSE_ID);

    expect(result.session_id).toBe(payload.session_id);
    expect(result.detected_students).toHaveLength(1);
    expect(result.detected_students[0]?.name).toBe('Jane Doe');
    expect(result.detected_students[0]?.confidence).toBe(0.89);
    expect(result.unrecognized_count).toBe(2);
    expect(result.processing_time_ms).toBe(420);
  });

  it('maps backend error literals without rewording', async () => {
    const cases: Array<{ status: number; detail: string }> = [
      { status: 400, detail: 'expected 3 photos, got 2' },
      { status: 400, detail: 'burst exceeds 8MB total' },
      { status: 400, detail: 'bad photo payload: cannot decode image' },
      { status: 404, detail: 'course not found' },
      { status: 500, detail: 'inference failed' },
    ];
    for (const { status, detail } of cases) {
      vi.stubGlobal(
        'fetch',
        vi.fn(async () => new Response(JSON.stringify({ detail }), { status })),
      );
      try {
        await processBurst([webpBlob('a'), webpBlob('b'), webpBlob('c')], COURSE_ID, {
          baseUrl: 'http://test/api/v1',
        });
        expect.unreachable(`expected throw for ${status} ${detail}`);
      } catch (err) {
        expect(err).toBeInstanceOf(ProcessBurstError);
        expect((err as ProcessBurstError).status).toBe(status);
        expect((err as ProcessBurstError).detail).toBe(detail);
      }
    }
  });

  it('surfaces network failure as status 0', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed');
      }),
    );
    try {
      await processBurst([webpBlob('a'), webpBlob('b'), webpBlob('c')], COURSE_ID, {
        baseUrl: 'http://test/api/v1',
      });
      expect.unreachable('expected network throw');
    } catch (err) {
      expect((err as ProcessBurstError).status).toBe(0);
    }
  });
});
