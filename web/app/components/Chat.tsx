"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { ask, ApiError, formatCount, health, type Health, type Reply } from "@/lib/api";
import { EXAMPLES } from "@/lib/examples";
import { Entry } from "./Entry";
import { Gallery } from "./Gallery";
import { REPO, Reader, Sheet } from "./SiteHeader";

type Turn =
  | { id: number; kind: "pending"; text: string }
  | { id: number; kind: "reply"; text: string; reply: Reply }
  | { id: number; kind: "error"; text: string; error: string };

type ServerState = { phase: "checking" | "waking" | "ready" | "offline"; info?: Health };

const MAX_CHARS = 300;
const TRY = [EXAMPLES[0].questions[0], EXAMPLES[2].questions[0], EXAMPLES[3].questions[1], EXAMPLES[1].questions[0]];

/** Resolve once the graph server reports ready (a cold start restores the graph in ~25 s, a fresh deploy takes ~1.5 min). */
async function waitUntilReady(limitMs = 4 * 60_000): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < limitMs) {
    try {
      if ((await health()).status === "ready") return true;
    } catch {
      /* proxy timeout or container still booting: keep polling */
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  return false;
}

function useServerState(): ServerState {
  const [state, setState] = useState<ServerState>({ phase: "checking" });
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    const slow = setTimeout(() => {
      if (!cancelled) setState((s) => (s.phase === "checking" ? { phase: "waking" } : s));
    }, 2500);

    const poll = async () => {
      try {
        const info = await health();
        if (cancelled) return;
        if (info.status === "ready") {
          setState({ phase: "ready", info });
          return;
        }
        setState({ phase: "waking", info });
      } catch {
        if (cancelled) return;
        if (Date.now() - started > 4 * 60_000) {
          setState({ phase: "offline" });
          return;
        }
        setState((s) => (s.phase === "checking" ? { phase: "waking" } : s));
      }
      timer = setTimeout(poll, 4000);
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(slow);
      if (timer) clearTimeout(timer);
    };
  }, []);
  return state;
}

function statusText(state: ServerState): string {
  if (state.phase === "ready" && state.info) return `${formatCount(state.info.triples)} facts online`;
  if (state.phase === "waking") return "Waking the graph server";
  if (state.phase === "offline") return "Graph server offline";
  return "Connecting";
}

function Composer({
  inputRef,
  draft,
  setDraft,
  onSend,
  busy,
  variant,
}: {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  setDraft: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  variant: "landing" | "dock";
}) {
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSend();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };
  return (
    <form className={`composer composer-${variant}`} onSubmit={onSubmit}>
      <label htmlFor="question" className="sr-only">
        Your question
      </label>
      <textarea
        id="question"
        ref={inputRef}
        rows={1}
        value={draft}
        maxLength={MAX_CHARS}
        placeholder={variant === "dock" ? "Ask another question" : "Who directed Heat?"}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <button type="submit" disabled={busy || !draft.trim()}>
        Ask
      </button>
    </form>
  );
}

function Pending({ text, waking }: { text: string; waking: boolean }) {
  return (
    <div className="entry entry-pending" aria-busy="true">
      <div className="skeleton-media" />
      <p className="skeleton-line" />
      <p className="skeleton-line skeleton-short" />
      <p className="entry-status" role="status">
        {waking ? "Waking the graph server. The first answer can take up to a minute." : `Looking up “${text}”`}
      </p>
    </div>
  );
}

export function Chat() {
  const server = useServerState();
  const readyRef = useRef(false);
  useEffect(() => {
    readyRef.current = server.phase === "ready";
  }, [server.phase]);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const nextId = useRef(1);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastCount = useRef(0);

  // When a question is added, bring it to the top of the sheet so its answer is read from the start.
  useEffect(() => {
    if (turns.length === lastCount.current) return;
    lastCount.current = turns.length;
    const last = turns[turns.length - 1];
    if (last) requestAnimationFrame(() => document.getElementById(`q-${last.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }, [turns]);

  // Focus the box on desktop only; on phones it would raise the keyboard over the gallery.
  useEffect(() => {
    if (window.matchMedia("(min-width: 961px)").matches) inputRef.current?.focus();
  }, []);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;
      setBusy(true);
      setDraft("");
      const id = nextId.current++;
      setTurns((t) => [...t, { id, kind: "pending", text }]);
      try {
        if (!readyRef.current && !(await waitUntilReady())) {
          throw new ApiError("The graph server did not start. Try again in a minute.", 503);
        }
        const reply = await ask(text);
        setTurns((t) => t.map((x) => (x.id === id ? { id, kind: "reply", text, reply } : x)));
      } catch (err) {
        const error =
          err instanceof ApiError
            ? err.status === 502 || err.status === 504
              ? "The graph server is still starting. Ask again in a few seconds."
              : err.message
            : "Could not reach the graph server. Check your connection and ask again.";
        setTurns((t) => t.map((x) => (x.id === id ? { id, kind: "error", text, error } : x)));
      } finally {
        setBusy(false);
        if (window.matchMedia("(min-width: 961px)").matches) inputRef.current?.focus();
      }
    },
    [busy],
  );

  // Questions linked from film and person pages arrive as /?q=...
  const askedFromLink = useRef(false);
  useEffect(() => {
    if (askedFromLink.current) return;
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      askedFromLink.current = true;
      window.history.replaceState(null, "", "/");
      setTimeout(() => send(q), 0);
    }
  }, [send]);

  const reset = () => setTurns([]);

  if (turns.length === 0) {
    return (
      <div className="landing">
        <header className="corner corner-top">
          <Link href="/" className="corner-brand">
            CineGraph
          </Link>
          <span className={`corner-status status-${server.phase}`} role="status">
            {statusText(server)}
          </span>
        </header>

        <main className="landing-main" id="main">
          <h1 className="sr-only">CineGraph, ask the film graph</h1>
          <Gallery ready={server.phase === "ready"} />
          <div className="landing-ask">
            <p className="landing-kicker">
              Ask the film graph · {server.info ? formatCount(server.info.triples) : "2.4M"} Wikidata facts, every answer with its path
            </p>
            <Composer inputRef={inputRef} draft={draft} setDraft={setDraft} onSend={() => send(draft)} busy={busy} variant="landing" />
            <ul className="landing-try" aria-label="Example questions">
              {TRY.map((q) => (
                <li key={q}>
                  <button type="button" onClick={() => send(q)} disabled={busy}>
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </main>

        <footer className="corner corner-bottom">
          <nav className="corner-switch" aria-label="Browse">
            <span aria-current="page">Featured</span>
            <span aria-hidden="true">/</span>
            <Link href="/films">All films</Link>
          </nav>
          <nav className="corner-links" aria-label="Site">
            <Link href="/about">How it works</Link>
            <a href={REPO} target="_blank" rel="noreferrer">
              Source
            </a>
          </nav>
        </footer>
      </div>
    );
  }

  const sections = turns.map((t) => ({ id: `q-${t.id}`, label: t.text }));

  return (
    <Sheet title="Ask" onClose={reset}>
      <Reader
        back={{ href: "/", label: "Gallery", onClick: reset }}
        title="Ask the film graph"
        meta={[
          { label: "Graph", value: statusText(server) },
          { label: "Answers from", value: "SPARQL · TransE · Jaccard recommender · image index" },
        ]}
        sections={sections}
        extra={
          <div className="reader-try">
            <p>Try</p>
            <ul>
              {TRY.map((q) => (
                <li key={q}>
                  <button type="button" onClick={() => send(q)} disabled={busy}>
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        }
      >
        <div className="thread" aria-live="polite">
          {turns.map((t, i) => (
            <section key={t.id} className="turn" id={`q-${t.id}`}>
              <p className="turn-index">Question {String(i + 1).padStart(2, "0")}</p>
              <h2 className="question">{t.text}</h2>
              {t.kind === "pending" && <Pending text={t.text} waking={server.phase !== "ready"} />}
              {t.kind === "error" && (
                <p className="error" role="alert">
                  {t.error}
                </p>
              )}
              {t.kind === "reply" && <Entry reply={t.reply} />}
            </section>
          ))}
          <div className="thread-end" aria-hidden="true" />
        </div>
        <div className="dock">
          <Composer inputRef={inputRef} draft={draft} setDraft={setDraft} onSend={() => send(draft)} busy={busy} variant="dock" />
        </div>
      </Reader>
    </Sheet>
  );
}
