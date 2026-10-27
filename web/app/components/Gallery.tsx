"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { filmHref, showcase, type FilmRow } from "@/lib/api";

/* eslint-disable @next/next/no-img-element */

const larger = (url: string | null) => (url ? url.replace("/w342/", "/w500/") : "");

/**
 * Wave gallery of real posters from the graph (after the portfolio's Jesper gallery):
 * a horizontal track whose cards bend toward the viewer at the edges as it scrolls.
 * A different random sample on every visit; each card opens its film page.
 */
export function Gallery({ ready }: { ready: boolean }) {
  const [films, setFilms] = useState<FilmRow[]>([]);
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ready || films.length) return;
    const ctrl = new AbortController();
    showcase(ctrl.signal)
      .then((all) => setFilms(all.filter((f) => f.image).slice(0, 24)))
      .catch(() => {
        /* the gallery is optional; asking works without it */
      });
    return () => ctrl.abort();
  }, [ready, films.length]);

  // Bend every card by its distance from the viewport centre; plain DOM writes, no re-render.
  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    const paint = () => {
      frame = 0;
      const mid = window.innerWidth / 2;
      for (const card of Array.from(track.children) as HTMLElement[]) {
        const r = card.getBoundingClientRect();
        const d = Math.max(-1.6, Math.min(1.6, (r.left + r.width / 2 - mid) / mid));
        const rot = still ? 0 : d * 20;
        const z = still ? 0 : Math.abs(d) * 70;
        const lift = still ? 0 : d * d * -10;
        card.style.transform = `perspective(1300px) translate3d(0, ${lift}px, ${z}px) rotateY(${rot}deg)`;
      }
    };
    const queue = () => {
      if (!frame) frame = requestAnimationFrame(paint);
    };
    // A mouse wheel scrolls the gallery sideways; the landing page itself never scrolls.
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        track.scrollLeft += e.deltaY;
        e.preventDefault();
      }
    };
    queue();
    track.addEventListener("scroll", queue, { passive: true });
    track.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("resize", queue);
    return () => {
      cancelAnimationFrame(frame);
      track.removeEventListener("scroll", queue);
      track.removeEventListener("wheel", onWheel);
      window.removeEventListener("resize", queue);
    };
  }, [films.length]);

  // Start in the middle of the sample so cards bend on both sides.
  useEffect(() => {
    const track = trackRef.current;
    if (track && films.length) track.scrollLeft = (track.scrollWidth - track.clientWidth) / 2;
  }, [films.length]);

  return (
    <div className="gallery" aria-label="Films in the graph">
      <div className="gallery-floor" aria-hidden="true" />
      <div className={`gallery-track ${films.length ? "gallery-ready" : ""}`} ref={trackRef}>
        {films.length === 0
          ? Array.from({ length: 7 }, (_, i) => <span key={i} className="gallery-card gallery-slot" />)
          : films.map((f) => (
              <Link key={f.qid} href={filmHref(f.qid)} className="gallery-card">
                <img src={larger(f.image)} alt="" draggable={false} />
                <span className="gallery-shade" aria-hidden="true" />
                <span className="gallery-name">
                  {f.label}
                  {f.year && <small>{f.year}</small>}
                </span>
                <span className="gallery-go" aria-hidden="true">
                  →
                </span>
              </Link>
            ))}
      </div>
    </div>
  );
}
