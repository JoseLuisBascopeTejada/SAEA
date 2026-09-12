import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BURST_INTERVAL_MS, CameraCapture } from './CameraCapture';

class FakeTrack {
  stop() {}
}

class FakeStream {
  getTracks() {
    return [new FakeTrack()];
  }
}

let frameCounter = 0;
const captureTimestamps: number[] = [];

function installCameraMocks() {
  frameCounter = 0;
  captureTimestamps.length = 0;

  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: vi.fn(async () => new FakeStream()),
    },
    configurable: true,
    writable: true,
  });

  window.HTMLMediaElement.prototype.play = vi.fn(async function (
    this: HTMLMediaElement,
  ) {
    return undefined;
  }) as unknown as typeof window.HTMLMediaElement.prototype.play;

  const originalCreateElement = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation(
    (tagName: string, options?: ElementCreationOptions) => {
      const el = originalCreateElement(tagName, options);
      if (tagName.toLowerCase() === 'canvas') {
        const canvas = el as HTMLCanvasElement;
        Object.defineProperty(canvas, 'width', { value: 640, writable: true });
        Object.defineProperty(canvas, 'height', { value: 480, writable: true });
        vi.spyOn(canvas, 'getContext').mockImplementation(
          () =>
            ({
              drawImage: () => {},
            }) as unknown as CanvasRenderingContext2D,
        );
        (
          canvas as HTMLCanvasElement & { convertToBlob?: () => Promise<Blob> }
        ).convertToBlob = async () => {
          captureTimestamps.push(Date.now());
          frameCounter += 1;
          const bytes = new TextEncoder().encode(
            `burst-frame-${frameCounter}-${'y'.repeat(frameCounter * 32)}`,
          );
          return new Blob([bytes.buffer as ArrayBuffer], { type: 'image/webp' });
        };
      }
      return el;
    },
  );

  let urlCounter = 0;
  vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:frame-${(urlCounter += 1)}`);
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
}

beforeEach(() => {
  installCameraMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('CameraCapture burst', () => {
  it('captures exactly 3 webp Blobs ~500ms apart and exposes them via onBurstComplete', async () => {
    const user = userEvent.setup();
    const onBurstComplete = vi.fn();
    render(<CameraCapture onBurstComplete={onBurstComplete} />);

    const captureButton = await screen.findByRole('button', { name: /capture burst/i });
    await waitFor(() => {
      if (captureButton.hasAttribute('disabled')) throw new Error('camera not ready');
    });
    await user.click(captureButton);

    await waitFor(() => expect(onBurstComplete).toHaveBeenCalledTimes(1), {
      timeout: 5000,
    });

    const blobs: Blob[] = onBurstComplete.mock.calls[0][0] as Blob[];
    expect(blobs).toHaveLength(3);
    for (const blob of blobs) {
      expect(blob).toBeInstanceOf(Blob);
      expect(blob.type).toBe('image/webp');
      expect(blob.size).toBeGreaterThan(0);
    }
    const bodies = await Promise.all(blobs.map((b) => b.text()));
    expect(new Set(bodies).size).toBe(3);

    expect(captureTimestamps).toHaveLength(3);
    const gap1 = captureTimestamps[1] - captureTimestamps[0];
    const gap2 = captureTimestamps[2] - captureTimestamps[1];
    expect(gap1).toBeGreaterThanOrEqual(BURST_INTERVAL_MS - 150);
    expect(gap1).toBeLessThan(BURST_INTERVAL_MS + 400);
    expect(gap2).toBeGreaterThanOrEqual(BURST_INTERVAL_MS - 150);
    expect(gap2).toBeLessThan(BURST_INTERVAL_MS + 400);

    expect(await screen.findByAltText('Captured frame 1')).toBeTruthy();
    expect(await screen.findByAltText('Captured frame 3')).toBeTruthy();
    expect(screen.getByRole('button', { name: /retake/i })).toBeTruthy();
  }, 15000);

  it('shows a retry message on permission denial instead of crashing', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: vi.fn(async () => {
          throw new DOMException('denied', 'NotAllowedError');
        }),
      },
      configurable: true,
      writable: true,
    });
    render(<CameraCapture />);

    const alert = await screen.findByRole('alert', {}, { timeout: 5000 });
    expect(alert.textContent ?? '').toMatch(/permission was denied/i);
    expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
  });
});
