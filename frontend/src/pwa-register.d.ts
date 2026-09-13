/**
 * Ambient types for vite-plugin-pwa's `virtual:pwa-register` module.
 * Kept in this standalone .d.ts (global script, not a module) because the
 * plugin ships no declarations for the virtual module, and `declare module`
 * augmentation inside service-worker.ts would fail to resolve (TS2664).
 */
declare module 'virtual:pwa-register' {
  export interface RegisterSWOptions {
    immediate?: boolean;
    onNeedRefresh?: () => void;
    onOfflineReady?: () => void;
    onRegistered?: (registration: ServiceWorkerRegistration | undefined) => void;
    onRegisterError?: (error: unknown) => void;
  }
  export function registerSW(
    options?: RegisterSWOptions,
  ): (reloadPage?: boolean) => Promise<void>;
}
