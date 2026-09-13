import { describe, expect, it } from 'vitest';
import { registerServiceWorker } from './service-worker';

describe('registerServiceWorker', () => {
  it('no-ops safely where Service Workers are unsupported (jsdom)', () => {
    expect('serviceWorker' in navigator).toBe(false);
    expect(() => registerServiceWorker({ onStatusChange: () => undefined })).not.toThrow();
  });
});
