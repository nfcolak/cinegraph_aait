"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, Suspense, useContext, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { formatCount, health, type Health } from "@/lib/api";
import { useBackdrop } from "@/lib/backdrop";
import { REPO } from "@/lib/site";
import { hasThread } from "@/lib/thread";

// Quiet shell, rendered once by layout.tsx: the ambient film field, a small header, the page column and a
// one-line footer that also carries the server state. Sheet is the frame the film, person, catalogue and about pages use.

export type ServerPhase = "checking" | "waking" | "ready" | "offline";
export type ServerState = { phase: ServerPhase; info?: Health };

/** Dispatched on window when the logo is pressed on the ask page; the chat clears its thread. */
export const HOME_EVENT = "cg:home";

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

function useServerState(): ServerState {
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

const ServerContext = createContext<ServerState>({ phase: "checking" });

/** The graph server's state, polled once by the shell. */
export function useServer(): ServerState {
  return useContext(ServerContext);
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

/** A film frame with a two-node graph edge inside: the CineGraph mark. */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4.5" y="2.5" width="15" height="19" rx="3.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="m10.6 13.7 2.8-3.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="9.5" cy="15" r="1.7" fill="currentColor" />
      <circle cx="14.5" cy="9" r="1.7" fill="currentColor" />
    </svg>
  );
}

/** Fixed layer behind everything: the current film image, blurred, crossfading between two stacked layers. */
function Ambient() {
  const url = useBackdrop();
  const [layers, setLayers] = useState<{ urls: [string | null, string | null]; front: 0 | 1 }>({ urls: [null, null], front: 0 });

  useEffect(() => {
    if (!url) return;
    let cancelled = false;
    const img = new Image();
    // swap once the image is decoded, so the fade never starts on an empty layer
    const show = () => {
      if (cancelled) return;
      setLayers((s) => {
        if (s.urls[s.front] === url) return s;
        const back = s.front === 0 ? 1 : 0;
        const urls: [string | null, string | null] = [...s.urls];
        urls[back] = url;
        return { urls, front: back };
      });
    };
    img.onload = show;
    img.onerror = show;
    img.src = url;
    return () => {
      cancelled = true;
      img.onload = null;
      img.onerror = null;
    };
  }, [url]);

  return (
    <div className="ambient" aria-hidden="true">
      {([0, 1] as const).map((i) => (
        <span
          key={i}
          className={`ambient-layer ${url && layers.front === i && layers.urls[i] ? "on" : ""}`}
          style={layers.urls[i] ? { backgroundImage: `url("${layers.urls[i]}")` } : undefined}
        />
      ))}
    </div>
  );
}

function watchTheme(onChange: () => void) {
  const obs = new MutationObserver(onChange);
  obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => obs.disconnect();
}

function ThemeToggle() {
  // null on the server: it cannot know the theme, so aria-pressed only appears once mounted
  const dark = useSyncExternalStore<boolean | null>(watchTheme, () => document.documentElement.dataset.theme === "dark", () => null);

  // follow the system scheme while the visitor has not chosen one
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      try {
        if (localStorage.getItem("cg-theme")) return;
      } catch {
        /* storage blocked: follow the system */
      }
      document.documentElement.dataset.theme = mq.matches ? "dark" : "light";
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const toggle = () => {
    const root = document.documentElement;
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try {
      localStorage.setItem("cg-theme", next);
    } catch {
      /* storage blocked: the choice lasts for this visit */
    }
  };

  // the icon for the other theme is picked by CSS from html[data-theme], so server and client markup match
  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label="Dark theme" aria-pressed={dark ?? undefined}>
      <svg className="icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
      </svg>
      <svg className="icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />
      </svg>
    </button>
  );
}

/** The nav links; the current page is only known on the client, so the links render first and the mark follows. */
function NavLinks() {
  const path = usePathname();
  const films = path === "/films" || path.startsWith("/film/");
  return (
    <>
      <Link href="/" className="nav-link" aria-current={path === "/" ? "page" : undefined}>
        Ask
      </Link>
      <Link href="/films" className="nav-link" aria-current={films ? "page" : undefined}>
        Films
      </Link>
      <Link href="/about" className="nav-link" aria-current={path === "/about" ? "page" : undefined}>
        About
      </Link>
    </>
  );
}

function Header() {
  return (
    <header className="header">
      <div className="header-in">
        <Link
          href="/"
          className="brand"
          onClick={() => {
            if (window.location.pathname === "/") window.dispatchEvent(new Event(HOME_EVENT));
          }}
        >
          <BrandMark />
          <span className="brand-name">CineGraph</span>
        </Link>
        <nav className="nav" aria-label="Site">
          <Suspense
            fallback={
              <>
                <Link href="/" className="nav-link">
                  Ask
                </Link>
                <Link href="/films" className="nav-link">
                  Films
                </Link>
                <Link href="/about" className="nav-link">
                  About
                </Link>
              </>
            }
          >
            <NavLinks />
          </Suspense>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  );
}

function Footer({ server }: { server: ServerState }) {
  const seconds = useElapsed(server.phase === "waking");
  const facts = `${server.info ? formatCount(server.info.triples) : "2.4M"} facts`;
  const waking = server.phase === "waking";
  const state = waking ? "waking up the graph…" : server.phase === "offline" ? "graph offline" : facts;
  return (
    <footer className="footer">
      <p>
        Wikidata film graph ·{" "}
        {/* announces phase changes only; the ticking clock stays outside the live region */}
        <span role="status" aria-live="polite">
          {state}
        </span>
        {waking && <span aria-hidden="true"> {clock(seconds)}</span>}{" "}
        ·{" "}
        <a href={REPO} target="_blank" rel="noreferrer">
          GitHub
        </a>
      </p>
    </footer>
  );
}

/** The frame around every page: ambient field, header, the page column and the footer. */
export function Shell({ children }: { children: ReactNode }) {
  const server = useServerState();
  return (
    <ServerContext.Provider value={server}>
      <Ambient />
      <div className="shell">
        <Header />
        <div className="shell-main">{children}</div>
        <Footer server={server} />
      </div>
    </ServerContext.Provider>
  );
}

/** Frame the film, person, catalogue and about pages render their content in (the shell is already around it). */
/** The way back to the ask page at the top of every other page; names the thread when there is one. */
const noSubscribe = () => () => {};

export function BackToAsk() {
  const thread = useSyncExternalStore(noSubscribe, hasThread, () => false);
  return (
    <Link href="/" className="back-link">
      <span aria-hidden="true">←</span> {thread ? "Back to your questions" : "Ask a question"}
    </Link>
  );
}

export function Sheet({ children }: { children: ReactNode }) {
  return (
    <div className="page-body">
      <BackToAsk />
      {children}
    </div>
  );
}
