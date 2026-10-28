import Link from "next/link";
import type { ReactNode } from "react";
import { askHref } from "@/lib/api";
import { BackToAsk } from "./Shell";

/* eslint-disable @next/next/no-img-element */

// Small pieces shared by the film and person pages (design.md section 5).

/** The single main landmark of a page; the skip link targets #main. `side` sits in a right column from 1100 px. */
export function Page({ busy, side, children }: { busy?: boolean; side?: ReactNode; children: ReactNode }) {
  return (
    <main id="main" className="detail" aria-busy={busy || undefined}>
      <BackToAsk />
      <div className={`d-grid${side ? " d-has-side" : ""}`}>
        <div className="d-main">{children}</div>
        {side && <aside className="d-side" tabIndex={0} aria-label="Details">{side}</aside>}
      </div>
    </main>
  );
}

/** A plain sentence-case heading and its content. */
export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="d-section">
      <div className="d-section-head">
        <h2 className="block-title">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Row of images that scrolls inside its own box; each image opens the large version. */
export function ImageRow({ images, kind, alt }: { images: string[]; kind: "poster" | "still" | "portrait"; alt: string }) {
  return (
    <ul className={`strip strip-${kind}`} tabIndex={0} aria-label={`${alt}, ${kind}s`}>
      {images.map((src, i) => (
        <li key={src}>
          <a href={src.replace(/\/t\/p\/[^/]+\//, "/t/p/original/")} target="_blank" rel="noreferrer">
            <img src={src} alt={`${alt}, ${kind} ${i + 1}`} loading="lazy" />
          </a>
        </li>
      ))}
    </ul>
  );
}

/** Quiet chips that open the ask page with a ready question. */
export function AskChips({ items }: { items: { q: string; label: string }[] }) {
  return (
    <ul className="chip-list d-asks" aria-label="Ask the agent">
      {items.map((it) => (
        <li key={it.q}>
          <Link className="chip" href={askHref(it.q)}>
            {it.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export interface Fact {
  label: string;
  /** Wikidata property ID; shown only as a tooltip. */
  title?: string;
  value: ReactNode;
}

/** Two-column list: label muted, value in ink. */
export function Facts({ rows }: { rows: Fact[] }) {
  return (
    <dl className="kv">
      {rows.map((r) => (
        <div key={`${r.label}|${r.title ?? ""}`}>
          <dt title={r.title}>{r.label}</dt>
          <dd>{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Flat placeholder while a film or person loads. */
export function PageSkeleton({ round }: { round?: boolean }) {
  return (
    <Page busy>
      <div className="d-skeleton" aria-hidden="true">
        <div className="d-head">
          <div className={`d-art ${round ? "d-art-round" : ""} tile-skeleton`} />
          <div className="d-head-body">
            <span className="skeleton-line d-skeleton-title" />
            <span className="skeleton-line skeleton-short" />
          </div>
        </div>
        <span className="skeleton-line" />
        <span className="skeleton-line skeleton-short" />
        <ul className="tiles">
          {Array.from({ length: 6 }, (_, i) => (
            <li key={i} className="tile-skeleton" />
          ))}
        </ul>
      </div>
    </Page>
  );
}

/** Full-page message: a missing film or person, or a failed load. */
export function PageState({ title, text, actions }: { title: string; text: string; actions?: ReactNode }) {
  return (
    <main id="main" className="notfound">
      <BackToAsk />
      <h1 className="notfound-title">{title}</h1>
      <p className="note">{text}</p>
      {actions && <div className="d-state-actions">{actions}</div>}
    </main>
  );
}
