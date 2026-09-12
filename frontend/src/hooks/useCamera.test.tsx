import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useCamera } from './useCamera';

class FakeTrack {
  stopped = false;
  stop() {
    this.stopped = true;
  }
}

class FakeStream {
  tracks = [new FakeTrack()];
  getTracks() {
    return this.tracks;
  }
}

let frameCounter = 0;
let drawCalls = 0;

function installCanvasMock() {
  drawCalls = 0;
  const originalCreateElement = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation(
    (tagName: string, options?: ElementCreationOptions) => {
      const el = originalCreateElement(tagName, options);
      if (tagName.toLowerCase() === 'canvas') {
        const canvas = el as HTMLCanvasElement;
        vi.spyOn(canvas, 'getContext').mockImplementation(
          () =>
            ({
              drawImage: () => {
                drawCalls += 1;
              },
            }) as unknown as CanvasRenderingContext2D,
        );
        const fallback = canvas as HTMLCanvasElement & {
          convertToBlob?: () => Promise<Blob>;
        };
        fallback.convertToBlob = async () => {
          frameCounter += 1;
          const bytes = new TextEncoder().encode(
            `fake-webp-frame-${frameCounter}-${'x'.repeat(frameCounter * 16)}`,
          );
          return new Blob([bytes.buffer as ArrayBuffer], { type: 'image/webp' });
        };
      }
      return el;
    },
  );
}

function mockGetUserMedia(stream: unknown, impl?: () => Promise<unknown>) {
  const getUserMedia = impl ?? (async () => stream);
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia },
    configurable: true,
    writable: true,
  });
  return getUserMedia;
}

beforeEach(() => {
  frameCounter = 0;
  installCanvasMock();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useCamera', () => {
  it('requests an environment-facing stream and becomes ready', async () => {
    const stream = new FakeStream();
    const getUserMedia = vi.fn(async () => stream);
    mockGetUserMedia(stream, getUserMedia);

    const { result } = renderHook(() => useCamera());
    await act(async () => {
      await result.current.start();
    });

    expect(getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: 'environment' },
      audio: false,
    });
    expect(result.current.error).toBeNull();
    expect(result.current.isReady).toBe(true);
    expect(result.current.stream).toBe(stream);
  });

  it('maps permission denial to an error state instead of throwing', async () => {
    mockGetUserMedia(null, async () => {
      throw new DOMException('denied', 'NotAllowedError');
    });

    const { result } = renderHook(() => useCamera());
    await act(async () => {
      await result.current.start();
    });

    expect(result.current.error).toBe('permission-denied');
    expect(result.current.isReady).toBe(false);
  });

  it('captures a real non-empty webp Blob drawn from the video frame', async () => {
    const stream = new FakeStream();
    mockGetUserMedia(stream);
    const { result } = renderHook(() => useCamera());

    await act(async () => {
      await result.current.start();
    });

    const fakeVideo = {
      videoWidth: 640,
      videoHeight: 480,
    } as HTMLVideoElement;
    act(() => {
      result.current.videoRef.current = fakeVideo;
    });

    let blob: Blob | null = null;
    await act(async () => {
      blob = await result.current.captureFrame();
    });

    expect(blob).toBeInstanceOf(Blob);
    expect(blob!.type).toBe('image/webp');
    expect(blob!.size).toBeGreaterThan(0);
    expect(drawCalls).toBe(1);
    const text = await blob!.text();
    expect(text).toContain('fake-webp-frame-1');
  });

  it('produces distinct bytes for successive frames (animated source)', async () => {
    const stream = new FakeStream();
    mockGetUserMedia(stream);
    const { result } = renderHook(() => useCamera());
    await act(async () => {
      await result.current.start();
    });
    act(() => {
      result.current.videoRef.current = {
        videoWidth: 640,
        videoHeight: 480,
      } as HTMLVideoElement;
    });

    let first: Blob = new Blob();
    let second: Blob = new Blob();
    await act(async () => {
      first = await result.current.captureFrame();
      second = await result.current.captureFrame();
    });

    expect(await first.text()).not.toBe(await second.text());
    expect(second.size).toBeGreaterThan(first.size);
  });
});
