"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { askHref, getFilm, getSimilar, personHref, whenReady, type FilmDetail, type FilmRow } from "@/lib/api";
import { FilmTile, Strip } from "./Catalog";
import { Reader, Sheet } from "./SiteHeader";

/* eslint-disable @next/next/no-img-element */

export function FilmView() {
  const { qid } = useParams<{ qid: string }>();
  // keyed by ID so state starts empty for every film without resetting it inside an effect
  return <FilmViewInner key={qid} qid={qid} />;
}

function AskLinks({ links }: { links: { q: string; label: string }[] }) {
  return (
    <div className="reader-ask">
      <p>Ask the agent</p>
      <ul>
        {links.map((l) => (
          <li key={l.q}>
            <Link href={askHref(l.q)}>{l.label}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FilmViewInner({ qid }: { qid: string }) {
  const [film, setFilm] = useState<FilmDetail | null>(null);
  const [similar, setSimilar] = useState<FilmRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    whenReady(() => getFilm(qid, ctrl.signal), ctrl.signal)
      .then((f) => {
        setFilm(f);
        document.title = `${f.label}${f.year ? ` (${f.year})` : ""} · CineGraph`;
        return getSimilar(qid, ctrl.signal).then(setSimilar);
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "Could not load this film.");
      });
    return () => ctrl.abort();
  }, [qid]);

  if (error) {
    return (
      <Sheet title="Film">
        <Reader back={{ href: "/films", label: "All films" }} title="Film not found">
          <p className="note">{error}</p>
        </Reader>
      </Sheet>
    );
  }

  if (!film) {
    return (
      <Sheet title="Film">
        <Reader back={{ href: "/films", label: "All films" }} title={<span className="skeleton-line" />} busy>
          <div className="skeleton-media skeleton-hero" />
          <p className="skeleton-line" />
          <p className="skeleton-line skeleton-short" />
        </Reader>
      </Sheet>
    );
  }

  const directors = film.facts.find((f) => f.property === "P57")?.values ?? [];
  const crew = film.facts.filter((f) => f.property !== "P57");
  const hero = film.backdrop ?? film.stills[0] ?? null;

  const sections = [
    { id: "overview", label: "Overview" },
    { id: "cast", label: "Cast" },
    { id: "details", label: "Details" },
    ...(film.stills.length ? [{ id: "stills", label: "Stills" }] : []),
    ...(film.posters.length ? [{ id: "posters", label: "Posters" }] : []),
    { id: "similar", label: "Similar films" },
  ];

  return (
    <Sheet title={film.label}>
      <Reader
        back={{ href: "/films", label: "All films" }}
        title={film.label}
        meta={[
          { label: "Type", value: `Film${film.year ? ` · ${film.year}` : ""}` },
          ...(directors.length
            ? [
                {
                  label: "Directed by",
                  value: directors.map((d, i) => (
                    <span key={d.label}>
                      {d.qid ? <Link href={personHref(d.qid)}>{d.label}</Link> : d.label}
                      {i < directors.length - 1 ? ", " : ""}
                    </span>
                  )),
                },
              ]
            : []),
          ...(film.genres.length ? [{ label: "Genre", value: film.genres.join(", ") }] : []),
          {
            label: "Wikidata",
            value: (
              <a href={`https://www.wikidata.org/wiki/${film.qid}`} target="_blank" rel="noreferrer">
                {film.qid} ↗
              </a>
            ),
          },
        ]}
        extra={
          <AskLinks
            links={[
              { q: `Who is the composer of ${film.label}?`, label: "Who composed it" },
              { q: `Recommend movies like ${film.label}`, label: "Films like it" },
              { q: `Show me a scene from ${film.label}`, label: "A scene" },
            ]}
          />
        }
        sections={sections}
      >
        <section className="block" id="overview">
          <div className={`hero ${hero ? "" : "hero-poster"}`}>
            {hero ? (
              <img src={hero} alt="" />
            ) : film.image ? (
              <img src={film.image} alt={`Poster of ${film.label}`} />
            ) : (
              <span className="hero-blank">{film.label}</span>
            )}
          </div>
          <div className="overview">
            {film.image && hero && <img className="overview-poster" src={film.image} alt={`Poster of ${film.label}`} />}
            <div>
              {film.description && <p className="lede">{film.description}</p>}
              {film.date && (
                <p className="overview-sub">
                  Released {film.date}
                  {film.rating !== null ? ` · rated ${film.rating.toFixed(1)} of 5 by course users` : ""}
                </p>
              )}
            </div>
          </div>
        </section>

        <section className="block" id="cast">
          <h2 className="block-title">
            Cast <span>{film.cast_total > film.cast.length ? `${film.cast.length} of ${film.cast_total}` : film.cast_total || ""}</span>
          </h2>
          {film.cast.length ? (
            <ul className="people">
              {film.cast.map((c) => (
                <li key={c.qid}>
                  <Link className="person-tile" href={personHref(c.qid)}>
                    {c.image ? <img src={c.image} alt="" loading="lazy" /> : <span className="person-tile-blank">{c.label[0]}</span>}
                    <span>{c.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty">The graph lists no cast for this film.</p>
          )}
        </section>

        <section className="block" id="details">
          <h2 className="block-title">Details</h2>
          <dl className="kv">
            {crew.map((f) => (
              <div key={f.property}>
                <dt>
                  {f.name} <code>{f.property}</code>
                </dt>
                <dd>
                  {f.values.map((v, i) => (
                    <span key={v.label + i}>
                      {v.qid ? <Link href={personHref(v.qid)}>{v.label}</Link> : v.label}
                      {i < f.values.length - 1 ? ", " : ""}
                    </span>
                  ))}
                  {f.more > 0 && <span className="muted"> and {f.more} more</span>}
                </dd>
              </div>
            ))}
            {film.tags.length > 0 && (
              <div>
                <dt>Keywords</dt>
                <dd>{film.tags.join(", ")}</dd>
              </div>
            )}
            {film.imdb && (
              <div>
                <dt>IMDb</dt>
                <dd>
                  <a href={`https://www.imdb.com/title/${film.imdb}/`} target="_blank" rel="noreferrer">
                    {film.imdb} ↗
                  </a>
                </dd>
              </div>
            )}
          </dl>
        </section>

        <Strip id="stills" title="Stills" total={film.stills_total} images={film.stills} kind="still" alt={film.label} />
        <Strip id="posters" title="Posters" total={film.posters_total} images={film.posters} kind="poster" alt={film.label} />

        <section className="block" id="similar">
          <h2 className="block-title">Similar films</h2>
          {similar === null ? (
            <p className="empty">Scoring every film against this one</p>
          ) : similar.length ? (
            <ul className="tiles">
              {similar.map((f) => (
                <FilmTile key={f.qid} film={f} />
              ))}
            </ul>
          ) : (
            <p className="empty">The recommender found no close match.</p>
          )}
        </section>
      </Reader>
    </Sheet>
  );
}
