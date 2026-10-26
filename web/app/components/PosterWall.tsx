"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { filmHref, showcase, type FilmRow } from "@/lib/api";

/* eslint-disable @next/next/no-img-element */

/**
 * Columns of real posters from the graph drifting slowly in opposite directions.
 * A different random sample of the catalogue on every visit; every poster opens its film page.
 */
export function PosterWall({ ready }: { ready: boolean }) {
  const [films, setFilms] = useState<FilmRow[]>([]);

  useEffect(() => {
    if (!ready || films.length) return;
    const ctrl = new AbortController();
    showcase(ctrl.signal)
      .then(setFilms)
      .catch(() => {
        /* the wall is optional; the page works without it */
      });
    return () => ctrl.abort();
  }, [ready, films.length]);

  const columns = [0, 1, 2].map((c) => films.filter((_, i) => i % 3 === c));

  return (
    <div className={`wall ${films.length ? "wall-ready" : ""}`} aria-label="Films in the graph">
      {films.length === 0
        ? [0, 1, 2].map((c) => (
            <div key={c} className="wall-col">
              {[0, 1, 2, 3].map((i) => (
                <span key={i} className="wall-slot" />
              ))}
            </div>
          ))
        : columns.map((col, c) => (
            <div key={c} className={`wall-col wall-col-${c}`}>
              <div className="wall-track">
                {/* the second copy makes the loop seamless and is hidden from assistive tech */}
                {[...col, ...col].map((f, i) => (
                  <Link
                    key={`${f.qid}-${i}`}
                    href={filmHref(f.qid)}
                    className="wall-poster"
                    aria-hidden={i >= col.length ? true : undefined}
                    tabIndex={i >= col.length ? -1 : undefined}
                  >
                    <img src={f.image ?? ""} alt="" loading="lazy" />
                    <span className="wall-caption">
                      {f.label}
                      {f.year && <small>{f.year}</small>}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
    </div>
  );
}
