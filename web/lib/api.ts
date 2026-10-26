export type Route = "factual" | "prediction" | "recommendation" | "multimedia";

export interface EntityCard {
  qid: string | null;
  label: string;
  imdb?: string | null;
  image: string | null;
  backdrop?: string | null;
  type?: "film" | "person" | "other";
  year?: string | null;
  directors?: string[];
  genres?: string[];
  rating?: number | null;
}

export interface Reply {
  message: string;
  answer: string;
  ok: boolean;
  note: string | null;
  hint: string | null;
  suggestions: FilmRow[];
  suggestions_title: string;
  route: Route;
  image: { url: string; kind: "poster" | "profile" | "scene"; label: string | null } | null;
  subject: EntityCard | null;
  relation: string | null;
  property: string | null;
  inverse: boolean;
  objects: string[];
  count: number;
  cards: EntityCard[];
  seeds: EntityCard[];
  rewritten: string | null;
  sparql: string | null;
  trace: string[];
  latency_ms: number;
}

export interface Health {
  status: "ready" | "loading";
  triples: number;
  entities: number;
  embeddings: boolean;
  load_seconds: number;
}

/** One film in the catalogue (browse grid, filmographies, similar films). */
export interface FilmRow {
  qid: string;
  label: string;
  year: string | null;
  image: string | null;
  rating: number | null;
}

export interface PersonRow {
  qid: string;
  label: string;
  image: string | null;
}

export interface FactValue {
  label: string;
  qid?: string | null;
  image?: string | null;
}

export interface FilmDetail extends FilmRow {
  imdb: string | null;
  date: string | null;
  description: string | null;
  genres: string[];
  tags: string[];
  facts: { property: string; name: string; values: FactValue[]; more: number }[];
  cast: PersonRow[];
  cast_total: number;
  posters: string[];
  posters_total: number;
  stills: string[];
  stills_total: number;
  backdrop: string | null;
}

export interface PersonDetail {
  qid: string;
  label: string;
  imdb: string | null;
  description: string | null;
  image: string | null;
  facts: { property: string; name: string; values: string[] }[];
  credits: { role: string; property: string; films: FilmRow[] }[];
  portraits: string[];
  portraits_total: number;
  stills: string[];
  stills_total: number;
}

export type FilmSort = "popular" | "rating" | "newest" | "oldest" | "title";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(path, { signal });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : "";
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail || `The graph server answered with an error (${res.status}).`, res.status);
  }
  return res.json();
}

export async function ask(message: string, signal?: AbortSignal): Promise<Reply> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ message }),
    signal,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : "";
    } catch {
      /* not JSON */
    }
    if (res.status === 429) throw new ApiError(detail || "Too many questions in a minute. Wait a moment and ask again.", 429);
    if (res.status === 422) throw new ApiError("Questions can be up to 300 characters.", 422);
    throw new ApiError(detail || `The graph server answered with an error (${res.status}). Try again in a moment.`, res.status);
  }
  return res.json();
}

export async function health(signal?: AbortSignal): Promise<Health> {
  const res = await fetch("/api/health", { cache: "no-store", signal });
  if (!res.ok) throw new ApiError(`health ${res.status}`, res.status);
  return res.json();
}

export async function showcase(signal?: AbortSignal): Promise<FilmRow[]> {
  return (await getJSON<{ films: FilmRow[] }>("/api/showcase", signal)).films ?? [];
}

export function listFilms(q: string, sort: FilmSort, offset: number, signal?: AbortSignal) {
  const params = new URLSearchParams({ q, sort, offset: String(offset), limit: "60" });
  return getJSON<{ total: number; offset: number; films: FilmRow[] }>(`/api/films?${params}`, signal);
}

export function search(q: string, signal?: AbortSignal) {
  return getJSON<{ films: FilmRow[]; people: PersonRow[] }>(`/api/search?q=${encodeURIComponent(q)}`, signal);
}

export const getFilm = (qid: string, signal?: AbortSignal) => getJSON<FilmDetail>(`/api/film/${encodeURIComponent(qid)}`, signal);
export const getPerson = (qid: string, signal?: AbortSignal) =>
  getJSON<PersonDetail>(`/api/person/${encodeURIComponent(qid)}`, signal);
export const getSimilar = async (qid: string, signal?: AbortSignal) =>
  (await getJSON<{ films: FilmRow[] }>(`/api/similar/${encodeURIComponent(qid)}`, signal)).films;

/**
 * Retry a catalogue request while the graph server wakes up (503 while loading,
 * 502/504 from the proxy during a cold start, network errors).
 */
export async function whenReady<T>(load: () => Promise<T>, signal?: AbortSignal, limitMs = 4 * 60_000): Promise<T> {
  const started = Date.now();
  for (;;) {
    try {
      return await load();
    } catch (err) {
      if (signal?.aborted) throw err;
      const status = err instanceof ApiError ? err.status : 0;
      const retry = status === 0 || status === 502 || status === 503 || status === 504;
      if (!retry || Date.now() - started > limitMs) throw err;
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

/** How each pipeline is named to the reader. */
export const ROUTE_INFO: Record<Route, { name: string; method: string }> = {
  factual: { name: "Stored fact", method: "SPARQL query on the graph" },
  prediction: { name: "Prediction", method: "TransE embeddings" },
  recommendation: { name: "Recommendation", method: "Weighted Jaccard similarity" },
  multimedia: { name: "Picture", method: "IMDb image index" },
};

export function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(n);
}

export function formatLatency(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export const filmHref = (qid: string) => `/film/${qid}`;
export const personHref = (qid: string) => `/person/${qid}`;
export const askHref = (q: string) => `/?q=${encodeURIComponent(q)}`;
