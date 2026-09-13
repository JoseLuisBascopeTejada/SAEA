/**
 * Thin service-worker REGISTRATION wrapper (TSK-404, approved plan iii).
 *
 * The actual service worker is generated at build time by vite-plugin-pwa in
 * its default generateSW (Workbox) mode — see vite.config.ts. This file does
 * NOT hand-roll fetch handlers or precache lists (that would duplicate the
 * plugin); it only registers the generated worker and surfaces update status.
 * Offline capture/confirm queueing lives in services/offlineSync.ts (app
 * thread), not in the worker.
 */

export type ServiceWorkerStatus = 'idle' | 'need-refresh' | 'offline-ready';

export interface RegisterServiceWorkerOptions {
  onStatusChange?: (status: ServiceWorkerStatus) => void;
}

/**
 * Register the plugin-generated service worker. No-ops when Service Workers
 * are unsupported, in dev (the plugin only emits a worker for builds unless
 * devOptions are enabled), or outside a browser (e.g. vitest runs where the
 * virtual module cannot resolve — the dynamic import rejects and is caught).
 */
export function registerServiceWorker(options?: RegisterServiceWorkerOptions): void {
  if (typeof window === 'undefined') return;
  if (!('serviceWorker' in navigator)) return;
  if (import.meta.env.DEV) return;
  void import('virtual:pwa-register')
    .then(({ registerSW }) => {
      registerSW({
        onNeedRefresh() {
          options?.onStatusChange?.('need-refresh');
        },
        onOfflineReady() {
          options?.onStatusChange?.('offline-ready');
        },
      });
    })
    .catch(() => undefined);
}
