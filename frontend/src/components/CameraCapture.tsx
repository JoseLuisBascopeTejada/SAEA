import { useCallback, useEffect, useRef, useState } from 'react';
import { useCamera } from '../hooks/useCamera';

export const BURST_COUNT = 3;
export const BURST_INTERVAL_MS = 500;

type Phase = 'ready' | 'capturing' | 'done';

interface CameraCaptureProps {
  onBurstComplete?: (blobs: Blob[]) => void;
}

const ERROR_MESSAGES: Record<string, string> = {
  'not-supported': 'Camera is not supported in this browser.',
  'permission-denied': 'Camera permission was denied. Allow access and retry.',
  'no-camera': 'No camera was found on this device.',
  unknown: 'Could not start the camera. Retry.',
};

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function CameraCapture({ onBurstComplete }: CameraCaptureProps) {
  const { videoRef, error, isReady, start, captureFrame } = useCamera();
  const [phase, setPhase] = useState<Phase>('ready');
  const [frames, setFrames] = useState<Blob[]>([]);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [previewUrls, setPreviewUrls] = useState<string[]>([]);
  const previewUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    void start();
  }, [start]);

  useEffect(() => {
    const urls = previewUrlsRef.current;
    return () => {
      for (const url of urls) URL.revokeObjectURL(url);
    };
  }, []);

  const replacePreviews = useCallback((blobs: Blob[]) => {
    for (const url of previewUrlsRef.current) URL.revokeObjectURL(url);
    const urls = blobs.map((blob) => URL.createObjectURL(blob));
    previewUrlsRef.current = urls;
    setPreviewUrls(urls);
  }, []);

  const handleCapture = useCallback(async () => {
    setCaptureError(null);
    replacePreviews([]);
    setFrames([]);
    setPhase('capturing');
    try {
      const blobs: Blob[] = [];
      for (let i = 0; i < BURST_COUNT; i += 1) {
        const blob = await captureFrame();
        blobs.push(blob);
        if (i < BURST_COUNT - 1) await delay(BURST_INTERVAL_MS);
      }
      setFrames(blobs);
      replacePreviews(blobs);
      setPhase('done');
      onBurstComplete?.(blobs);
    } catch {
      setCaptureError('Capture failed. Retry.');
      setPhase('ready');
    }
  }, [captureFrame, onBurstComplete, replacePreviews]);

  const handleRetake = useCallback(() => {
    replacePreviews([]);
    setFrames([]);
    setCaptureError(null);
    setPhase('ready');
  }, [replacePreviews]);

  const handleRetry = useCallback(() => {
    void start();
  }, [start]);

  if (error) {
    const message = ERROR_MESSAGES[error] ?? ERROR_MESSAGES.unknown;
    return (
      <div>
        <p role="alert">{message}</p>
        <button type="button" onClick={handleRetry}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <video ref={videoRef} autoPlay playsInline muted data-testid="camera-preview" />
      {captureError && <p role="alert">{captureError}</p>}
      {phase === 'capturing' ? (
        <button type="button" disabled>
          Capturing…
        </button>
      ) : phase === 'done' ? (
        <>
          <div>
            {frames.map((blob, index) => (
              <img
                key={`${index}-${previewUrls[index] ?? blob.size}`}
                src={previewUrls[index]}
                alt={`Captured frame ${index + 1}`}
              />
            ))}
          </div>
          <button type="button" onClick={handleRetake}>
            Retake
          </button>
        </>
      ) : (
        <button type="button" onClick={handleCapture} disabled={!isReady}>
          Capture burst
        </button>
      )}
    </div>
  );
}
