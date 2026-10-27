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
          {film.image ? <img src={film.image} alt="" loading="lazy" /> : <span className="tile-blank">{film.label}</span>}
        </div>
        <p className="tile-title">{film.label}</p>
        {(sub ?? film.year) && <p className="tile-meta">{sub ?? film.year}</p>}
      </Link>
    </li>
  );
}

/** Horizontal strip of images that scrolls inside itself; the page never scrolls sideways. */
export function Strip({
  id,
  title,
  total,
  images,
  kind,
  alt,
}: {
  id?: string;
  title: string;
  total: number;
  images: string[];
  kind: "poster" | "still" | "portrait";
  alt: string;
}) {
  if (!images.length) return null;
  return (
    <section className="block" id={id}>
      <h2 className="block-title">
        {title} <span>{total > images.length ? `${images.length} of ${total}` : total}</span>
      </h2>
      <ul className={`strip strip-${kind}`} tabIndex={0} aria-label={title}>
        {images.map((src, i) => (
          <li key={src}>
            <a href={src.replace(/\/t\/p\/[^/]+\//, "/t/p/original/")} target="_blank" rel="noreferrer">
              <img src={src} alt={`${alt}, ${kind} ${i + 1}`} loading="lazy" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
