"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
  type RefObject,
} from "react";
import { ask, ApiError, filmHref, formatCount, showcase, type FilmRow, type Reply, type Route } from "@/lib/api";
import { EXAMPLES } from "@/lib/examples";
import { TopBar, useElapsed, useServerState, waitUntilReady, WakeBanner, type ServerState } from "./Console";
import { AnswerBody, backdropOf, routeName, toneOf } from "./Entry";
import { Evidence, evidenceCount } from "./Evidence";

/* eslint-disable @next/next/no-img-element */

type Turn =
  | { id: number; kind: "pending"; text: string; at: string }
  | { id: number; kind: "reply"; text: string; at: string; reply: Reply }
  | { id: number; kind: "error"; text: string; at: string; error: string };

type ReplyTurn = Extract<Turn, { kind: "reply" }>;
type Tab = "all" | Route;

const MAX_CHARS = 300;
const SHEET_QUERY = "(max-width: 980px)";
const DESKTOP_QUERY = "(min-width: 981px)";

const clock = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const TABS: { id: Tab; label: string }[] = [
  { id: "all", label: "All" },
  ...EXAMPLES.map((g) => ({ id: g.route as Tab, label: g.title })),
];

function examplesFor(tab: Tab): string[] {
  if (tab === "all") return EXAMPLES.flatMap((g) => g.questions.slice(0, 2));
  return EXAMPLES.find((g) => g.route === tab)?.questions ?? [];
}

/** Live value of a media query (false on the server and during hydration). */
function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", notify);
      return () => mq.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

const smooth = (): ScrollBehavior => (window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");

function IconTrash() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6" />
    </svg>
  );
}

function IconGraph() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <circle cx="5" cy="12" r="2.5" />
      <circle cx="19" cy="6" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="M7.4 11 16.6 7M7.4 13l9.2 4" />
    </svg>
  );
}

/** Route tabs over the chat: a tablist (arrow keys, Home and End move between tabs) and the active route's example chips. */
function RouteTabs({ tab, setTab, onPick, busy }: { tab: Tab; setTab: (t: Tab) => void; onPick: (q: string) => void; busy: boolean }) {
  const refs = useRef<Partial<Record<Tab, HTMLButtonElement | null>>>({});
  const blurb = tab === "all" ? "One or two questions from every route." : EXAMPLES.find((g) => g.route === tab)?.blurb;

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const at = TABS.findIndex((t) => t.id === tab);
    const to =
      e.key === "ArrowRight" ? (at + 1) % TABS.length : e.key === "ArrowLeft" ? (at - 1 + TABS.length) % TABS.length : e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : -1;
    if (to < 0) return;
    e.preventDefault();
    setTab(TABS[to].id);
    refs.current[TABS[to].id]?.focus();
  };

  return (
    <div className="routebar">
      <div className="route-tabs" role="tablist" aria-label="Answer routes" onKeyDown={onKeyDown}>
        {TABS.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={`route-tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls="route-panel"
            tabIndex={tab === t.id ? 0 : -1}
            className={`route-tab route-tab-${t.id}`}
            onClick={() => setTab(t.id)}
          >
            {t.id !== "all" && <span className="route-dot" aria-hidden="true" />}
            {t.label}
          </button>
        ))}
      </div>
      <div id="route-panel" role="tabpanel" aria-labelledby={`route-tab-${tab}`}>
        <p className="route-blurb">{blurb}</p>
        <div className="route-examples">
          {examplesFor(tab).map((q) => (
            <button key={q} type="button" className="ex-chip" onClick={() => onPick(q)} disabled={busy}>
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Composer({
  inputRef,
  draft,
  setDraft,
  onSend,
  busy,
}: {
  inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string;
  setDraft: (v: string) => void;
  onSend: () => void;
  busy: boolean;
}) {
  // grow with the text, up to about four lines
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [draft, inputRef]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSend();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSend();
    }
  };
  return (
    <div className="composer-wrap">
      <form className="composer" onSubmit={onSubmit}>
        <span className="composer-prompt" aria-hidden="true">
          ?
        </span>
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          ref={inputRef}
          rows={1}
          className="composer-input"
          value={draft}
          maxLength={MAX_CHARS}
          placeholder="Ask about a film or a person…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        {draft.length > MAX_CHARS * 0.8 && (
          <span className="composer-count" aria-hidden="true">
            {draft.length}/{MAX_CHARS}
          </span>
        )}
        <button type="submit" className="composer-send" disabled={busy || !draft.trim()}>
          Ask <kbd>↵</kbd>
        </button>
      </form>
    </div>
  );
}

function PosterReel({ ready }: { ready: boolean }) {
  const [films, setFilms] = useState<FilmRow[]>([]);
  useEffect(() => {
    if (!ready || films.length) return;
    const ctrl = new AbortController();
    showcase(ctrl.signal)
      .then((all) => setFilms(all.filter((f) => f.image).slice(0, 8)))
      .catch(() => {
        /* optional decoration */
      });
    return () => ctrl.abort();
  }, [ready, films.length]);
  if (!films.length) return <div className="reel reel-empty" aria-hidden="true" />;
  return (
    <ul className="reel" aria-label="Films in the graph">
      {films.map((f) => (
        <li key={f.qid}>
          <Link href={filmHref(f.qid)} title={f.year ? `${f.label} (${f.year})` : f.label}>
            <img src={f.image!} alt={f.label} loading="lazy" />
          </Link>
        </li>
      ))}
    </ul>
  );
}

function Intro({ server }: { server: ServerState }) {
  const info = server.info;
  return (
    <div className="intro">
      <p className="intro-kicker">Wikidata film graph · {info ? formatCount(info.triples) : "2.4M"} facts</p>
      <h1 className="intro-title">
        Ask the film graph <em>anything</em> about who made what.
      </h1>
      <p className="intro-sub">
        Facts, filmographies, recommendations and pictures. Each answer is drawn as the path it took through the graph, in
        the evidence panel.
      </p>
      <dl className="intro-stats">
        <div>
          <dt>facts</dt>
          <dd>{info ? formatCount(info.triples) : "2.4M"}</dd>
        </div>
        <div>
          <dt>entities</dt>
          <dd>{info ? formatCount(info.entities) : "130k"}</dd>
        </div>
        <div>
          <dt>routes</dt>
          <dd>{EXAMPLES.length}</dd>
        </div>
      </dl>
      <PosterReel ready={server.phase === "ready"} />
    </div>
  );
}

function Question({ turn, index }: { turn: Turn; index: number }) {
  return (
    <div className="q-row">
      <span className="q-index">Q{String(index).padStart(2, "0")}</span>
      <h2 className="q-text">{turn.text}</h2>
      <span className="q-time">{turn.at}</span>
    </div>
  );
}

const STAGES = ["Reading the question", "Linking entities", "Querying the graph"];

/** Pending answer: the projector reel spins while the stages of the agent run by. */
function Pending({ waking }: { waking: boolean }) {
  const seconds = useElapsed(true);
  const text = waking ? "Waiting for the graph server to wake up" : `${STAGES[Math.min(STAGES.length - 1, Math.floor(seconds / 2))]}…`;
  return (
    <div className="a-panel a-pending" role="status">
      <span className="projector" aria-hidden="true" />
      {text}
    </div>
  );
}

function Answer({
  turn,
  selected,
  expanded,
  onSelect,
  onRetry,
  waking,
}: {
  turn: Turn;
  selected: boolean;
  expanded: boolean;
  onSelect: (e: MouseEvent<HTMLButtonElement>) => void;
  onRetry: () => void;
  waking: boolean;
}) {
  if (turn.kind === "pending") return <Pending waking={waking} />;
  if (turn.kind === "error") {
    return (
      <div className="a-panel a-error" role="alert">
        <span>{turn.error}</span>
        <button type="button" className="text-btn" onClick={onRetry}>
          Ask again
        </button>
      </div>
    );
  }
  const reply = turn.reply;
  const bg = backdropOf(reply);
  const tone = toneOf(reply);
  return (
    <div className={`a-panel a-${tone} ${selected ? "selected" : ""}`}>
      {bg && (
        <div className="a-backdrop" aria-hidden="true">
          <span style={{ backgroundImage: `url("${bg}")` }} />
        </div>
      )}
      <div className="a-content">
        <AnswerBody reply={reply} />
        <div className="a-meta">
          <span className={`tag tag-route tag-${tone}`}>{routeName(reply)}</span>
          {reply.relation && <span className="tag">{reply.relation}</span>}
          <span className="tag">{reply.latency_ms < 1000 ? `${reply.latency_ms} ms` : `${(reply.latency_ms / 1000).toFixed(1)} s`}</span>
          <button
            type="button"
            className={`tag tag-action ${selected ? "active" : ""}`}
            onClick={onSelect}
            aria-expanded={expanded}
            aria-controls="evidence-panel"
          >
            <IconGraph /> evidence · {evidenceCount(reply)}
          </button>
        </div>
      </div>
    </div>
  );
}

function EvidencePanel({
  turn,
  sheet,
  onClose,
  onAsk,
  closeRef,
}: {
  turn: ReplyTurn | null;
  sheet: boolean;
  onClose: () => void;
  onAsk: (q: string) => void;
  closeRef: RefObject<HTMLButtonElement | null>;
}) {
  return (
    <aside
      id="evidence-panel"
      className="rail-right"
      aria-label="Evidence"
      role={sheet ? "dialog" : undefined}
      aria-modal={sheet ? true : undefined}
    >
      <div className="evidence-header">
        <div className="evidence-bar">
          <span className="evidence-mark" aria-hidden="true" />
          <h2 className="evidence-title">Evidence</h2>
          {turn && <span className="evidence-count">{evidenceCount(turn.reply)}</span>}
          <button type="button" className="evidence-close" ref={closeRef} onClick={onClose}>
            Close
          </button>
        </div>
        {turn ? <p className="evidence-q">{turn.text}</p> : <p className="evidence-kicker">How the selected answer was found in the graph.</p>}
      </div>
      <div className="evidence-scroll">
        {turn ? (
          <Evidence reply={turn.reply} onAsk={onAsk} />
        ) : (
          <div className="evidence-empty">
            <div className="evidence-empty-icon">
              <IconGraph />
            </div>
            <div className="evidence-empty-title">No answer yet</div>
            <div className="evidence-empty-text">Ask a question. Its path through the graph, the query and the agent&apos;s log appear here.</div>
          </div>
        )}
      </div>
    </aside>
  );
}

export function Chat() {
  const server = useServerState();
  const readyRef = useRef(false);
  useEffect(() => {
    readyRef.current = server.phase === "ready";
  }, [server.phase]);

  const [turns, setTurns] = useState<Turn[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("all");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [announce, setAnnounce] = useState("");
  const nextId = useRef(1);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const count = turns.length;
  const narrow = useMedia(SHEET_QUERY);
  const sheetOpen = narrow && evidenceOpen;

  // Bring the newest question to the top of the chat so its answer is read from the start.
  useEffect(() => {
    if (!count) return;
    const id = nextId.current - 1;
    requestAnimationFrame(() => document.getElementById(`q-${id}`)?.scrollIntoView({ behavior: smooth(), block: "start" }));
  }, [count]);

  useEffect(() => {
    if (window.matchMedia(DESKTOP_QUERY).matches) inputRef.current?.focus();
  }, []);

  const closeEvidence = useCallback(() => setEvidenceOpen(false), []);

  // The bottom sheet: focus moves into it when it opens and back to the evidence button when it closes
  // (the cleanup runs after the chat column stops being inert); Escape closes it.
  useEffect(() => {
    if (!sheetOpen) return;
    closeRef.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") closeEvidence();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      openerRef.current?.focus();
    };
  }, [sheetOpen, closeEvidence]);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;
      setBusy(true);
      setDraft("");
      setEvidenceOpen(false);
      const id = nextId.current++;
      const at = clock();
      setTurns((t) => [...t, { id, kind: "pending", text, at }]);
      try {
        if (!readyRef.current && !(await waitUntilReady())) {
          throw new ApiError("The graph server did not start. Try again in a minute.", 503);
        }
        const reply = await ask(text);
        setTurns((t) => t.map((x) => (x.id === id ? { id, kind: "reply", text, at, reply } : x)));
        setSelectedId(id);
        setAnnounce(`${routeName(reply)}. ${reply.answer || "Picture ready."}`);
      } catch (err) {
        const error =
          err instanceof ApiError
            ? err.status === 502 || err.status === 504
              ? "The graph server is still starting. Ask again in a few seconds."
              : err.message
            : "Could not reach the graph server. Check your connection and ask again.";
        setTurns((t) => t.map((x) => (x.id === id ? { id, kind: "error", text, at, error } : x)));
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

  const reset = () => {
    setTurns([]);
    setSelectedId(null);
    setEvidenceOpen(false);
    setAnnounce("");
    if (window.matchMedia(DESKTOP_QUERY).matches) inputRef.current?.focus();
  };

  const replies = turns.filter((t): t is ReplyTurn => t.kind === "reply");
  const selected = replies.find((t) => t.id === selectedId) ?? replies[replies.length - 1] ?? null;

  return (
    <div className="app">
      <TopBar server={server} onHome={reset} inert={sheetOpen} />
      <div className={`workspace ${evidenceOpen ? "evidence-open" : ""}`}>
        <section className="chat-col" aria-label="Ask the graph" inert={sheetOpen}>
          <RouteTabs tab={tab} setTab={setTab} onPick={send} busy={busy} />
          <WakeBanner server={server} />
          <p className="sr-only" role="status" aria-live="polite">
            {announce}
          </p>
          <main className="chat-scroll" id="main" tabIndex={-1}>
            {turns.length === 0 ? (
              <Intro server={server} />
            ) : (
              <>
                <h1 className="sr-only">CineGraph: ask the film graph</h1>
                {turns.map((t, i) => {
                  const isSelected = t.kind === "reply" && selected?.id === t.id;
                  return (
                    <article key={t.id} className="turn" id={`q-${t.id}`}>
                      <Question turn={t} index={i + 1} />
                      <Answer
                        turn={t}
                        waking={server.phase === "waking" || server.phase === "offline"}
                        selected={isSelected}
                        expanded={narrow ? isSelected && evidenceOpen : isSelected}
                        onSelect={(e) => {
                          // a second press on the open answer's button closes the sheet
                          if (isSelected && evidenceOpen) {
                            setEvidenceOpen(false);
                            return;
                          }
                          openerRef.current = e.currentTarget;
                          setSelectedId(t.id);
                          setEvidenceOpen(true);
                        }}
                        onRetry={() => {
                          setTurns((all) => all.filter((x) => x.id !== t.id));
                          send(t.text);
                        }}
                      />
                    </article>
                  );
                })}
                <div className="thread-tools">
                  <button type="button" className="text-btn" onClick={reset}>
                    <IconTrash /> Clear {turns.length === 1 ? "question" : `${turns.length} questions`}
                  </button>
                </div>
              </>
            )}
          </main>
          <Composer inputRef={inputRef} draft={draft} setDraft={setDraft} onSend={() => send(draft)} busy={busy} />
        </section>

        {sheetOpen && <button type="button" className="sheet-scrim" aria-label="Close evidence" tabIndex={-1} onClick={closeEvidence} />}
        <EvidencePanel
          turn={selected}
          sheet={sheetOpen}
          onClose={closeEvidence}
          onAsk={(q) => {
            setEvidenceOpen(false);
            send(q);
          }}
          closeRef={closeRef}
        />
      </div>
    </div>
  );
}
