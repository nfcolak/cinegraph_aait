"use client";

import Link from "next/link";
import { useState } from "react";
import { askHref, filmHref, formatLatency, personHref, ROUTE_INFO, type EntityCard, type Reply } from "@/lib/api";
import { FilmTile } from "./Catalog";

/* eslint-disable @next/next/no-img-element -- TMDB images are remote and already sized by the CDN path */

function filmMeta(card: EntityCard, omitDirector?: string): string {
  const director = card.directors?.find((d) => d !== omitDirector);
  return [card.year, director].filter(Boolean).join(", ");
}

/** Letterboxd-style header: the film's still bleeds across the entry, the poster sits over its lower edge. */
function FilmHeader({ film }: { film: EntityCard }) {
  return (
    <div className={`film-head ${film.backdrop ? "" : "film-head-plain"}`}>
      {film.backdrop && (
        <div className="film-head-still" aria-hidden="true">
          <img src={film.backdrop} alt="" />
        </div>
      )}
      <div className="film-head-row">
        {film.image && <img className="film-head-poster" src={film.image} alt={`Poster of ${film.label}`} />}
        <div className="film-head-text">
          <h3>
            {film.qid ? <Link href={filmHref(film.qid)}>{film.label}</Link> : film.label}
            {film.year && <span className="film-head-year">{film.year}</span>}
          </h3>
          {film.directors && film.directors.length > 0 && (
            <p className="film-head-by">
              Directed by <strong>{film.directors.join(" and ")}</strong>
            </p>
          )}
          {film.genres && film.genres.length > 0 && <p className="film-head-genres">{film.genres.join(", ")}</p>}
        </div>
      </div>
    </div>
  );
}

function PersonHeader({ person }: { person: EntityCard }) {
  return (
    <div className="person-head">
      {person.image ? (
        <img src={person.image} alt={`Portrait of ${person.label}`} />
      ) : (
        <span className="person-head-blank" aria-hidden="true">
          {person.label.slice(0, 1)}
        </span>
      )}
      <h3>{person.qid ? <Link href={personHref(person.qid)}>{person.label}</Link> : person.label}</h3>
    </div>
  );
}

function PosterTile({ card, omitDirector }: { card: EntityCard; omitDirector?: string }) {
  const meta = filmMeta(card, omitDirector);
  return (
    <li className="tile">
      <Link href={card.qid ? filmHref(card.qid) : "/films"} className="tile-link">
        <div className="tile-art">{card.image ? <img src={card.image} alt={`Poster of ${card.label}`} loading="lazy" /> : null}</div>
        <p className="tile-title">{card.label}</p>
        {meta && <p className="tile-meta">{meta}</p>}
      </Link>
    </li>
  );
}

function PersonTile({ card }: { card: EntityCard }) {
  return (
    <li>
      <Link className="person-tile" href={card.qid ? personHref(card.qid) : "/films"}>
      {card.image ? (
        <img src={card.image} alt={`Portrait of ${card.label}`} loading="lazy" />
      ) : (
        <span className="person-tile-blank" aria-hidden="true">
          {card.label.slice(0, 1)}
        </span>
      )}
      <span>{card.label}</span>
      </Link>
    </li>
  );
}

/** The triple the agent queried, written as one line: subject, property, objects. */
function GraphPath({ reply }: { reply: Reply }) {
  if (!reply.ok || !reply.relation || !reply.subject?.label) return null;
  const n = Math.max(reply.count, reply.objects.length);
  const objects =
    n > 3 ? `${n} ${reply.inverse ? "titles" : "entries"}` : reply.objects.length > 0 ? reply.objects.join(", ") : reply.answer.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? "?";
  return (
    <p className="path" aria-label="Path through the knowledge graph">
      <span className="path-node">
        {reply.subject.label}
        {reply.subject.qid && <code>{reply.subject.qid}</code>}
      </span>
      <span className="path-edge" data-dir={reply.inverse ? "in" : "out"}>
        {reply.relation}
        {reply.property && <code>{reply.property}</code>}
      </span>
      <span className="path-node">{objects}</span>
    </p>
  );
}

/** One quiet line: how the question was read. */
function ReadAs({ reading }: { reading: NonNullable<Reply["reading"]> }) {
  if (!reading.relation || !reading.subject) return null;
  const kind = reading.subject_kind && reading.subject_kind !== "film" ? ` (${reading.subject_kind})` : "";
  const via = reading.via_count > 0 ? `, through ${reading.via_count} ${reading.via_count === 1 ? "film" : "films"}` : "";
  const more = reading.parts.length > 1 ? `, ${reading.parts.length} questions` : "";
  return (
    <p className="read-as">
      Read as: {reading.relation} of {reading.subject}
      {kind}
      {via}
      {more}
    </p>
  );
}

export function Entry({ reply }: { reply: Reply }) {
  const [open, setOpen] = useState(false);
  const info = ROUTE_INFO[reply.route];
  const subject = reply.subject;
  const films = reply.cards.filter((c) => c.type === "film" && c.image);
  const people = reply.cards.filter((c) => c.type === "person");
  const answer = reply.answer.replace(/\.\.$/, ".");
  const pictureFilm = reply.route === "multimedia" ? reply.cards.find((c) => c.type === "film") : undefined;
  const picturePerson = reply.route === "multimedia" ? reply.cards.find((c) => c.type === "person") : undefined;
  const caption = (() => {
    const kind = reply.image?.kind;
    if (kind === "scene" && picturePerson && pictureFilm) return `in ${pictureFilm.label}${pictureFilm.year ? `, ${pictureFilm.year}` : ""}`;
    if (kind === "scene") return pictureFilm?.year ? `Still, ${pictureFilm.year}` : "Still";
    if (kind === "poster") return pictureFilm ? filmMeta(pictureFilm) : "Poster";
    return "Portrait";
  })();

  return (
    <article className={`entry entry-${reply.route} ${reply.ok ? "" : "entry-miss"}`}>
      {reply.ok && subject?.type === "film" && reply.route !== "multimedia" && <FilmHeader film={subject} />}
      {reply.ok && subject?.type === "person" && reply.route !== "multimedia" && <PersonHeader person={subject} />}

      {reply.image ? (
        <figure className={`picture picture-${reply.image.kind}`}>
          <img src={reply.image.url} alt={`${reply.image.kind} of ${reply.image.label ?? "the requested entity"}`} />
          <figcaption>
            <strong>{reply.image.label}</strong>
            {caption && <span>{caption}</span>}
          </figcaption>
        </figure>
      ) : (
        <p className={`answer ${reply.route === "prediction" ? "answer-guess" : ""}`}>{answer}</p>
      )}

      {reply.ok && reply.route === "prediction" && (
        <p className="caveat">
          A prediction, not a stored fact. The graph has no {reply.relation ?? "value"} for this film, so the agent returns the
          nearest entity in its TransE embedding space. These guesses are often wrong.
        </p>
      )}

      {reply.hint && <p className="caveat">{reply.hint}</p>}

      {reply.reading && <ReadAs reading={reply.reading} />}

      {reply.alternatives.length > 0 && (
        <p className="alternatives">
          <span>Other entries named {reply.reading?.subject ?? reply.alternatives[0].label}:</span>
          {reply.alternatives.map((alt) => (
            <Link key={alt.qid} href={askHref(alt.ask)}>
              {alt.year ? `${alt.label} (${alt.year})` : alt.label}
              {alt.kind && alt.kind !== "film" ? `, ${alt.kind}` : ""}
            </Link>
          ))}
        </p>
      )}

      {!reply.ok && !reply.hint && (
        <p className="caveat">
          Name the film or person as it is titled and ask one thing at a time, for example “Who directed Heat?”
        </p>
      )}

      {reply.suggestions.length > 0 && (
        <div className="suggestions">
          <p>{reply.suggestions_title}:</p>
          <ul className="tiles">
            {reply.suggestions.map((f) => (
              <FilmTile key={f.qid} film={f} />
            ))}
          </ul>
        </div>
      )}

      {reply.route === "recommendation" && reply.seeds.length > 0 && (
        <p className="because">
          Because you liked{" "}
          {reply.seeds.map((s, i) => (
            <span key={s.label} className="because-film">
              {s.image && <img src={s.image} alt="" />}
              {s.label}
              {i < reply.seeds.length - 1 ? (i === reply.seeds.length - 2 ? " and " : ", ") : ""}
            </span>
          ))}
        </p>
      )}

      {reply.route !== "multimedia" && films.length > 0 && (
        <ul className={`tiles ${reply.route === "recommendation" ? "tiles-large" : ""}`}>
          {films.map((c) => (
            <PosterTile key={c.qid ?? c.label} card={c} omitDirector={reply.inverse ? subject?.label : undefined} />
          ))}
        </ul>
      )}

      {reply.route !== "multimedia" && people.length > 0 && (
        <ul className="people">
          {people.map((c) => (
            <PersonTile key={c.qid ?? c.label} card={c} />
          ))}
        </ul>
      )}

      {reply.route !== "recommendation" && reply.route !== "multimedia" && <GraphPath reply={reply} />}

      <footer className="entry-foot">
        <span className="entry-route">{reply.ok ? info.name : "No answer"}</span>
        <span>{info.method}</span>
        <span>{formatLatency(reply.latency_ms)}</span>
        {(reply.trace.length > 0 || reply.sparql) && (
          <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {open ? "Hide details" : reply.sparql ? "Show query" : "Show log"}
          </button>
        )}
      </footer>

      {open && (
        <div className="details">
          {reply.rewritten && (
            <p>
              Rewritten as <q>{reply.rewritten}</q>
            </p>
          )}
          {reply.sparql && <pre aria-label="SPARQL query">{reply.sparql}</pre>}
          {reply.trace.length > 0 && <pre aria-label="Agent log">{reply.trace.join("\n")}</pre>}
        </div>
      )}
    </article>
  );
}
