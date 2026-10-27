"use client";

import Link from "next/link";
import { filmHref, personHref, ROUTE_INFO, type EntityCard, type Reply, type Route } from "@/lib/api";
import { FilmTile } from "./Catalog";

/* eslint-disable @next/next/no-img-element -- TMDB images are remote and already sized by the CDN path */
// Posters and portraits sit next to their visible title or name, so they carry alt="" (as in Catalog.tsx).
// Only the picture an answer is about (the figure) has a descriptive alt.

function filmMeta(card: EntityCard, omitDirector?: string): string {
  const director = card.directors?.find((d) => d !== omitDirector);
  return [card.year, director].filter(Boolean).join(", ");
}

/** The answer's subject film: still or poster with the title over it, director and genre under it. */
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
        <div className="feature-facts">
          {film.directors && film.directors.length > 0 && (
            <span className="meta-pill">
              <span className="k">director</span>
              <span className="v">{film.directors.join(", ")}</span>
            </span>
          )}
          {film.genres && film.genres.length > 0 && (
            <span className="meta-pill">
              <span className="k">genre</span>
              <span className="v">{film.genres.join(", ")}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function PersonHeader({ person }: { person: EntityCard }) {
  return (
    <div className="person-head">
      {person.image ? (
        <img src={person.image} alt="" />
      ) : (
        <span className="person-head-blank" aria-hidden="true">
          {person.label.slice(0, 1)}
        </span>
      )}
      <div>
        <p className="person-head-kicker">Person</p>
        <h3>{person.qid ? <Link href={personHref(person.qid)}>{person.label}</Link> : person.label}</h3>
      </div>
    </div>
  );
}

function PosterTile({ card, omitDirector }: { card: EntityCard; omitDirector?: string }) {
  const meta = filmMeta(card, omitDirector);
  return (
    <li className="tile">
      <Link href={card.qid ? filmHref(card.qid) : "/films"} className="tile-link">
        <div className="tile-art">{card.image ? <img src={card.image} alt="" loading="lazy" /> : null}</div>
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
          <img src={card.image} alt="" loading="lazy" />
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

/** Image that sits blurred behind an answer: the subject film's still, else the first poster. */
export function backdropOf(reply: Reply): string | null {
  const s = reply.subject;
  if (s?.backdrop) return s.backdrop;
  if (s?.type === "film" && s.image) return s.image;
  if (reply.image?.url) return reply.image.url;
  return reply.cards.find((c) => c.type === "film" && (c.backdrop || c.image))?.backdrop ?? reply.cards.find((c) => c.image)?.image ?? null;
}

/**
 * The route colour of a reply: its route when it answered, "miss" when it did not.
 * A prediction that offers an embedding guess for a missing fact counts as a prediction.
 */
export function toneOf(reply: Reply): Route | "miss" {
  return reply.ok || (reply.route === "prediction" && reply.note) ? reply.route : "miss";
}

/** Short route name for a reply, used on tags. */
export function routeName(reply: Reply): string {
  const tone = toneOf(reply);
  return tone === "miss" ? "No answer" : ROUTE_INFO[tone].name;
}

/** The answer as the chat shows it: text or picture, then the films and people it names. */
export function AnswerBody({ reply }: { reply: Reply }) {
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
  // a prediction without a stored fact carries the embedding's guess in `note`
  const guess = !reply.ok && toneOf(reply) === "prediction" ? reply.note : null;

  return (
    <div className={`entry entry-${reply.route} ${reply.ok ? "" : "entry-miss"}`}>
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
          A prediction, not a stored fact. The graph has no {reply.relation ?? "value"} for this film, so the agent returns the nearest
          entity in its TransE embedding space. These guesses are often wrong.
        </p>
      )}
      {guess && <p className="note note-mark">{guess}</p>}
      {reply.hint && <p className="note">{reply.hint}</p>}

      {reply.route === "recommendation" && reply.seeds.length > 0 && reply.seeds.length <= 3 && (
        <p className="because">
          Because you liked{" "}
          {reply.seeds.map((s, i) => (
            <span key={s.qid ?? s.label} className="because-film">
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
    </div>
  );
}
