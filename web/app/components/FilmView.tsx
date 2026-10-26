"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { askHref, getFilm, getSimilar, personHref, whenReady, type FilmDetail, type FilmRow } from "@/lib/api";
import { FilmTile, Strip } from "./Catalog";
import { SiteHeader } from "./SiteHeader";

/* eslint-disable @next/next/no-img-element */

export function FilmView() {
  const { qid } = useParams<{ qid: string }>();
  // keyed by ID so state starts empty for every film without resetting it inside an effect
  return <FilmViewInner key={qid} qid={qid} />;
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
      <div className="app app-doc">
        <SiteHeader />
        <main className="page-missing" id="main">
          <h1>Film not found</h1>
          <p>{error}</p>
          <Link href="/films">Browse all films</Link>
        </main>
      </div>
    );
  }

  if (!film) {
    return (
      <div className="app app-doc">
        <SiteHeader />
        <main className="detail" id="main" aria-busy="true">
          <div className="detail-band detail-band-loading" />
          <div className="detail-top">
            <div className="detail-poster tile-skeleton" />
            <div className="detail-intro">
              <p className="skeleton-line" />
              <p className="skeleton-line skeleton-short" />
            </div>
          </div>
        </main>
      </div>
    );
  }

  const directors = film.facts.find((f) => f.property === "P57")?.values ?? [];
  const crew = film.facts.filter((f) => f.property !== "P57");

  return (
    <div className="app app-doc">
      <SiteHeader />
      <main className="detail" id="main">
        <div className={`detail-band ${film.backdrop ? "" : "detail-band-empty"}`} aria-hidden="true">
          {film.backdrop && <img src={film.backdrop} alt="" />}
        </div>

        <div className="detail-top">
          {film.image ? (
            <img className="detail-poster" src={film.image} alt={`Poster of ${film.label}`} />
          ) : (
            <div className="detail-poster detail-poster-empty">{film.label}</div>
          )}
          <div className="detail-intro">
            <h1>
              {film.label}
              {film.year && <span className="detail-year">{film.year}</span>}
            </h1>
            {directors.length > 0 && (
              <p className="detail-by">
                Directed by{" "}
                {directors.map((d, i) => (
                  <span key={d.label}>
                    {d.qid ? <Link href={personHref(d.qid)}>{d.label}</Link> : d.label}
                    {i < directors.length - 1 ? " and " : ""}
                  </span>
                ))}
              </p>
            )}
            {film.description && <p className="detail-desc">{film.description}</p>}
            {film.genres.length > 0 && <p className="detail-genres">{film.genres.join(", ")}</p>}
            <p className="detail-ask">
              Ask the agent:{" "}
              <Link href={askHref(`Who is the composer of ${film.label}?`)}>composer</Link>
              <Link href={askHref(`Recommend movies like ${film.label}`)}>films like it</Link>
              <Link href={askHref(`Show me a scene from ${film.label}`)}>a scene</Link>
            </p>
          </div>
        </div>

        <div className="detail-cols">
          <section aria-label="Cast">
            <h2 className="block-title">
              Cast <span>{film.cast_total > film.cast.length ? `${film.cast.length} of ${film.cast_total}` : film.cast_total || ""}</span>
            </h2>
            {film.cast.length ? (
              <ul className="cast">
                {film.cast.map((c) => (
                  <li key={c.qid}>
                    <Link href={personHref(c.qid)}>
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

          <section aria-label="Details">
            <h2 className="block-title">Details</h2>
            <dl className="facts-list">
              {film.date && (
                <div>
                  <dt>Released</dt>
                  <dd>{film.date}</dd>
                </div>
              )}
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
                    {f.more > 0 && <span className="facts-more"> and {f.more} more</span>}
                  </dd>
                </div>
              ))}
              {film.rating !== null && (
                <div>
                  <dt>Course user rating</dt>
                  <dd>{film.rating.toFixed(1)} of 5</dd>
                </div>
              )}
              {film.tags.length > 0 && (
                <div>
                  <dt>Keywords</dt>
                  <dd>{film.tags.join(", ")}</dd>
                </div>
              )}
              <div>
                <dt>Wikidata</dt>
                <dd>
                  <a href={`https://www.wikidata.org/wiki/${film.qid}`} target="_blank" rel="noreferrer">
                    {film.qid}
                  </a>
                  {film.imdb && (
                    <>
                      {", IMDb "}
                      <a href={`https://www.imdb.com/title/${film.imdb}/`} target="_blank" rel="noreferrer">
                        {film.imdb}
                      </a>
                    </>
                  )}
                </dd>
              </div>
            </dl>
          </section>
        </div>

        <Strip title="Stills" total={film.stills_total} images={film.stills} kind="still" alt={film.label} />
        <Strip title="Posters" total={film.posters_total} images={film.posters} kind="poster" alt={film.label} />

        <section className="strip-block">
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
      </main>
    </div>
  );
}
