"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { ask, ApiError, formatCount, health, type Health, type Reply } from "@/lib/api";
import { EXAMPLES } from "@/lib/examples";
import { Entry } from "./Entry";
import { PosterWall } from "./PosterWall";
import { SiteHeader } from "./SiteHeader";

type Turn =
  | { id: number; kind: "pending"; text: string }
  | { id: number; kind: "reply"; text: string; reply: Reply }
  | { id: number; kind: "error"; text: string; error: string };

type ServerState = { phase: "checking" | "waking" | "ready" | "offline"; info?: Health };

const MAX_CHARS = 300;

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

function Status({ state }: { state: ServerState }) {
  const text =
    state.phase === "ready" && state.info
      ? `${formatCount(state.info.triples)} facts online`
      : state.phase === "waking"
        ? "Waking the graph server"
        : state.phase === "offline"
          ? "Graph server offline"
          : "Connecting";
  return (
    <span className={`status status-${state.phase}`} role="status">
      {text}
    </span>
  );
}

function Composer({
  inputRef,
  draft,
  setDraft,
  onSend,
  busy,
  docked,
}: {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  setDraft: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  docked: boolean;
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
  const form = (
    <form className="composer" onSubmit={onSubmit}>
      <label htmlFor="question" className="sr-only">
        Your question
      </label>
      <textarea
        id="question"
        ref={inputRef}
        rows={1}
        value={draft}
        maxLength={MAX_CHARS}
        placeholder={docked ? "Ask another question" : "Who directed Heat?"}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <button type="submit" disabled={busy || !draft.trim()}>
        Ask
      </button>
    </form>
  );
  return docked ? <div className="dock">{form}</div> : form;
}

function Pending({ text, waking }: { text: string; waking: boolean }) {
  return (
    <article className="entry entry-pending" aria-busy="true">
      <p className="skeleton-line" />
      <p className="skeleton-line skeleton-short" />
      <div className="skeleton-tiles">
        <span />
        <span />
        <span />
        <span />
      </div>
      <p className="entry-foot" role="status">
        {waking ? "Waking the graph server. The first answer can take up to a minute." : `Looking up “${text}”`}
      </p>
    </article>
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
  const threadRef = useRef<HTMLDivElement>(null);
  const lastCount = useRef(0);

  // When a question is added, bring it to the top of the view so its answer is read from the start.
  useEffect(() => {
    if (turns.length === lastCount.current) return;
    lastCount.current = turns.length;
    const qs = threadRef.current?.querySelectorAll(".turn");
    qs?.[qs.length - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [turns]);

  // Focus the box on desktop only; on phones it would raise the keyboard over the start screen.
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

  const empty = turns.length === 0;

  return (
    <div className={`app ${empty ? "app-start" : "app-thread"}`}>
      <SiteHeader extra={<Status state={server} />} onHome={() => setTurns([])} />

      {empty ? (
        <main className="start" id="main">
          <section className="start-copy">
            <h1>Ask the film graph.</h1>
            <p className="lede">
              {server.info ? formatCount(server.info.triples) : "2.4M"} Wikidata facts about films and the people who make them.
              Every answer shows the path it took through the graph.
            </p>
            <Composer inputRef={inputRef} draft={draft} setDraft={setDraft} onSend={() => send(draft)} busy={busy} docked={false} />
            <div className="suggest">
              {EXAMPLES.map((g) => (
                <section key={g.route}>
                  <h2>{g.title}</h2>
                  <ul>
                    {g.questions.slice(0, 2).map((q) => (
                      <li key={q}>
                        <button type="button" onClick={() => send(q)} disabled={busy}>
                          {q}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </section>
          <PosterWall ready={server.phase === "ready"} />
        </main>
      ) : (
        <main className="thread" id="main" ref={threadRef} aria-live="polite">
          {turns.map((t) => (
            <section key={t.id} className="turn">
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
          <Composer inputRef={inputRef} draft={draft} setDraft={setDraft} onSend={() => send(draft)} busy={busy} docked />
        </main>
      )}
    </div>
  );
}
