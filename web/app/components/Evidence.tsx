"use client";

import Link from "next/link";
import { filmHref, personHref, type EntityCard, type Reply } from "@/lib/api";
import { graphShape, pathText } from "./graphShape";

// What sits under "How it was found": how the question was read, the graph path, the entities, the query and the log.

/** How the question was read, in one line. */
function readAs(reading: NonNullable<Reply["reading"]>): string | null {
  if (!reading.relation || !reading.subject) return null;
  const kind = reading.subject_kind && reading.subject_kind !== "film" ? ` (${reading.subject_kind})` : "";
  const via = reading.via_count > 0 ? `, through ${reading.via_count} ${reading.via_count === 1 ? "film" : "films"}` : "";
  const more = reading.parts.length > 1 ? `, ${reading.parts.length} questions` : "";
  return `${reading.relation} of ${reading.subject}${kind}${via}${more}`;
}

/** The entities the answer names, once each. */
function entitiesOf(reply: Reply): EntityCard[] {
  const seen = new Set<string>();
  const out: EntityCard[] = [];
  for (const c of [reply.subject, ...reply.cards, ...reply.seeds]) {
    if (!c?.qid || seen.has(c.qid)) continue;
    seen.add(c.qid);
    out.push(c);
  }
  return out;
}

export function Evidence({ reply, id, hidden }: { reply: Reply; id: string; hidden: boolean }) {
  const read = reply.reading ? readAs(reply.reading) : null;
  const shape = graphShape(reply);
  const entities = entitiesOf(reply);

  return (
    <div className="evidence" id={id} hidden={hidden}>
      {read && (
        <section>
          <h3 className="ev-label">Read as</h3>
          <p>{read}</p>
          {reply.rewritten && <p className="ev-sub">Rewritten as “{reply.rewritten}”</p>}
        </section>
      )}

      {shape && (
        <section>
          <h3 className="ev-label">Path</h3>
          <p>{pathText(shape)}</p>
        </section>
      )}

      {entities.length > 0 && (
        <section>
          <h3 className="ev-label">Entities</h3>
          <ul className="ev-entities">
            {entities.map((c) => (
              <li key={c.qid}>
                <Link href={c.type === "person" ? personHref(c.qid!) : filmHref(c.qid!)}>{c.label}</Link> <code>{c.qid}</code>
              </li>
            ))}
          </ul>
        </section>
      )}

      {reply.sparql && (
        <section>
          <h3 className="ev-label">Query</h3>
          <pre tabIndex={0} role="region" aria-label="SPARQL query">
            {reply.sparql}
          </pre>
        </section>
      )}

      {reply.trace.length > 0 && (
        <section>
          <h3 className="ev-label">Log</h3>
          <pre tabIndex={0} role="region" aria-label="Agent log">
            {reply.trace.join("\n")}
          </pre>
        </section>
      )}
    </div>
  );
}
