"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, getPerson, whenReady, type PersonDetail } from "@/lib/api";
import { setBackdrop } from "@/lib/backdrop";
import { FilmTile } from "./Catalog";
import { AskChips, Facts, ImageRow, Page, PageSkeleton, PageState, Section, type Fact } from "./PageLayout";

/* eslint-disable @next/next/no-img-element */

export function PersonView() {
  const { qid } = useParams<{ qid: string }>();
  // keyed by ID so state starts empty for every person without resetting it inside an effect
  return <PersonViewInner key={qid} qid={qid} />;
}

const filmCount = (n: number) => `${n} ${n === 1 ? "film" : "films"}`;

/** "Director of 12 films · Actor in 41": the first role names the films, the others the count. */
function creditLine(credits: PersonDetail["credits"]): string {
  return credits
    .slice(0, 3)
    .map((c, i) => (i === 0 ? `${c.role} of ${filmCount(c.films.length)}` : `${c.role} in ${c.films.length}`))
    .join(" · ");
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

  // the portrait colours the page behind it; cleared when the page goes away
  const backdrop = person ? (person.image ?? person.portraits[0] ?? person.stills[0] ?? null) : null;
  useEffect(() => {
    setBackdrop(backdrop);
    return () => setBackdrop(null);
  }, [backdrop]);

  if (error) {
    const missing = error.status === 404;
    return (
      <PageState
        title={missing ? "This person is not in the graph." : "This person could not be loaded."}
        text={missing ? "The graph holds no person with this ID. Search the catalogue or ask a question instead." : error.message}
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

  if (!person) return <PageSkeleton round />;

  // QIDs and property codes live in tooltips only
  const rows: Fact[] = [
    ...person.facts.map((f) => ({ label: f.name, title: f.property, value: f.values.join(", ") })),
    {
      label: "Wikidata",
      title: person.qid,
      value: (
        <a href={`https://www.wikidata.org/wiki/${person.qid}`} target="_blank" rel="noreferrer" title={person.qid}>
          Open on Wikidata ↗
        </a>
      ),
    },
    ...(person.imdb
      ? [
          {
            label: "IMDb",
            title: person.imdb,
            value: (
              <a href={`https://www.imdb.com/name/${person.imdb}/`} target="_blank" rel="noreferrer" title={person.imdb}>
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
        <div className="d-art d-art-round">
          {person.image ? (
            <img src={person.image} alt={`Portrait of ${person.label}`} />
          ) : (
            <span className="person-head-blank" aria-hidden="true">
              {person.label[0]}
            </span>
          )}
        </div>
        <div className="d-head-body">
          <h1 className="d-title">{person.label}</h1>
          {person.description && <p className="d-sub">{person.description}</p>}
          {person.credits.length > 0 && <p className="d-sub">{creditLine(person.credits)}</p>}
        </div>
      </header>

      <AskChips
        items={[
          { q: `Show me a picture of ${person.label}`, label: "A portrait" },
          { q: `Which movies did ${person.label} direct?`, label: "Films directed" },
        ]}
      />

      {person.credits.length === 0 ? (
        <Section title="Films">
          <p className="empty">The graph links no films to this person.</p>
        </Section>
      ) : (
        person.credits.map((c) => (
          <Section key={c.role} title={c.role}>
            <ul className="tiles">
              {c.films.map((f) => (
                <FilmTile key={`${c.role}-${f.qid}`} film={f} />
              ))}
            </ul>
          </Section>
        ))
      )}

      {person.portraits.length > 0 && (
        <Section title="Portraits">
          <ImageRow images={person.portraits} kind="portrait" alt={person.label} />
        </Section>
      )}

      {person.stills.length > 0 && (
        <Section title="In scenes">
          <ImageRow images={person.stills} kind="still" alt={person.label} />
        </Section>
      )}
    </Page>
  );
}
