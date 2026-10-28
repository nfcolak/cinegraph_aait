import { useSyncExternalStore } from "react";

// The image behind the page. A page sets the URL of the film or person it shows; the shell's ambient field
// crossfades to it. Pages clear it (setBackdrop(null)) when they unmount.

let current: string | null = null;
const listeners = new Set<() => void>();

export function setBackdrop(url: string | null): void {
  if (url === current) return;
  current = url;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useBackdrop(): string | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}
