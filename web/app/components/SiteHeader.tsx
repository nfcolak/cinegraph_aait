"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

export const REPO = "https://github.com/nfcolak/cinegraph_aait";

const NAV = [
  { href: "/", label: "Ask" },
  { href: "/films", label: "Films" },
  { href: "/about", label: "How it works" },
];

/** Bar on top of the reading sheet: title on the left, page actions and Close on the right. */
function SheetBar({ title, onClose }: { title?: ReactNode; onClose?: () => void }) {
  const path = usePathname();
  const current = (href: string) =>
    (href === "/" ? path === "/" : path === href || path.startsWith(href.replace(/s$/, "") + "/")) ? "page" : undefined;
  return (
    <header className="sheet-bar">
      <div className="sheet-title">
        <Link href="/" onClick={onClose}>
          CineGraph
        </Link>
        {title && <span className="sheet-crumb">{title}</span>}
      </div>
      <nav className="sheet-actions" aria-label="Site">
        {NAV.map((n) => (
          <Link
            key={n.href}
            href={n.href}
            className="sheet-action sheet-nav"
            aria-current={current(n.href)}
            onClick={n.href === "/" ? onClose : undefined}
          >
            {n.label}
          </Link>
        ))}
        <a href={REPO} target="_blank" rel="noreferrer" className="sheet-action sheet-nav">
          Source ↗
        </a>
        <Link href="/" className="sheet-action sheet-close" onClick={onClose}>
          Close ×
        </Link>
      </nav>
    </header>
  );
}

/**
 * The white reading sheet floating on the black canvas; every page except the gallery
 * lives in one. Its body is the only vertical scroll container.
 */
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
  return (
    <div className="canvas">
      <div className="sheet">
        <SheetBar title={title} onClose={onClose} />
        <div className="sheet-body" ref={bodyRef} id="sheet-body">
          {children}
        </div>
      </div>
    </div>
  );
}

export interface ReaderSection {
  id: string;
  label: string;
}

/** Case-page layout: sticky side column (back link, title, meta, section index) and the reading column. */
export function Reader({
  back,
  title,
  meta,
  sections,
  extra,
  children,
  busy,
}: {
  back?: { href: string; label: string; onClick?: () => void };
  title: ReactNode;
  meta?: { label: string; value: ReactNode }[];
  sections?: ReaderSection[];
  extra?: ReactNode;
  children: ReactNode;
  busy?: boolean;
}) {
  const [active, setActive] = useState<string | null>(null);
  const ids = (sections ?? []).map((s) => s.id).join("|");
  const seen = useRef(new Map<string, number>());

  useEffect(() => {
    if (!ids) return;
    const order = ids.split("|");
    const root = document.getElementById("sheet-body");
    const map = seen.current;
    map.clear();
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) map.set(e.target.id, e.boundingClientRect.top);
          else map.delete(e.target.id);
        }
        const first = order.find((id) => map.has(id));
        if (first) setActive(first);
      },
      { root, rootMargin: "0px 0px -60% 0px", threshold: 0 },
    );
    order.forEach((id) => {
      const el = document.getElementById(id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [ids]);

  const current = active && ids.split("|").includes(active) ? active : (sections?.[0]?.id ?? null);

  return (
    <div className="reader" aria-busy={busy || undefined}>
      <aside className="reader-side">
        {back && (
          <Link href={back.href} className="reader-back" onClick={back.onClick}>
            ← {back.label}
          </Link>
        )}
        <h1 className="reader-title">{title}</h1>
        {meta && meta.length > 0 && (
          <dl className="reader-meta">
            {meta.map((m) => (
              <div key={m.label}>
                <dt>{m.label}</dt>
                <dd>{m.value}</dd>
              </div>
            ))}
          </dl>
        )}
        {extra}
        {sections && sections.length > 0 && (
          <nav className="reader-index" aria-label="On this page">
            {sections.map((s) => (
              <a
                key={s.id}
                href={`#${s.id}`}
                aria-current={current === s.id ? "true" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                  setActive(s.id);
                }}
              >
                {s.label}
              </a>
            ))}
          </nav>
        )}
      </aside>
      <main className="reader-main" id="main">
        {children}
      </main>
    </div>
  );
}
