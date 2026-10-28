"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { listFilms, personHref, search, whenReady, type FilmRow, type FilmSort, type PersonRow } from "@/lib/api";
import { FilmTile } from "./Catalog";
import { Sheet } from "./Shell";

/* eslint-disable @next/next/no-img-element */

const SORTS: { id: FilmSort; label: string }[] = [
  { id: "popular", label: "Popular" },
  { id: "rating", label: "Top rated" },
  { id: "newest", label: "Newest" },
  { id: "oldest", label: "Oldest" },
  { id: "title", label: "A–Z" },
];

const fmt = (n: number) => n.toLocaleString("en");

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
  const [catalogue, setCatalogue] = useState<number | null>(null);
  const [more, setMore] = useState(false);
  const reqId = useRef(0);
  const sortRefs = useRef(new Map<FilmSort, HTMLButtonElement>());
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
      .then((res) => {
        if (id !== reqId.current) return;
        setResult({ key: k, films: res.films, total: res.total, error: null });
        if (!query) setCatalogue(res.total);
      })
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

  // arrow keys move through the sort options like a radio group
  const onSortKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const at = SORTS.findIndex((s) => s.id === sort);
    let to = at;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") to = (at + 1) % SORTS.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") to = (at - 1 + SORTS.length) % SORTS.length;
    else return;
    e.preventDefault();
    setSort(SORTS[to].id);
    sortRefs.current.get(SORTS[to].id)?.focus();
  };

  const count =
    total === null
      ? catalogue === null
        ? "Loading the catalogue"
        : `${fmt(catalogue)} films`
      : query
        ? `${fmt(total)} ${total === 1 ? "film matches" : "films match"} “${query}”`
        : `${fmt(total)} films`;

  return (
    <Sheet>
      <main id="main" className="cat" aria-busy={loading || undefined}>
        <header className="cat-head">
          <h1>Films</h1>
          <p className="cat-count" role="status">
            {count}
          </p>
        </header>

        <label className="cat-search">
          <span className="sr-only">Search films and people</span>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search a title or a name"
            autoComplete="off"
          />
        </label>

        <div className="cat-sort" role="radiogroup" aria-label="Sort films" onKeyDown={onSortKey}>
          {SORTS.map((s) => (
            <button
              key={s.id}
              ref={(el) => {
                if (el) sortRefs.current.set(s.id, el);
                else sortRefs.current.delete(s.id);
              }}
              type="button"
              role="radio"
              className="quiet"
              aria-checked={sort === s.id}
              tabIndex={sort === s.id ? 0 : -1}
              onClick={() => setSort(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>

        {peopleHits.length > 0 && (
          <section className="cat-people" aria-label="People">
            <h2 className="block-title">People</h2>
            <ul className="row" tabIndex={0} aria-label="People matching the search">
              {peopleHits.map((p) => (
                <li key={p.qid} className="person-tile-item">
                  <Link className="person-tile" href={personHref(p.qid)}>
                    {p.image ? <img src={p.image} alt="" loading="lazy" /> : <span className="person-tile-blank" aria-hidden="true">{p.label[0]}</span>}
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

        {films.length === 0 && !loading && !error && (
          <p className="empty cat-empty">
            {query
              ? `No film title contains “${query}”.${peopleHits.length ? " The people above match the name." : " Try part of the title."}`
              : "The catalogue is empty."}
          </p>
        )}

        <ul className="tiles cat-grid" aria-busy={loading}>
          {films.map((f) => (
            <FilmTile key={f.qid} film={f} />
          ))}
          {loading && Array.from({ length: films.length === 0 ? 18 : 6 }, (_, i) => <li key={`sk${i}`} className="tile-skeleton" />)}
        </ul>

        {total !== null && films.length < total && (
          <div className="cat-more">
            <button type="button" className="quiet" onClick={loadMore} disabled={loading}>
              Show more
            </button>
          </div>
        )}
      </main>
    </Sheet>
  );
}
