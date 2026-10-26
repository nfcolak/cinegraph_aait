"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { listFilms, personHref, search, whenReady, type FilmRow, type FilmSort, type PersonRow } from "@/lib/api";
import { FilmTile } from "./Catalog";
import { SiteHeader } from "./SiteHeader";

/* eslint-disable @next/next/no-img-element */

const SORTS: { id: FilmSort; label: string }[] = [
  { id: "popular", label: "Popular" },
  { id: "rating", label: "Highest rated" },
  { id: "newest", label: "Newest" },
  { id: "oldest", label: "Oldest" },
  { id: "title", label: "A to Z" },
];

export function FilmsBrowser() {
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<FilmSort>("popular");
  const key = `${sort}|${query}`;
  // results remember which query produced them, so a new query shows as loading without resetting state in an effect
  const [result, setResult] = useState<{ key: string; films: FilmRow[]; total: number | null; error: string | null }>({
    key: "",
    films: [],
    total: null,
    error: null,
  });
  const [people, setPeople] = useState<{ key: string; list: PersonRow[] }>({ key: "", list: [] });
  const [more, setMore] = useState(false);
  const reqId = useRef(0);
  const loading = result.key !== key || more;
  const films = result.key === key ? result.films : [];
  const total = result.key === key ? result.total : null;
  const error = result.key === key ? result.error : null;

  // debounce typing
  useEffect(() => {
    const t = setTimeout(() => setQuery(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const ctrl = new AbortController();
    const id = ++reqId.current;
    const k = `${sort}|${query}`;
    whenReady(() => listFilms(query, sort, 0, ctrl.signal), ctrl.signal)
      .then((res) => id === reqId.current && setResult({ key: k, films: res.films, total: res.total, error: null }))
      .catch((e) => {
        if (!ctrl.signal.aborted)
          setResult({ key: k, films: [], total: null, error: e instanceof Error ? e.message : "Could not load films." });
      });
    if (query.length >= 2) {
      search(query, ctrl.signal)
        .then((r) => id === reqId.current && setPeople({ key: query, list: r.people }))
        .catch(() => undefined);
    }
    return () => ctrl.abort();
  }, [query, sort]);

  const peopleHits = query.length >= 2 && people.key === query ? people.list : [];

  const loadMore = async () => {
    setMore(true);
    try {
      const res = await listFilms(query, sort, films.length);
      setResult((r) => (r.key === key ? { ...r, films: [...r.films, ...res.films], total: res.total } : r));
    } catch (e) {
      setResult((r) => ({ ...r, error: e instanceof Error ? e.message : "Could not load more films." }));
    } finally {
      setMore(false);
    }
  };

  return (
    <div className="app app-doc">
      <SiteHeader />
      <main className="catalog" id="main">
        <div className="catalog-head">
          <h1>Films</h1>
          <p className="catalog-count">
            {total === null ? "Loading the catalogue" : query ? `${total.toLocaleString("en")} matching “${query}”` : `${total.toLocaleString("en")} films in the graph`}
          </p>
        </div>

        <div className="catalog-controls">
          <label className="search">
            <span className="sr-only">Search films and people</span>
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search a title or a name"
              autoComplete="off"
            />
          </label>
          <div className="sorts" role="radiogroup" aria-label="Sort films">
            {SORTS.map((s) => (
              <button key={s.id} type="button" role="radio" aria-checked={sort === s.id} onClick={() => setSort(s.id)}>
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {peopleHits.length > 0 && (
          <section className="people-hits" aria-label="People">
            <h2 className="block-title">People</h2>
            <ul>
              {peopleHits.map((p) => (
                <li key={p.qid}>
                  <Link href={personHref(p.qid)}>
                    {p.image ? <img src={p.image} alt="" loading="lazy" /> : <span className="person-tile-blank">{p.label[0]}</span>}
                    <span>{p.label}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {films.length === 0 && !loading && !error && <p className="empty">No film title contains “{query}”. Try part of the title.</p>}

        <ul className="tiles catalog-grid" aria-busy={loading}>
          {films.map((f) => (
            <FilmTile key={f.qid} film={f} />
          ))}
          {loading && films.length === 0 && Array.from({ length: 18 }, (_, i) => <li key={i} className="tile tile-skeleton" />)}
        </ul>

        {total !== null && films.length < total && (
          <div className="more">
            <button type="button" onClick={loadMore} disabled={loading}>
              {loading ? "Loading" : `Show more (${(total - films.length).toLocaleString("en")} left)`}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
