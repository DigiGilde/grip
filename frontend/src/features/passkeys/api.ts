/**
 * Passkeys: a person's own keys, logging in with one, and confirming a
 * decision with one. The ceremonies with the device run through
 * @simplewebauthn/browser, which turns the server's options into what
 * navigator.credentials wants and its answer back into JSON.
 */
import { startAuthentication, startRegistration } from '@simplewebauthn/browser';
import { apiDelete, apiGet, apiPost } from '@/api/client';

export interface Passkey {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
  device_type: string | null;
  backed_up: boolean | null;
}

export interface PasskeyList {
  /** False where the instance has no passkeys set up. */
  available: boolean;
  /** Whether a passkey alone can log in here. */
  login_enabled: boolean;
  login_max_age_days: number;
  /** False in a session that began with a passkey: a new one needs the ordinary login. */
  may_register: boolean;
  items: Passkey[];
}

interface Options {
  options_json: string;
}

export const PASSKEYS_KEY = ['passkeys'] as const;

export function fetchPasskeys(): Promise<PasskeyList> {
  return apiGet<PasskeyList>('/api/passkeys');
}

export function revokePasskey(id: string): Promise<void> {
  return apiDelete(`/api/passkeys/${id}`);
}

/** Whether this browser can work with passkeys at all. */
export function passkeysSupported(): boolean {
  return typeof window !== 'undefined' && typeof window.PublicKeyCredential === 'function';
}

/** True when the person closed the device's prompt; that is not an error to show. */
export function isCancellation(error: unknown): boolean {
  return (
    error instanceof Error && (error.name === 'NotAllowedError' || error.name === 'AbortError')
  );
}

export async function registerPasskey(label: string): Promise<Passkey> {
  const { options_json } = await apiPost<Options>('/api/passkeys/register/options');
  const credential = await startRegistration({ optionsJSON: JSON.parse(options_json) });
  const passkey = await apiPost<Passkey>('/api/passkeys/register/verify', {
    credential: JSON.stringify(credential),
    label,
  });
  rememberPasskeyHere();
  return passkey;
}

export async function loginWithPasskey(): Promise<void> {
  const { options_json } = await apiPost<Options>('/api/auth/passkey/options');
  const credential = await startAuthentication({ optionsJSON: JSON.parse(options_json) });
  await apiPost('/api/auth/passkey/verify', { credential: JSON.stringify(credential) });
}

/**
 * That a passkey was once made in this browser. Only a hint for the login
 * page, so it does not offer a passkey to someone who never made one; it
 * says nothing about who, and the server never reads it.
 */
const HINT_KEY = 'grip_passkey_here';

function rememberPasskeyHere(): void {
  try {
    localStorage.setItem(HINT_KEY, '1');
  } catch {
    // Without storage the login page simply does not offer the passkey.
  }
}

export function passkeyMadeHere(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) === '1';
  } catch {
    return false;
  }
}

/** What an intent says about confirming it with a passkey; null when it cannot. */
export interface PasskeyStep {
  options_url: string;
  verify_url: string;
}

/**
 * Confirm a decision with a passkey, before leaving for the identity
 * provider. An addition to the proof, never a condition: without a passkey,
 * when the person closes the prompt or when the device fails, this resolves
 * to false and the decision goes on exactly as without one.
 */
export async function confirmWithPasskey(step: PasskeyStep | null | undefined): Promise<boolean> {
  if (!step || !passkeysSupported()) return false;
  try {
    const { options_json } = await apiPost<Options>(step.options_url);
    const credential = await startAuthentication({ optionsJSON: JSON.parse(options_json) });
    await apiPost(step.verify_url, { credential: JSON.stringify(credential) });
    return true;
  } catch {
    return false;
  }
}
