"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getPerson, whenReady, type PersonDetail } from "@/lib/api";
import { FilmTile, Strip } from "./Catalog";
import { AskChips, HeroBand, HeroSkeleton, Ledger, Page, PageGrid, PageState, SectionTabs, StatBox, type LedgerRow } from "./PageLayout";
import { Sheet } from "./Console";

/* eslint-disable @next/next/no-img-element */

export function PersonView() {
  const { qid } = useParams<{ qid: string }>();
  // keyed by ID so state starts empty for every person without resetting it inside an effect
  return <PersonViewInner key={qid} qid={qid} />;
}

function PersonViewInner({ qid }: { qid: string }) {
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [error, setError] = useState<{ message: string; status: number } | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    whenReady(() => getPerson(qid, ctrl.signal), ctrl.signal)
      .then((p) => {
        setPerson(p);
      })
      .catch((e) => {
        if (ctrl.signal.aborted) return;
        setError({
          message: e instanceof Error ? e.message : "Could not load this person.",
          status: e instanceof ApiError ? e.status : 0,
        });
      });
    return () => ctrl.abort();
  }, [qid]);

  // the tab title follows every state: loading, loaded, missing and failed
  useEffect(() => {
    document.title = person
      ? `${person.label} · CineGraph`
      : error
        ? `${error.status === 404 ? "Not in the graph" : "Person not found"} · CineGraph`
        : "Loading person · CineGraph";
  }, [person, error]);

  if (error) {
    const missing = error.status === 404;
    return (
      <Sheet title="Person">
        <PageState
          code={missing ? "404" : "Error"}
          title={missing ? "Not in the graph" : "Person not found"}
          text={missing ? "The graph holds no person with this ID. Search the catalogue or ask a question instead." : error.message}
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

  if (!person) {
    return (
      <Sheet title="Person">
        <Page busy>
          <HeroSkeleton />
          <div className="page-grid page-grid-single" aria-hidden="true">
            <div>
              <span className="skeleton-line" />
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

  const total = person.credits.reduce((n, c) => n + c.films.length, 0);
  const roleId = (role: string) => `role-${role.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  const sections = [
    ...(person.credits.length
      ? person.credits.map((c) => ({ id: roleId(c.role), label: c.role, count: c.films.length }))
      : [{ id: "films", label: "Films" }]),
    ...(person.portraits.length ? [{ id: "portraits", label: "Portraits", count: person.portraits_total }] : []),
    ...(person.stills.length ? [{ id: "scenes", label: "In scenes", count: person.stills_total }] : []),
  ];

  const rows: LedgerRow[] = [
    { label: "In the graph", value: `${total} ${total === 1 ? "film" : "films"}` },
    ...person.facts.map((f) => ({ label: f.name, code: f.property, value: f.values.join(", ") })),
    {
      label: "Wikidata",
      value: (
        <a href={`https://www.wikidata.org/wiki/${person.qid}`} target="_blank" rel="noreferrer">
          {person.qid} ↗
        </a>
      ),
    },
  ];

  return (
    <Sheet title={person.label}>
      <Page>
        <HeroBand
          backdrop={person.stills[0] ?? person.image}
          art={
            person.image ? (
              <img src={person.image} alt={`Portrait of ${person.label}`} />
            ) : (
              <span className="hero-art-blank hero-art-initial" aria-hidden="true">{person.label[0]}</span>
            )
          }
          kicker="Person"
          title={person.label}
          meta={person.description ? <p>{person.description}</p> : undefined}
        >
          {person.credits.length > 0 && (
            <StatBox label="Credits by role" items={person.credits.map((c) => ({ label: c.role.toLowerCase(), value: c.films.length }))} />
          )}
        </HeroBand>

        <AskChips
          items={[
            { q: `Show me a picture of ${person.label}`, label: "A portrait" },
            { q: `Which movies did ${person.label} direct?`, label: "Films directed" },
          ]}
        />

        <SectionTabs sections={sections} label="On this person page" />

        <PageGrid ledger={<Ledger title="Ledger" rows={rows} />}>
          {person.credits.length === 0 ? (
            <section className="block" id="films">
              <h2 className="block-title">Films</h2>
              <p className="empty">The graph links no films to this person.</p>
            </section>
          ) : (
            person.credits.map((c) => (
              <section className="block" id={roleId(c.role)} key={c.role}>
                <h2 className="block-title">
                  {c.role} <span>{c.films.length}</span>
                </h2>
                <ul className="tiles tiles-large tiles-over">
                  {c.films.map((f) => (
                    <FilmTile key={`${c.role}-${f.qid}`} film={f} />
                  ))}
                </ul>
              </section>
            ))
          )}

          <Strip id="portraits" title="Portraits" total={person.portraits_total} images={person.portraits} kind="portrait" alt={person.label} />
          <Strip id="scenes" title="In scenes" total={person.stills_total} images={person.stills} kind="still" alt={person.label} />
        </PageGrid>
      </Page>
    </Sheet>
  );
}
