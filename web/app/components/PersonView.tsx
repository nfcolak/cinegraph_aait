"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { askHref, getPerson, whenReady, type PersonDetail } from "@/lib/api";
import { FilmTile, Strip } from "./Catalog";
import { Reader, Sheet } from "./SiteHeader";

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
      <Sheet title="Person">
        <Reader back={{ href: "/films", label: "All films" }} title="Person not found">
          <p className="note">{error}</p>
        </Reader>
      </Sheet>
    );
  }

  if (!person) {
    return (
      <Sheet title="Person">
        <Reader back={{ href: "/films", label: "All films" }} title={<span className="skeleton-line" />} busy>
          <div className="skeleton-media skeleton-hero" />
          <p className="skeleton-line" />
        </Reader>
      </Sheet>
    );
  }

  const active = person.credits.find((c) => c.role === role) ?? person.credits[0];
  const total = person.credits.reduce((n, c) => n + c.films.length, 0);
  const sections = [
    { id: "films", label: "Films" },
    ...(person.portraits.length ? [{ id: "portraits", label: "Portraits" }] : []),
    ...(person.stills.length ? [{ id: "scenes", label: "In scenes" }] : []),
  ];

  return (
    <Sheet title={person.label}>
      <Reader
        back={{ href: "/films", label: "All films" }}
        title={person.label}
        meta={[
          ...(person.description ? [{ label: "About", value: person.description }] : []),
          { label: "In the graph", value: `${total} ${total === 1 ? "film" : "films"}` },
          ...person.facts.map((f) => ({ label: f.name, value: f.values.join(", ") })),
          {
            label: "Wikidata",
            value: (
              <a href={`https://www.wikidata.org/wiki/${person.qid}`} target="_blank" rel="noreferrer">
                {person.qid} ↗
              </a>
            ),
          },
        ]}
        extra={
          <div className="reader-ask">
            <p>Ask the agent</p>
            <ul>
              <li>
                <Link href={askHref(`Show me a picture of ${person.label}`)}>A portrait</Link>
              </li>
              <li>
                <Link href={askHref(`Which movies did ${person.label} direct?`)}>Films directed</Link>
              </li>
            </ul>
          </div>
        }
        sections={sections}
      >
        <div className="person-hero">
          {person.image ? (
            <img src={person.image} alt={`Portrait of ${person.label}`} />
          ) : (
            <span className="person-head-blank">{person.label[0]}</span>
          )}
        </div>

        <section className="block" id="films">
          <h2 className="block-title">
            Films <span>{total}</span>
          </h2>
          {person.credits.length === 0 ? (
            <p className="empty">The graph links no films to this person.</p>
          ) : (
            <>
              {person.credits.length > 1 && (
                <div className="pills" role="tablist" aria-label="Role">
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

        <Strip id="portraits" title="Portraits" total={person.portraits_total} images={person.portraits} kind="portrait" alt={person.label} />
        <Strip id="scenes" title="In scenes" total={person.stills_total} images={person.stills} kind="still" alt={person.label} />
      </Reader>
    </Sheet>
  );
}
