"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const REPO = "https://github.com/nfcolak/cinegraph_aait";

/** Top bar shared by every page. `extra` holds page-specific items such as the server status. */
export function SiteHeader({ extra, onHome }: { extra?: ReactNode; onHome?: () => void }) {
  const path = usePathname();
  const current = (href: string) =>
    (href === "/" ? path === "/" : path === href || path.startsWith(href.replace(/s$/, "") + "/") || path.startsWith(href + "/"))
      ? "page"
      : undefined;
  return (
    <header className="topbar">
      <Link href="/" className="brand" onClick={onHome}>
        CineGraph
      </Link>
      {extra}
      <nav className="topnav" aria-label="Site">
        <Link href="/" aria-current={current("/")} onClick={onHome}>
          Ask
        </Link>
        <Link href="/films" aria-current={current("/films")}>
          Films
        </Link>
        <Link href="/about" aria-current={current("/about")}>
          How it works
        </Link>
        <a href={REPO} target="_blank" rel="noreferrer" className="nav-source">
          Source
        </a>
      </nav>
    </header>
  );
}
