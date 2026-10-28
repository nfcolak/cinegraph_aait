"use client";

import Link from "next/link";
import { filmHref, type FilmRow } from "@/lib/api";

/* eslint-disable @next/next/no-img-element */

/** Poster tile linking to the film page; used by the catalogue, filmographies and "similar" rows. */
export function FilmTile({ film, sub }: { film: FilmRow; sub?: string | null }) {
  return (
    <li className="tile">
      <Link href={filmHref(film.qid)} className="tile-link">
        <div className="tile-art">
          {film.image ? <img src={film.image} alt="" loading="lazy" /> : <span className="tile-blank" aria-hidden="true">{film.label}</span>}
        </div>
        <p className="tile-title">{film.label}</p>
        {(sub ?? film.year) && <p className="tile-meta">{sub ?? film.year}</p>}
      </Link>
    </li>
  );
}
