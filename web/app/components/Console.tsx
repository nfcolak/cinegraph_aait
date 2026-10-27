"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { formatCount, health, type Health } from "@/lib/api";

// Cinema console shell: top bar with a film-strip edge, one LIVE pill, cold-start banner and the page frame.

import { REPO } from "@/lib/site";

export type ServerPhase = "checking" | "waking" | "ready" | "offline";
export type ServerState = { phase: ServerPhase; info?: Health };

/** Resolve once the graph server reports ready (a cold start restores the graph in ~25 s, a fresh deploy takes ~1.5 min). */
export async function waitUntilReady(limitMs = 4 * 60_000): Promise<boolean> {
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

export function useServerState(): ServerState {
  const [state, setState] = useState<ServerState>({ phase: "checking" });
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    const slow = setTimeout(() => {
      if (!cancelled) setState((s) => (s.phase === "checking" ? { ...s, phase: "waking" } : s));
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
          setState((s) => ({ ...s, phase: "offline" }));
          return;
        }
        setState((s) => (s.phase === "checking" ? { ...s, phase: "waking" } : s));
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

/** Clapperboard whose stripes end in a graph edge: the CineGraph mark. */
export function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="9" width="18" height="12" rx="1.6" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3.4 9 5 4.2l15.4 1.9L19 9" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8.6 4.8 7.2 9M13.6 5.4 12.3 9" stroke="var(--accent)" strokeWidth="1.6" />
      <circle cx="8" cy="15" r="1.7" fill="var(--accent)" />
      <circle cx="16" cy="15" r="1.7" fill="var(--red)" />
      <path d="M9.7 15h4.6" stroke="currentColor" strokeWidth="1.3" opacity="0.6" />
    </svg>
  );
}

const NAV = [
  { href: "/", label: "Ask" },
  { href: "/films", label: "Films" },
  { href: "/about", label: "How it works" },
];

export function TopBar({
  server,
  crumb,
  onHome,
  inert,
}: {
  server: ServerState;
  crumb?: ReactNode;
  onHome?: () => void;
  inert?: boolean; // the ask page's bottom sheet is modal: nothing behind it takes focus
}) {
  const path = usePathname();
  const current = (href: string) =>
    (href === "/" ? path === "/" : path === href || path.startsWith(href.replace(/s$/, "") + "/")) ? "page" : undefined;
  const info = server.info;
  const seconds = useElapsed(server.phase === "waking");
  // ready: LIVE + counts; waking: BOOT + elapsed m:ss; offline: OFF; checking (first answer pending): just a quiet dot
  const word = { ready: "LIVE", offline: "OFF", waking: "BOOT", checking: "" }[server.phase];
  const status =
    server.phase === "ready"
      ? `${info ? formatCount(info.triples) : "2.4M"} facts · ${info ? formatCount(info.entities) : "130k"} entities`
      : server.phase === "waking"
        ? clock(seconds)
        : "";
  const label =
    server.phase === "ready"
      ? `Graph server live, ${status}`
      : server.phase === "offline"
        ? "Graph server offline"
        : server.phase === "checking"
          ? "Checking the graph server"
          : `Graph server starting, ${status}`;
  return (
    <header className="topbar" inert={inert}>
      <Link href="/" className="brand" onClick={onHome}>
        <span className="brand-mark">
          <BrandMark />
        </span>
        <span className="brand-name">
          Cine<span>Graph</span>
        </span>
      </Link>
      <nav className="topnav" aria-label="Site">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className="topnav-link" aria-current={current(n.href)} onClick={n.href === "/" ? onHome : undefined}>
            {n.label}
          </Link>
        ))}
        <a href={REPO} target="_blank" rel="noreferrer" className="topnav-link">
          Source ↗
        </a>
      </nav>
      {crumb && <span className="topbar-crumb">{crumb}</span>}
      <span className="topbar-spacer" />
      <span className={`live-pill live-${server.phase}`} role="status" aria-label={label} title={label}>
        <span className="live-dot" aria-hidden="true" />
        {word && (
          <span className="live-word" aria-hidden="true">
            {word}
          </span>
        )}
        {status && (
          <span className="live-text" aria-hidden="true">
            {status}
          </span>
        )}
      </span>
    </header>
  );
}

/** Page frame for every non-ask page: the top bar and one scrolling body (the only vertical scroll container). */
export function Sheet({
  title,
  onClose,
  children,
  bodyRef,
}: {
  title?: ReactNode;
  onClose?: () => void;
  children: ReactNode;
  bodyRef?: RefObject<HTMLDivElement | null>;
}) {
  const server = useServerState();
  return (
    <div className="app">
      <TopBar server={server} crumb={title} onHome={onClose} />
      <div className="page-body" ref={bodyRef} id="sheet-body">
        {children}
      </div>
    </div>
  );
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Seconds since `active` first became true, ticking once a second. */
export function useElapsed(active: boolean): number {
  const start = useRef<number | null>(null);
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    start.current ??= Date.now();
    const t = setInterval(() => setSeconds(Math.floor((Date.now() - (start.current ?? Date.now())) / 1000)), 1000);
    return () => clearInterval(t);
  }, [active]);
  return active ? seconds : 0;
}

/** Cold-start banner: the graph server sleeps when idle and needs about a minute to load 2.4M facts. */
export function WakeBanner({ server }: { server: ServerState }) {
  const seconds = useElapsed(server.phase === "waking");
  // no banner while the first health answer is pending: a ready server would flash it for a moment
  if (server.phase === "ready" || server.phase === "checking") return null;
  if (server.phase === "offline") {
    return (
      <div className="boot-banner failed" role="alert">
        <div className="boot-title">The graph server did not start.</div>
        <div className="boot-text">It may still be coming up. Reload the page in a minute to try again.</div>
      </div>
    );
  }
  const pct = Math.min(96, Math.round((seconds / 100) * 100));
  return (
    <div className="boot-banner" role="status" aria-live="polite">
      <div className="boot-row">
        <span className="boot-spinner" aria-hidden="true" />
        <div className="boot-title">{seconds > 150 ? "Still loading the graph…" : "Waking up the graph server…"}</div>
        <span className="boot-clock">{clock(seconds)}</span>
      </div>
      <div className="boot-text">
        To keep the demo free, the server sleeps when nobody is using it and loads 2.4M facts when it starts, which takes about a
        minute. You can type your question now; it is sent as soon as the graph is ready.
      </div>
      <div className="boot-bar" aria-hidden="true">
        <div className="boot-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
