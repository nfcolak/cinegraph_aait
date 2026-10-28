"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError, getFilm, getSimilar, personHref, whenReady, type FactValue, type FilmDetail, type FilmRow } from "@/lib/api";
import { setBackdrop } from "@/lib/backdrop";
import { FilmTile } from "./Catalog";
import { AskChips, Facts, ImageRow, Page, PageSkeleton, PageState, Section, type Fact } from "./PageLayout";

/* eslint-disable @next/next/no-img-element */

const CAST_SHOWN = 12;

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
  const [allCast, setAllCast] = useState(false);

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

  // the film's own image colours the page behind it; cleared when the page goes away
  const backdrop = film ? (film.backdrop ?? film.stills[0] ?? film.image ?? null) : null;
  useEffect(() => {
    setBackdrop(backdrop);
    return () => setBackdrop(null);
  }, [backdrop]);

  if (error) {
    const missing = error.status === 404;
    return (
      <PageState
        title={missing ? "This film is not in the graph." : "This film could not be loaded."}
        text={missing ? "The graph holds no film with this ID. Browse the catalogue or ask a question instead." : error.message}
        actions={
          <>
            <Link href="/films" className="quiet">
              All films
            </Link>
            <Link href="/" className="quiet">
              Ask
            </Link>
          </>
        }
      />
    );
  }

  if (!film) return <PageSkeleton />;

  const directors = film.facts.find((f) => f.property === "P57")?.values ?? [];
  const cast = allCast ? film.cast : film.cast.slice(0, CAST_SHOWN);

  const subline: ReactNode[] = [];
  if (film.year) subline.push(film.year);
  if (directors.length) subline.push(<People key="dir" values={directors} />);
  if (film.genres.length) subline.push(film.genres.slice(0, 3).join(", "));

  // QIDs and property codes live in tooltips only
  const rows: Fact[] = [
    ...(film.date ? [{ label: "Released", value: film.date }] : []),
    ...film.facts.map((f) => ({ label: f.name, title: f.property, value: <People values={f.values} more={f.more} /> })),
    ...(film.genres.length ? [{ label: "Genres", value: film.genres.join(", ") }] : []),
    ...(film.tags.length ? [{ label: "Keywords", value: film.tags.join(", ") }] : []),
    {
      label: "Wikidata",
      title: film.qid,
      value: (
        <a href={`https://www.wikidata.org/wiki/${film.qid}`} target="_blank" rel="noreferrer" title={film.qid}>
          Open on Wikidata ↗
        </a>
      ),
    },
    ...(film.imdb
      ? [
          {
            label: "IMDb",
            title: film.imdb,
            value: (
              <a href={`https://www.imdb.com/title/${film.imdb}/`} target="_blank" rel="noreferrer" title={film.imdb}>
                Open on IMDb ↗
              </a>
            ),
          },
        ]
      : []),
  ];

  return (
    <Page
      side={
        <Section title="Details">
          <Facts rows={rows} />
        </Section>
      }
    >
      <header className="d-head">
        <div className="d-art">
          {film.image ? <img src={film.image} alt={`Poster of ${film.label}`} /> : <span className="tile-blank">{film.label}</span>}
        </div>
        <div className="d-head-body">
          <h1 className="d-title">{film.label}</h1>
          {subline.length > 0 && (
            <p className="d-sub">
              {subline.map((s, i) => (
                <span key={i}>
                  {i > 0 && " · "}
                  {s}
                </span>
              ))}
            </p>
          )}
          {film.rating !== null && <p className="d-sub">Rated {film.rating.toFixed(1)} / 5 by course users</p>}
        </div>
      </header>

      <AskChips
        items={[
          { q: `Who is the composer of ${film.label}?`, label: "Who composed it?" },
          { q: `Recommend movies like ${film.label}`, label: "Similar films" },
          { q: `Show me a scene from ${film.label}`, label: "A scene" },
        ]}
      />

      <Section title="About">
        {film.description ? <p className="d-lede">{film.description}</p> : <p className="empty">The graph holds no description for this film.</p>}
      </Section>

      <Section
        title="Cast"
        action={
          film.cast.length > CAST_SHOWN ? (
            <button type="button" className="quiet" aria-expanded={allCast} onClick={() => setAllCast((v) => !v)}>
              {allCast ? "Show fewer" : "Show all"}
            </button>
          ) : null
        }
      >
        {cast.length ? (
          <ul className={allCast ? "people" : "row"}>
            {cast.map((c) => (
              <li key={c.qid} className="person-tile-item">
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
      </Section>

      {film.stills.length > 0 && (
        <Section title="Stills">
          <ImageRow images={film.stills} kind="still" alt={film.label} />
        </Section>
      )}

      {film.posters.length > 0 && (
        <Section title="Posters">
          <ImageRow images={film.posters} kind="poster" alt={film.label} />
        </Section>
      )}

      <Section title="Similar films">
        {similar === null ? (
          <div aria-busy="true">
            <p className="empty">Looking for similar films…</p>
            <ul className="row" aria-hidden="true">
              {Array.from({ length: 6 }, (_, i) => (
                <li key={i} className="tile tile-skeleton" />
              ))}
            </ul>
          </div>
        ) : similar.length ? (
          <ul className="row">
            {similar.map((f) => (
              <FilmTile key={f.qid} film={f} />
            ))}
          </ul>
        ) : (
          <p className="empty">The recommender found no close match.</p>
        )}
      </Section>
    </Page>
  );
}
