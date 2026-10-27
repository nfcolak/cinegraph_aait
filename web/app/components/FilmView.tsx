"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getFilm, getSimilar, personHref, whenReady, type FactValue, type FilmDetail, type FilmRow } from "@/lib/api";
import { FilmTile, Strip } from "./Catalog";
import { AskChips, HeroBand, HeroSkeleton, Ledger, Page, PageGrid, PageState, SectionTabs, type LedgerRow } from "./PageLayout";
import { Sheet } from "./Console";

/* eslint-disable @next/next/no-img-element */

const HERO_GENRES = 5;

export function FilmView() {
  const { qid } = useParams<{ qid: string }>();
  // keyed by ID so state starts empty for every film without resetting it inside an effect
  return <FilmViewInner key={qid} qid={qid} />;
}

function People({ values, more }: { values: FactValue[]; more?: number }) {
  return (
    <>
      {values.map((v, i) => (
        <span key={v.label + i}>
          {v.qid ? <Link href={personHref(v.qid)}>{v.label}</Link> : v.label}
          {i < values.length - 1 ? ", " : ""}
        </span>
      ))}
      {more ? <span className="muted"> and {more} more</span> : null}
    </>
  );
}

function FilmViewInner({ qid }: { qid: string }) {
  const [film, setFilm] = useState<FilmDetail | null>(null);
  const [similar, setSimilar] = useState<FilmRow[] | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    whenReady(() => getFilm(qid, ctrl.signal), ctrl.signal)
      .then((f) => {
        setFilm(f);
        return getSimilar(qid, ctrl.signal).then(setSimilar);
      })
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setError({
          message: e instanceof Error ? e.message : "Could not load this film.",
          status: e instanceof ApiError ? e.status : 0,
        });
      });
    return () => ctrl.abort();
  }, [qid]);

  // the tab title follows every state: loading, loaded, missing and failed
  useEffect(() => {
    document.title = film
      ? `${film.label}${film.year ? ` (${film.year})` : ""} · CineGraph`
      : error
        ? `${error.status === 404 ? "Not in the graph" : "Film not found"} · CineGraph`
        : "Loading film · CineGraph";
  }, [film, error]);

  if (error) {
    const missing = error.status === 404;
    return (
      <Sheet title="Film">
        <PageState
          code={missing ? "404" : "Error"}
          title={missing ? "Not in the graph" : "Film not found"}
          text={missing ? "The graph holds no film with this ID. Browse the catalogue or ask a question instead." : error.message}
          actions={
            <>
              <Link href="/films" className="ghost-button">
                All films
              </Link>
              <Link href="/" className="ghost-button">
                Ask
              </Link>
            </>
          }
        />
      </Sheet>
    );
  }

  if (!film) {
    return (
      <Sheet title="Film">
        <Page busy>
          <HeroSkeleton />
          <div className="page-grid page-grid-single" aria-hidden="true">
            <div>
              <span className="skeleton-line" />
              <span className="skeleton-line skeleton-short" />
              <ul className="tiles tiles-large">
                {Array.from({ length: 6 }, (_, i) => (
                  <li key={i} className="tile tile-skeleton" />
                ))}
              </ul>
            </div>
          </div>
        </Page>
      </Sheet>
    );
  }

  const directors = film.facts.find((f) => f.property === "P57")?.values ?? [];
  const backdrop = film.backdrop ?? film.stills[0] ?? film.image ?? null;

  const sections = [
    { id: "overview", label: "Overview" },
    { id: "cast", label: "Cast", count: film.cast_total || "" },
    ...(film.stills.length ? [{ id: "stills", label: "Stills", count: film.stills_total }] : []),
    ...(film.posters.length ? [{ id: "posters", label: "Posters", count: film.posters_total }] : []),
    { id: "similar", label: "Similar" },
  ];

  const rows: LedgerRow[] = [
    ...film.facts.map((f) => ({ label: f.name, code: f.property, value: <People values={f.values} more={f.more} /> })),
    ...(film.genres.length ? [{ label: "Genres", value: film.genres.join(", ") }] : []),
    ...(film.tags.length ? [{ label: "Keywords", value: film.tags.join(", ") }] : []),
    ...(film.imdb
      ? [
          {
            label: "IMDb",
            value: (
              <a href={`https://www.imdb.com/title/${film.imdb}/`} target="_blank" rel="noreferrer">
                {film.imdb} ↗
              </a>
            ),
          },
        ]
      : []),
  ];

  return (
    <Sheet title={film.label}>
      <Page>
        <HeroBand
          backdrop={backdrop}
          art={
            film.image ? (
              <img src={film.image} alt={`Poster of ${film.label}`} />
            ) : (
              <span className="hero-art-blank">{film.label}</span>
            )
          }
          kicker={`Film${film.year ? ` · ${film.year}` : ""}`}
          title={film.label}
          meta={
            <>
              {directors.length > 0 && (
                <p>
                  Directed by <People values={directors} />
                </p>
              )}
              {film.rating !== null && <p>rated {film.rating.toFixed(1)} / 5 by course users</p>}
            </>
          }
        >
          {film.genres.length > 0 && (
            <ul className="hero-tags" aria-label="Genres">
              {film.genres.slice(0, HERO_GENRES).map((g) => (
                <li key={g} className="tag">
                  {g}
                </li>
              ))}
              {film.genres.length > HERO_GENRES && <li className="tag">+{film.genres.length - HERO_GENRES}</li>}
            </ul>
          )}
          <div className="hero-links">
            <a className="tag hero-link" href={`https://www.wikidata.org/wiki/${film.qid}`} target="_blank" rel="noreferrer">
              Wikidata {film.qid} ↗
            </a>
            {film.imdb && (
              <a className="tag hero-link" href={`https://www.imdb.com/title/${film.imdb}/`} target="_blank" rel="noreferrer">
                IMDb {film.imdb} ↗
              </a>
            )}
          </div>
        </HeroBand>

        <AskChips
          items={[
            { q: `Who is the composer of ${film.label}?`, label: "Who composed it" },
            { q: `Recommend movies like ${film.label}`, label: "Films like it" },
            { q: `Show me a scene from ${film.label}`, label: "A scene" },
          ]}
        />

        <SectionTabs sections={sections} label="On this film page" />

        <PageGrid ledger={<Ledger title="Ledger" rows={rows} />} afterFirst>
          <section className="block" id="overview">
            <h2 className="block-title">Overview</h2>
            {film.description ? <p className="lede">{film.description}</p> : <p className="empty">The graph holds no description for this film.</p>}
            {film.date && <p className="overview-sub">Released {film.date}</p>}
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
                      {c.image ? <img src={c.image} alt="" loading="lazy" /> : <span className="person-tile-blank" aria-hidden="true">{c.label[0]}</span>}
                      <span>{c.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty">The graph lists no cast for this film.</p>
            )}
          </section>

          <Strip id="stills" title="Stills" total={film.stills_total} images={film.stills} kind="still" alt={film.label} />
          <Strip id="posters" title="Posters" total={film.posters_total} images={film.posters} kind="poster" alt={film.label} />

          <section className="block" id="similar" aria-busy={similar === null}>
            <h2 className="block-title">Similar films</h2>
            {similar === null ? (
              <>
                <p className="empty">Scoring every film against this one</p>
                <ul className="tiles tiles-large" aria-hidden="true">
                  {Array.from({ length: 6 }, (_, i) => (
                    <li key={i} className="tile tile-skeleton" />
                  ))}
                </ul>
              </>
            ) : similar.length ? (
              <ul className="tiles tiles-large tiles-over">
                {similar.map((f) => (
                  <FilmTile key={f.qid} film={f} />
                ))}
              </ul>
            ) : (
              <p className="empty">The recommender found no close match.</p>
            )}
          </section>
        </PageGrid>
      </Page>
    </Sheet>
  );
}
