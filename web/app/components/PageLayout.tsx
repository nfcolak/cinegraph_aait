"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { askHref } from "@/lib/api";

/* eslint-disable @next/next/no-img-element */

// Primitives shared by the film, person, catalogue and about pages (design.md section 5).

/** The single main landmark of a page; the skip link targets #main. */
export function Page({ busy, children }: { busy?: boolean; children: ReactNode }) {
  return (
    <main id="main" className="page" aria-busy={busy || undefined}>
      {children}
    </main>
  );
}

/** Full-width band: the image blurred and darkened behind, art (poster or portrait) and text on top. */
export function HeroBand({
  backdrop,
  art,
  kicker,
  title,
  meta,
  children,
}: {
  backdrop?: string | null;
  art?: ReactNode;
  kicker: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="hero-band">
      {backdrop && <img className="hero-band-bg" src={backdrop} alt="" aria-hidden="true" />}
      <div className="hero-band-inner">
        {art && <div className="hero-band-art">{art}</div>}
        <div className="hero-band-body">
          <p className="hero-band-kicker">{kicker}</p>
          <h1 className="hero-band-title">{title}</h1>
          {meta && <div className="hero-band-meta">{meta}</div>}
          {children}
        </div>
      </div>
    </header>
  );
}

/** Placeholder hero while a film or person loads. */
export function HeroSkeleton() {
  return (
    <div className="hero-band hero-band-skeleton" aria-hidden="true">
      <div className="hero-band-inner">
        <div className="hero-band-art skeleton-media" />
        <div className="hero-band-body">
          <span className="skeleton-line skeleton-short" />
          <span className="skeleton-line hero-skeleton-title" />
          <span className="skeleton-line" />
          <span className="skeleton-line skeleton-short" />
        </div>
      </div>
    </div>
  );
}

export interface StatItem {
  label: string;
  value: ReactNode;
}

/** Boxed row of label and figure cells. */
export function StatBox({ items, label }: { items: StatItem[]; label?: string }) {
  return (
    <dl className="stat-box" role={label ? "group" : undefined} aria-label={label}>
      {items.map((s) => (
        <div key={s.label}>
          <dt>{s.label}</dt>
          <dd>{s.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Amber "?" chips that open the ask page with a ready question. */
export function AskChips({ items, label = "Ask the agent" }: { items: { q: string; label: string }[]; label?: string }) {
  return (
    <div className="ask-chips">
      <span className="ask-chips-label">{label}</span>
      <ul>
        {items.map((it) => (
          <li key={it.q}>
            <Link className="ask-chip" href={askHref(it.q)}>
              <span aria-hidden="true">?</span>
              {it.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface PageSection {
  id: string;
  label: string;
  count?: ReactNode;
}

/** Sticky section index: jumps to a section, follows the scroll, and moves with the arrow keys. */
export function SectionTabs({ sections, label = "On this page" }: { sections: PageSection[]; label?: string }) {
  const [active, setActive] = useState<string | null>(null);
  const ids = sections.map((s) => s.id).join("|");
  const nav = useRef<HTMLElement>(null);
  const links = useRef(new Map<string, HTMLAnchorElement>());
  // while a click scrolls smoothly, the scroll listener must not flip the active tab back and forth
  const locked = useRef(false);
  const current = active && ids.split("|").includes(active) ? active : (sections[0]?.id ?? null);

  useEffect(() => {
    const root = document.getElementById("sheet-body");
    if (!root || !ids) return;
    const order = ids.split("|");
    let frame = 0;
    const update = () => {
      frame = 0;
      if (locked.current) return;
      const line = root.getBoundingClientRect().top + 80; // just under the sticky tabs
      let now = order[0];
      for (const id of order) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= line) now = id;
      }
      if (root.scrollTop > 0 && root.scrollTop + root.clientHeight >= root.scrollHeight - 2) now = order[order.length - 1];
      setActive(now);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      root.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [ids]);

  // keep the active tab visible in the tab row on narrow screens
  useEffect(() => {
    const el = current ? links.current.get(current) : null;
    const row = nav.current;
    if (!el || !row) return;
    if (el.offsetLeft < row.scrollLeft + 8) row.scrollLeft = Math.max(0, el.offsetLeft - 16);
    else if (el.offsetLeft + el.offsetWidth > row.scrollLeft + row.clientWidth - 8)
      row.scrollLeft = el.offsetLeft + el.offsetWidth - row.clientWidth + 16;
  }, [current]);

  const go = (id: string) => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduce) {
      locked.current = true;
      setTimeout(() => (locked.current = false), 700);
    }
    document.getElementById(id)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    setActive(id);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    const order = ids.split("|");
    const at = Math.max(0, order.indexOf(current ?? ""));
    let to = at;
    if (e.key === "ArrowRight") to = (at + 1) % order.length;
    else if (e.key === "ArrowLeft") to = (at - 1 + order.length) % order.length;
    else if (e.key === "Home") to = 0;
    else if (e.key === "End") to = order.length - 1;
    else return;
    e.preventDefault();
    links.current.get(order[to])?.focus();
    go(order[to]);
  };

  return (
    <div className="section-tabs">
      <nav className="section-tabs-row" aria-label={label} ref={nav} onKeyDown={onKeyDown}>
        {sections.map((s) => (
          <a
            key={s.id}
            ref={(el) => {
              if (el) links.current.set(s.id, el);
              else links.current.delete(s.id);
            }}
            href={`#${s.id}`}
            className="section-tab"
            aria-current={current === s.id ? "location" : undefined}
            tabIndex={current === s.id ? 0 : -1}
            onClick={(e) => {
              e.preventDefault();
              go(s.id);
            }}
          >
            {s.label}
            {s.count !== undefined && s.count !== "" && <span>{s.count}</span>}
          </a>
        ))}
      </nav>
    </div>
  );
}

export interface LedgerRow {
  label: string;
  /** Wikidata property code, drawn in red. */
  code?: string;
  value: ReactNode;
}

/** Sticky side panel with the look of the evidence panel: mono heading and key-value rows. */
export function Ledger({ title = "Ledger", rows }: { title?: string; rows: LedgerRow[] }) {
  return (
    <aside className="ledger" aria-label={title}>
      <h2 className="ledger-title">
        <span className="ledger-mark" aria-hidden="true" />
        {title}
        <span className="ledger-count">{rows.length}</span>
      </h2>
      <dl className="kv">
        {rows.map((r) => (
          <div key={`${r.label}|${r.code ?? ""}`}>
            <dt>
              {r.label}
              {r.code && <code>{r.code}</code>}
            </dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

/**
 * Two-column body: sections in the main column and the ledger beside them. Below 980 px the ledger
 * sits under the first section (`afterFirst`) or at the top.
 */
export function PageGrid({ ledger, afterFirst, children }: { ledger?: ReactNode; afterFirst?: boolean; children: ReactNode }) {
  return (
    <div className={`page-grid${ledger ? "" : " page-grid-single"}${afterFirst ? " ledger-after-first" : ""}`}>
      {!afterFirst && ledger}
      {children}
      {afterFirst && ledger}
    </div>
  );
}

/** Full-page message: a missing film or person, or a failed load. */
export function PageState({ code, title, text, actions }: { code: string; title: string; text: string; actions?: ReactNode }) {
  return (
    <main id="main" className="notfound">
      <div className="notfound-code">{code}</div>
      <h1 className="notfound-title">{title}</h1>
      <p className="notfound-text">{text}</p>
      {actions && <div className="notfound-actions">{actions}</div>}
    </main>
  );
}
