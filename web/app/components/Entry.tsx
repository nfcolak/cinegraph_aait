"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { askHref, filmHref, formatLatency, personHref, ROUTE_INFO, type EntityCard, type Reply } from "@/lib/api";
import { FilmTile } from "./Catalog";

/* eslint-disable @next/next/no-img-element -- TMDB images are remote and already sized by the CDN path */

function filmMeta(card: EntityCard, omitDirector?: string): string {
  const director = card.directors?.find((d) => d !== omitDirector);
  return [card.year, director].filter(Boolean).join(", ");
}

/** Gallery-card header: the film's still fills a rounded frame, its title set over the lower edge. */
function FilmHeader({ film }: { film: EntityCard }) {
  const href = film.qid ? filmHref(film.qid) : null;
  const art = film.backdrop ?? film.image;
  return (
    <div className="feature">
      <div className={`feature-frame ${film.backdrop ? "" : "feature-frame-poster"}`}>
        {art && <img src={art} alt="" />}
        <span className="feature-shade" aria-hidden="true" />
        <h3 className="feature-name">
          {href ? <Link href={href}>{film.label}</Link> : film.label}
          {film.year && <small>{film.year}</small>}
        </h3>
        {href && (
          <Link href={href} className="feature-go" aria-label={`Open ${film.label}`}>
            →
          </Link>
        )}
      </div>
      {((film.directors && film.directors.length > 0) || (film.genres && film.genres.length > 0)) && (
        <dl className="kv kv-inline">
          {film.directors && film.directors.length > 0 && (
            <div>
              <dt>Directed by</dt>
              <dd>{film.directors.join(", ")}</dd>
            </div>
          )}
          {film.genres && film.genres.length > 0 && (
            <div>
              <dt>Genre</dt>
              <dd>{film.genres.join(", ")}</dd>
            </div>
          )}
        </dl>
      )}
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
function graphPath(reply: Reply): ReactNode {
  if (!reply.ok || !reply.relation || !reply.subject?.label) return null;
  const n = Math.max(reply.count, reply.objects.length);
  const objects =
    n > 3
      ? `${n} ${reply.inverse ? "titles" : "entries"}`
      : reply.objects.length > 0
        ? reply.objects.join(", ")
        : (reply.answer.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? "?");
  return (
    <span className="path" aria-label="Path through the knowledge graph">
      <span>
        {reply.subject.label} {reply.subject.qid && <code>{reply.subject.qid}</code>}
      </span>
      <span className="path-edge">
        {reply.inverse ? "←" : "→"} {reply.relation} {reply.property && <code>{reply.property}</code>} {reply.inverse ? "←" : "→"}
      </span>
      <span>{objects}</span>
    </span>
  );
}

/** How the question was read, in one line. */
function readAs(reading: NonNullable<Reply["reading"]>): string | null {
  if (!reading.relation || !reading.subject) return null;
  const kind = reading.subject_kind && reading.subject_kind !== "film" ? ` (${reading.subject_kind})` : "";
  const via = reading.via_count > 0 ? `, through ${reading.via_count} ${reading.via_count === 1 ? "film" : "films"}` : "";
  const more = reading.parts.length > 1 ? `, ${reading.parts.length} questions` : "";
  return `${reading.relation} of ${reading.subject}${kind}${via}${more}`;
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
  const read = reply.reading ? readAs(reply.reading) : null;
  const path = reply.route !== "recommendation" && reply.route !== "multimedia" ? graphPath(reply) : null;

  return (
    <article className={`entry entry-${reply.route} ${reply.ok ? "" : "entry-miss"}`}>
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

      {reply.ok && subject?.type === "film" && reply.route !== "multimedia" && <FilmHeader film={subject} />}
      {reply.ok && subject?.type === "person" && reply.route !== "multimedia" && <PersonHeader person={subject} />}

      {reply.ok && reply.route === "prediction" && (
        <p className="note note-mark">
          A prediction, not a stored fact. The graph has no {reply.relation ?? "value"} for this film, so the agent returns the
          nearest entity in its TransE embedding space. These guesses are often wrong.
        </p>
      )}
      {reply.hint && <p className="note">{reply.hint}</p>}
      {!reply.ok && !reply.hint && (
        <p className="note">Name the film or person as it is titled and ask one thing at a time, for example “Who directed Heat?”</p>
      )}

      {reply.route === "recommendation" && reply.seeds.length > 0 && reply.seeds.length <= 3 && (
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

      {reply.suggestions.length > 0 && (
        <div className="suggestions">
          <p className="block-title">{reply.suggestions_title}</p>
          <ul className="tiles">
            {reply.suggestions.map((f) => (
              <FilmTile key={f.qid} film={f} />
            ))}
          </ul>
        </div>
      )}

      <dl className="kv entry-meta">
        {read && (
          <div>
            <dt>Read as</dt>
            <dd>{read}</dd>
          </div>
        )}
        {reply.alternatives.length > 0 && (
          <div>
            <dt>Same name</dt>
            <dd className="alternatives">
              {reply.alternatives.map((alt) => (
                <Link key={alt.qid} href={askHref(alt.ask)}>
                  {alt.year ? `${alt.label} (${alt.year})` : alt.label}
                  {alt.kind && alt.kind !== "film" ? `, ${alt.kind}` : ""}
                </Link>
              ))}
            </dd>
          </div>
        )}
        {path && (
          <div>
            <dt>Path</dt>
            <dd>{path}</dd>
          </div>
        )}
        <div>
          <dt>Answered by</dt>
          <dd>
            <span className={`route route-${reply.ok ? reply.route : "miss"}`}>{reply.ok ? info.name : "No answer"}</span>
            {" · "}
            {info.method}
            {" · "}
            {formatLatency(reply.latency_ms)}
          </dd>
        </div>
      </dl>

      {(reply.trace.length > 0 || reply.sparql) && (
        <button type="button" className="ghost-button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? "Hide details" : reply.sparql ? "Show query" : "Show log"}
        </button>
      )}

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
