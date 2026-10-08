/**
 * Notifications on this device: asking the browser, registering the device
 * with grip, and the person's preference.
 *
 * The browser's permission is asked only from a button the person presses,
 * never on load. A device is this browser's subscription at its vendor's
 * push service; grip keeps it to send to, and never shows it back.
 */
import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client';

export interface Device {
  id: string;
  label: string;
  created_at: string;
  last_success_at: string | null;
}

export interface Preference {
  push: boolean;
  mail_summary: boolean;
  tasks: boolean;
  overdue: boolean;
  decisions: boolean;
  quiet_from: string | null;
  quiet_until: string | null;
  weekends_quiet: boolean;
}

export interface Notifications {
  /** False where the instance cannot send notifications at all. */
  available: boolean;
  public_key: string | null;
  daily_cap: number;
  mail_summary_available: boolean;
  preference: Preference;
  devices: Device[];
}

export type PreferenceChange = Partial<Preference> & { quiet?: boolean };

export const NOTIFICATIONS_KEY = ['notifications'] as const;

export function fetchNotifications(): Promise<Notifications> {
  return apiGet<Notifications>('/api/notifications');
}

export function savePreference(change: PreferenceChange): Promise<Preference> {
  return apiPut<Preference>('/api/notifications/preference', change);
}

export function removeDevice(id: string): Promise<void> {
  return apiDelete(`/api/notifications/devices/${id}`);
}

export function sendTest(): Promise<unknown> {
  return apiPost('/api/notifications/test');
}

/**
 * Where this browser stands:
 * - `unsupported`: it cannot receive notifications at all;
 * - `needs-install`: an iPhone or iPad, where it only works from the home screen;
 * - `no-worker`: the application runs without its service worker (development);
 * - `denied`: the person said no in the browser; only the browser can undo that;
 * - `off`: possible, not switched on here;
 * - `on`: this browser is subscribed.
 */
export type BrowserState = 'unsupported' | 'needs-install' | 'no-worker' | 'denied' | 'off' | 'on';

function isAppleMobile(): boolean {
  const agent = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(agent) || (agent.includes('Mac') && navigator.maxTouchPoints > 1);
}

function isStandalone(): boolean {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches === true ||
    (navigator as { standalone?: boolean }).standalone === true
  );
}

async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null;
  return (await navigator.serviceWorker.getRegistration()) ?? null;
}

export async function browserState(): Promise<BrowserState> {
  const supported =
    'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  if (!supported) return isAppleMobile() && !isStandalone() ? 'needs-install' : 'unsupported';
  if (Notification.permission === 'denied') return 'denied';
  const worker = await registration();
  if (!worker) return 'no-worker';
  const subscription = await worker.pushManager.getSubscription();
  return subscription && Notification.permission === 'granted' ? 'on' : 'off';
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes;
}

/** Which device of the list this browser is, remembered in this browser only. */
const DEVICE_KEY = 'grip_push_device';

export function thisDeviceId(): string | null {
  try {
    return localStorage.getItem(DEVICE_KEY);
  } catch {
    return null;
  }
}

function rememberDevice(id: string | null): void {
  try {
    if (id) localStorage.setItem(DEVICE_KEY, id);
    else localStorage.removeItem(DEVICE_KEY);
  } catch {
    // Without storage the list simply does not mark this device.
  }
}

async function register(subscription: PushSubscription, label: string): Promise<Device> {
  const json = subscription.toJSON();
  const device = await apiPost<Device>('/api/notifications/devices', {
    endpoint: json.endpoint,
    keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth },
    label,
  });
  rememberDevice(device.id);
  return device;
}

/**
 * Switch notifications on for this browser. Call it from a button: this is
 * where the browser asks the person. Resolves to the state afterwards.
 */
export async function switchOn(publicKey: string, label: string): Promise<BrowserState> {
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return permission === 'denied' ? 'denied' : 'off';
  const worker = await registration();
  if (!worker) return 'no-worker';
  const subscription =
    (await worker.pushManager.getSubscription()) ??
    (await worker.pushManager.subscribe({
      // Every push shows a notification; browsers require the promise.
      userVisibleOnly: true,
      applicationServerKey: keyBytes(publicKey),
    }));
  await register(subscription, label);
  return 'on';
}

/** Switch notifications off for this browser, and forget it at grip. */
export async function switchOff(): Promise<void> {
  const id = thisDeviceId();
  if (id) await removeDevice(id).catch(() => undefined);
  rememberDevice(null);
  const worker = await registration();
  const subscription = await worker?.pushManager.getSubscription();
  await subscription?.unsubscribe().catch(() => undefined);
}

/**
 * The browser may have replaced its subscription since the last visit. When
 * it differs from what grip was last told, tell grip again.
 */
const ENDPOINT_KEY = 'grip_push_endpoint';

export async function keepInStep(): Promise<void> {
  try {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    const worker = await registration();
    const subscription = await worker?.pushManager.getSubscription();
    if (!subscription || !thisDeviceId()) return;
    if (localStorage.getItem(ENDPOINT_KEY) === subscription.endpoint) return;
    await register(subscription, '');
    localStorage.setItem(ENDPOINT_KEY, subscription.endpoint);
  } catch {
    // Not in step this time; the next visit tries again.
  }
}

/** Tell the worker how many tasks are the person's to do: the icon's number. */
export async function showTaskCount(count: number): Promise<void> {
  try {
    const worker = await registration();
    worker?.active?.postMessage({ type: 'tasks', count });
    if (!worker && 'setAppBadge' in navigator) {
      const badge = navigator as Navigator & {
        setAppBadge: (count: number) => Promise<void>;
        clearAppBadge: () => Promise<void>;
      };
      await (count > 0 ? badge.setAppBadge(count) : badge.clearAppBadge());
    }
  } catch {
    // A number on an icon is a nicety.
  }
}
