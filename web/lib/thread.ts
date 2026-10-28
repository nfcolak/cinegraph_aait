// The ask page keeps its answered questions for the browser tab, so going to a film page and back
// returns to the same thread.
export const THREAD_KEY = "cg-thread";
const MAX_KEPT = 20;

export function loadThread<T>(): T[] {
  try {
    const raw = sessionStorage.getItem(THREAD_KEY);
    const items = raw ? JSON.parse(raw) : [];
    return Array.isArray(items) ? items : [];
  } catch {
    return [];
  }
}

export function saveThread<T>(items: T[]) {
  try {
    if (items.length) sessionStorage.setItem(THREAD_KEY, JSON.stringify(items.slice(-MAX_KEPT)));
    else sessionStorage.removeItem(THREAD_KEY);
  } catch {
    /* storage full or blocked: the thread is only kept in memory */
  }
}

export function hasThread(): boolean {
  try {
    return !!sessionStorage.getItem(THREAD_KEY);
  } catch {
    return false;
  }
}
