import { useCallback, useEffect, useRef, useState } from 'react';

export type CameraError = 'not-supported' | 'permission-denied' | 'no-camera' | 'unknown';

export interface UseCamera {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  stream: MediaStream | null;
  error: CameraError | null;
  isReady: boolean;
  start: () => Promise<void>;
  stop: () => void;
  captureFrame: () => Promise<Blob>;
}

function mapGetUserMediaError(err: unknown): CameraError {
  if (err instanceof DOMException || err instanceof Error) {
    const name = (err as DOMException).name ?? '';
    if (name === 'NotAllowedError' || name === 'SecurityError') return 'permission-denied';
    if (
      name === 'NotFoundError' ||
      name === 'OverconstrainedError' ||
      name === 'DevicesNotFoundError'
    )
      return 'no-camera';
  }
  return 'unknown';
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  const convertToBlob = (
    canvas as HTMLCanvasElement & {
      convertToBlob?: (options?: { type?: string; quality?: number }) => Promise<Blob>;
    }
  ).convertToBlob;
  if (typeof convertToBlob === 'function') {
    return convertToBlob.call(canvas, { type: 'image/webp', quality: 0.85 });
  }
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(blob);
        else reject(new Error('frame-encode-failed'));
      },
      'image/webp',
      0.85,
    );
  });
}

export function useCamera(): UseCamera {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<CameraError | null>(null);
  const [isReady, setIsReady] = useState(false);

  const stop = useCallback(() => {
    setStream((prev) => {
      if (prev) {
        for (const track of prev.getTracks()) track.stop();
      }
      return null;
    });
    const video = videoRef.current;
    if (video) video.srcObject = null;
    setIsReady(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    const mediaDevices = navigator.mediaDevices;
    if (!mediaDevices?.getUserMedia) {
      setError('not-supported');
      setIsReady(false);
      return;
    }
    try {
      const nextStream = await mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
      const video = videoRef.current;
      if (video) {
        video.srcObject = nextStream;
        await video.play().catch(() => undefined);
      }
      setStream(nextStream);
      setIsReady(true);
    } catch (err) {
      setError(mapGetUserMediaError(err));
      setIsReady(false);
    }
  }, []);

  const captureFrame = useCallback(async (): Promise<Blob> => {
    const video = videoRef.current;
    if (!video || !isReady) throw new Error('camera-not-ready');
    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('frame-encode-failed');
    ctx.drawImage(video, 0, 0, width, height);
    return canvasToBlob(canvas);
  }, [isReady]);

  useEffect(() => {
    return () => {
      setStream((prev) => {
        if (prev) {
          for (const track of prev.getTracks()) track.stop();
        }
        return null;
      });
    };
  }, []);

  return { videoRef, stream, error, isReady, start, stop, captureFrame };
}
