"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { askHref, getPerson, whenReady, type PersonDetail } from "@/lib/api";
import { FilmTile, Strip } from "./Catalog";
import { SiteHeader } from "./SiteHeader";

/* eslint-disable @next/next/no-img-element */

export function PersonView() {
  const { qid } = useParams<{ qid: string }>();
  // keyed by ID so state starts empty for every person without resetting it inside an effect
  return <PersonViewInner key={qid} qid={qid} />;
}

function PersonViewInner({ qid }: { qid: string }) {
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    whenReady(() => getPerson(qid, ctrl.signal), ctrl.signal)
      .then((p) => {
        setPerson(p);
        document.title = `${p.label} · CineGraph`;
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : "Could not load this person.");
      });
    return () => ctrl.abort();
  }, [qid]);

  if (error) {
    return (
      <div className="app app-doc">
        <SiteHeader />
        <main className="page-missing" id="main">
          <h1>Person not found</h1>
          <p>{error}</p>
          <Link href="/films">Browse all films</Link>
        </main>
      </div>
    );
  }

  if (!person) {
    return (
      <div className="app app-doc">
        <SiteHeader />
        <main className="detail detail-person" id="main" aria-busy="true">
          <div className="detail-top">
            <div className="detail-portrait tile-skeleton" />
            <div className="detail-intro">
              <p className="skeleton-line" />
              <p className="skeleton-line skeleton-short" />
            </div>
          </div>
        </main>
      </div>
    );
  }

  const active = person.credits.find((c) => c.role === role) ?? person.credits[0];
  const total = person.credits.reduce((n, c) => n + c.films.length, 0);

  return (
    <div className="app app-doc">
      <SiteHeader />
      <main className="detail detail-person" id="main">
        <div className="detail-top">
          {person.image ? (
            <img className="detail-portrait" src={person.image} alt={`Portrait of ${person.label}`} />
          ) : (
            <div className="detail-portrait detail-poster-empty">{person.label[0]}</div>
          )}
          <div className="detail-intro">
            <h1>{person.label}</h1>
            {person.description && <p className="detail-desc">{person.description}</p>}
            <dl className="facts-list facts-compact">
              {person.facts.map((f) => (
                <div key={f.property}>
                  <dt>{f.name}</dt>
                  <dd>{f.values.join(", ")}</dd>
                </div>
              ))}
            </dl>
            <p className="detail-ask">
              Ask the agent: <Link href={askHref(`Show me a picture of ${person.label}`)}>a portrait</Link>
              <Link href={askHref(`Which movies did ${person.label} direct?`)}>films directed</Link>
            </p>
          </div>
        </div>

        <section className="strip-block">
          <h2 className="block-title">
            Films <span>{total}</span>
          </h2>
          {person.credits.length === 0 ? (
            <p className="empty">The graph links no films to this person.</p>
          ) : (
            <>
              {person.credits.length > 1 && (
                <div className="sorts" role="tablist" aria-label="Role">
                  {person.credits.map((c) => (
                    <button
                      key={c.role}
                      type="button"
                      role="tab"
                      aria-selected={active.role === c.role}
                      onClick={() => setRole(c.role)}
                    >
                      {c.role} <span>{c.films.length}</span>
                    </button>
                  ))}
                </div>
              )}
              <ul className="tiles" role="tabpanel">
                {active.films.map((f) => (
                  <FilmTile key={`${active.role}-${f.qid}`} film={f} />
                ))}
              </ul>
            </>
          )}
        </section>

        <Strip title="Portraits" total={person.portraits_total} images={person.portraits} kind="portrait" alt={person.label} />
        <Strip title="In scenes" total={person.stills_total} images={person.stills} kind="still" alt={person.label} />
      </main>
    </div>
  );
}
