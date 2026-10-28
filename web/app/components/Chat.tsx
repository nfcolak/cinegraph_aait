"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { ask, ApiError, formatLatency, type Reply } from "@/lib/api";
import { setBackdrop } from "@/lib/backdrop";
import { QUESTION_KINDS } from "@/lib/examples";
import { loadThread, saveThread } from "@/lib/thread";
import { HOME_EVENT, useServer, waitUntilReady } from "./Shell";
import { AnswerBody, backdropOf, isGuess } from "./Entry";
import { Evidence } from "./Evidence";

type Turn =
  | { id: number; kind: "pending"; text: string }
  | { id: number; kind: "reply"; text: string; reply: Reply }
  | { id: number; kind: "error"; text: string; error: string };

const MAX_CHARS = 300;
const DESKTOP_QUERY = "(min-width: 981px)";

const smooth = (): ScrollBehavior => (window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");

function Chevron() {
  return (
    <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m4.5 2.5 3.5 3.5-3.5 3.5" />
    </svg>
  );
}

/** The kinds of question the graph answers: one line each, the kind on the left, its questions inline. */
function AskGuide({ onPick, busy }: { onPick: (q: string) => void; busy: boolean }) {
  return (
    <section className="guide" aria-labelledby="guide-title">
      <h2 id="guide-title" className="guide-title">
        What you can ask
      </h2>
      <dl className="guide-list">
        {QUESTION_KINDS.map((kind) => (
          <div key={kind.title} className="guide-row">
            <dt title={kind.blurb}>{kind.title}</dt>
            <dd>
              {kind.questions.map((q) => (
                <button key={q} type="button" className="guide-q" onClick={() => onPick(q)} disabled={busy}>
                  {q}
                </button>
              ))}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

/** The input card: full while the page is empty, a compact sticky bar once a question is asked. */
function Composer({
  inputRef,
  draft,
  setDraft,
  onSend,
  busy,
  compact,
  status,
}: {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  setDraft: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  compact: boolean;
  status: string;
}) {
  // the compact bar grows with the text, up to about four lines
  useEffect(() => {
    const el = inputRef.current;
    if (!el || !compact) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 112)}px`;
  }, [draft, compact, inputRef]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSend();
  };
  // Enter, Cmd/Ctrl+Enter send; Shift+Enter adds a line
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSend();
    }
  };
  return (
    <form className={`card composer ${compact ? "compact" : ""}`} onSubmit={onSubmit}>
      <label htmlFor="question" className="sr-only">
        Your question
      </label>
      <textarea
        id="question"
        ref={inputRef}
        rows={compact ? 1 : 3}
        className="composer-input"
        value={draft}
        maxLength={MAX_CHARS}
        placeholder={compact ? "Ask another…" : "Who directed Inception?"}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="tools">
        <span className="status" role="status">
          {status}
        </span>
        <button type="submit" className="btn" disabled={busy || !draft.trim()}>
          Ask
        </button>
      </div>
    </form>
  );
}

function Answer({ id, reply, onAsk }: { id: number; reply: Reply; onAsk: (q: string) => void }) {
  const [open, setOpen] = useState(false);
  const evidenceId = `evidence-${id}`;
  // opening the log keeps it above the sticky input card
  useEffect(() => {
    if (open) document.getElementById(evidenceId)?.scrollIntoView({ behavior: smooth(), block: "nearest" });
  }, [open, evidenceId]);
  return (
    <>
      <AnswerBody reply={reply} onAsk={onAsk} />
      <div className="turn-foot">
        <button type="button" className="quiet disclosure" aria-expanded={open} aria-controls={evidenceId} onClick={() => setOpen((o) => !o)}>
          <Chevron />
          How it was found
        </button>
        <span className="latency">{formatLatency(reply.latency_ms)}</span>
      </div>
      <Evidence reply={reply} id={evidenceId} hidden={!open} />
    </>
  );
}

export function Chat() {
  const server = useServer();
  const readyRef = useRef(false);
  useEffect(() => {
    readyRef.current = server.phase === "ready";
  }, [server.phase]);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [announce, setAnnounce] = useState("");
  const nextId = useRef(1);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const count = turns.length;
  const empty = count === 0;

  // Bring the newest question to the top of the screen so its answer is read from the start.
  useEffect(() => {
    if (!count) return;
    const id = nextId.current - 1;
    requestAnimationFrame(() => document.getElementById(`q-${id}`)?.scrollIntoView({ behavior: smooth(), block: "start" }));
  }, [count]);

  useEffect(() => {
    if (window.matchMedia(DESKTOP_QUERY).matches) inputRef.current?.focus();
  }, []);

  // Coming back from a film or person page: the answered questions of this tab come back too.
  const restored = useRef(false);
  useEffect(() => {
    // a timeout, not a frame: frames do not run in a background tab
    const timer = setTimeout(() => {
      const kept = loadThread<Turn>().filter((t) => t && t.kind === "reply" && typeof t.id === "number");
      if (kept.length) {
        // negative ids: never clash with a question sent meanwhile (/?q=...)
        const back = kept.map((t, i) => ({ ...t, id: i - kept.length }));
        // the page may come back with its state kept (router cache): restore only into an empty thread
        setTurns((now) => (now.some((t) => t.kind === "reply") ? now : [...back, ...now]));
        setTimeout(() => document.getElementById(`q-${back[back.length - 1].id}`)?.scrollIntoView({ block: "start" }), 50);
      }
      restored.current = true;
    }, 0);
    return () => clearTimeout(timer);
  }, []);
  useEffect(() => {
    if (restored.current) saveThread(turns.filter((t) => t.kind === "reply"));
  }, [turns]);

  // The latest answer's image goes to the ambient field behind the page.
  const latest = [...turns].reverse().find((t): t is Extract<Turn, { kind: "reply" }> => t.kind === "reply");
  const backdrop = latest ? backdropOf(latest.reply) : null;
  useEffect(() => {
    setBackdrop(backdrop);
  }, [backdrop]);
  useEffect(() => () => setBackdrop(null), []);

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
        setAnnounce(`${isGuess(reply) ? "Guess. " : ""}${reply.answer || "Picture ready."}`);
      } catch (err) {
        const error =
          err instanceof ApiError
            ? err.status === 502 || err.status === 504
              ? "The graph server is still starting. Ask again in a few seconds."
              : err.message
            : "Could not reach the graph server. Check your connection and ask again.";
        setTurns((t) => t.map((x) => (x.id === id ? { id, kind: "error", text, error } : x)));
        setAnnounce(error);
      } finally {
        setBusy(false);
        if (window.matchMedia(DESKTOP_QUERY).matches) inputRef.current?.focus();
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

  // The logo, pressed on this page, clears the thread.
  useEffect(() => {
    const reset = () => {
      setTurns([]);
      setAnnounce("");
      if (window.matchMedia(DESKTOP_QUERY).matches) inputRef.current?.focus();
    };
    window.addEventListener(HOME_EVENT, reset);
    return () => window.removeEventListener(HOME_EVENT, reset);
  }, []);

  const status =
    draft.length >= MAX_CHARS
      ? `${MAX_CHARS} characters at most`
      : busy && server.phase !== "ready" && server.phase !== "checking"
        ? "Your question is sent when the graph is ready."
        : "";

  return (
    <main id="main" className={`ask ${empty ? "is-empty" : ""}`} tabIndex={-1}>
      <p className="sr-only" role="status" aria-live="polite">
        {announce}
      </p>

      {empty ? (
        <div className="hero">
          <h1 className="hero-title">Ask anything about films.</h1>
          <p className="hero-sub">Directors, casts, release dates, similar films and pictures, from Wikidata.</p>
        </div>
      ) : (
        <div className="thread">
          <h1 className="sr-only">CineGraph: ask the film graph</h1>
          {turns.map((t) => (
            <article key={t.id} className="turn" id={`q-${t.id}`}>
              <h2 className="turn-q">{t.text}</h2>
              {t.kind === "pending" && (
                <p className="turn-wait" role="status">
                  Looking it up…
                </p>
              )}
              {t.kind === "error" && (
                <p className="turn-error" role="alert">
                  <span>{t.error}</span>
                  <button
                    type="button"
                    className="quiet"
                    onClick={() => {
                      setTurns((all) => all.filter((x) => x.id !== t.id));
                      send(t.text);
                    }}
                  >
                    Try again
                  </button>
                </p>
              )}
              {t.kind === "reply" && <Answer id={t.id} reply={t.reply} onAsk={send} />}
            </article>
          ))}
        </div>
      )}

      <Composer inputRef={inputRef} draft={draft} setDraft={setDraft} onSend={() => send(draft)} busy={busy} compact={!empty} status={status} />
      {empty && <AskGuide onPick={send} busy={busy} />}
    </main>
  );
}
