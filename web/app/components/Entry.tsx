"use client";

import Link from "next/link";
import { filmHref, personHref, type EntityCard, type Reply } from "@/lib/api";

/* eslint-disable @next/next/no-img-element -- TMDB images are remote and already sized by the CDN path */
// Posters and portraits sit next to their visible title or name, so they carry alt="" (as in Catalog.tsx).
// Only the pictures an answer is about (the film poster beside the text, the figure) have a descriptive alt.

function filmMeta(card: EntityCard, omitDirector?: string): string {
  const director = card.directors?.find((d) => d !== omitDirector);
  return [card.year, director].filter(Boolean).join(", ");
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
    <li className="person-tile-item">
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

/** Image that sits blurred behind the page for an answer: the subject film's still, else the first poster. */
export function backdropOf(reply: Reply): string | null {
  const s = reply.subject;
  if (s?.backdrop) return s.backdrop;
  if (s?.type === "film" && s.image) return s.image;
  if (reply.image?.url) return reply.image.url;
  return reply.cards.find((c) => c.type === "film" && (c.backdrop || c.image))?.backdrop ?? reply.cards.find((c) => c.image)?.image ?? null;
}

/** A prediction: the graph had no stored fact, or the answer comes from the embedding space. */
export function isGuess(reply: Reply): boolean {
  return reply.route === "prediction" && (reply.ok || !!reply.note);
}

/** The answer as the thread shows it: the text (or picture) with its media, notes and suggestions. */
export function AnswerBody({ reply, onAsk }: { reply: Reply; onAsk: (question: string) => void }) {
  const subject = reply.subject;
  const multimedia = reply.route === "multimedia";
  const films = reply.cards.filter((c) => c.type === "film" && c.image);
  const people = reply.cards.filter((c) => c.type === "person");
  // the person an answer is about heads the people row
  if (!multimedia && subject?.type === "person" && !people.some((p) => p.qid === subject.qid)) people.unshift(subject);
  const answer = reply.answer.replace(/\.\.$/, ".");
  const pictureFilm = multimedia ? reply.cards.find((c) => c.type === "film") : undefined;
  const picturePerson = multimedia ? reply.cards.find((c) => c.type === "person") : undefined;
  const caption = (() => {
    const kind = reply.image?.kind;
    if (kind === "scene" && picturePerson && pictureFilm) return `in ${pictureFilm.label}${pictureFilm.year ? `, ${pictureFilm.year}` : ""}`;
    if (kind === "scene") return pictureFilm?.year ? `Still, ${pictureFilm.year}` : "Still";
    if (kind === "poster") return pictureFilm ? filmMeta(pictureFilm) : "Poster";
    return "Portrait";
  })();
  const guess = isGuess(reply);
  // a stored-fact miss carries the embedding's guess in `note`; a found prediction gets the standing explanation
  const guessNote = guess ? (reply.ok ? `A prediction, not a stored fact. The graph has no ${reply.relation ?? "value"} for this film, so the agent returns the nearest entity in its TransE embedding space. These guesses are often wrong.` : reply.note) : null;
  const poster = reply.ok && !multimedia && subject?.type === "film" && subject.image ? subject : null;
  const hasText = answer.trim().length > 0;

  return (
    <div className="answer-body">
      {reply.image && (
        <figure className="picture">
          <img src={reply.image.url} alt={`${reply.image.kind} of ${reply.image.label ?? "the requested entity"}`} />
          <figcaption>{[reply.image.label, caption].filter(Boolean).join(" · ")}</figcaption>
        </figure>
      )}

      {(hasText || poster) && (
        <div className={`answer-row ${poster ? "with-poster" : ""}`}>
          {poster && (
            <Link href={poster.qid ? filmHref(poster.qid) : "/films"} className="answer-poster">
              <img src={poster.image!} alt={`Poster of ${poster.label}`} />
            </Link>
          )}
          <div className="answer-text">
            {hasText && (
              <p className="answer">
                {guess && (
                  <span className="guess-mark">
                    <span className="guess-dot" aria-hidden="true" />
                    Guess
                  </span>
                )}
                {answer}
              </p>
            )}
            {guessNote && <p className="note">{guessNote}</p>}
            {reply.hint && <p className="note">{reply.hint}</p>}
          </div>
        </div>
      )}

      {!multimedia && films.length > 0 && (
        <ul className="row" aria-label="Films">
          {films.map((c) => (
            <PosterTile key={c.qid ?? c.label} card={c} omitDirector={reply.inverse ? subject?.label : undefined} />
          ))}
        </ul>
      )}

      {!multimedia && people.length > 0 && (
        <ul className="row" aria-label="People">
          {people.map((c) => (
            <PersonTile key={c.qid ?? c.label} card={c} />
          ))}
        </ul>
      )}

      {(reply.suggestions.length > 0 || reply.alternatives.length > 0) && (
        <div className="suggest">
          {reply.suggestions.length > 0 && (
            <>
              <p className="suggest-title">{reply.suggestions_title}</p>
              <ul className="chip-list">
                {reply.suggestions.map((f) => (
                  <li key={f.qid}>
                    <Link className="chip sans" href={filmHref(f.qid)}>
                      {f.year ? `${f.label} (${f.year})` : f.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
          {reply.alternatives.length > 0 && (
            <>
              <p className="suggest-title">Same name in the graph</p>
              <ul className="chip-list">
                {reply.alternatives.map((alt) => (
                  <li key={alt.qid}>
                    <button type="button" className="chip sans" onClick={() => onAsk(alt.ask)}>
                      {`${alt.year ? `${alt.label} (${alt.year})` : alt.label}${alt.kind && alt.kind !== "film" ? `, ${alt.kind}` : ""}`}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
