/**
 * Installing grip as an application.
 *
 * Browsers that can install a web application announce it with an event
 * before they show their own prompt. This module keeps that event, so the
 * account menu can offer "Installeer grip" at a moment the person chooses.
 * Where the browser has no such event (Safari) nothing is offered here: the
 * person installs from the browser's own share menu.
 */
import { useSyncExternalStore } from 'react';

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let pending: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();

function changed(): void {
  for (const listener of listeners) listener();
}

export function watchInstallPrompt(): void {
  window.addEventListener('beforeinstallprompt', (event) => {
    // Keep the browser's own banner away; the menu item is the invitation.
    event.preventDefault();
    pending = event as InstallPromptEvent;
    changed();
  });
  window.addEventListener('appinstalled', () => {
    pending = null;
    changed();
  });
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Whether the browser is ready to install grip right now. */
export function useCanInstall(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => pending !== null,
    () => false,
  );
}

export async function install(): Promise<void> {
  const event = pending;
  if (!event) return;
  pending = null;
  changed();
  await event.prompt();
  await event.userChoice.catch(() => undefined);
}
