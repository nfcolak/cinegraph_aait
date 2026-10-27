"use client";

import Link from "next/link";
import { useId, type ReactNode } from "react";
import { askHref, filmHref, formatLatency, personHref, ROUTE_INFO, type Reply } from "@/lib/api";
import { describeShape, graphShape, type GraphShape } from "./graphShape";
import { routeName, toneOf } from "./Entry";

export { graphShape, type GraphShape };

/** The triple the agent queried: subject, property, objects. */
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
    <span className="path" role="group" aria-label="Path through the knowledge graph">
      <span className="path-node">
        {reply.subject.label} {reply.subject.qid && <code>{reply.subject.qid}</code>}
      </span>
      <span className="path-edge">
        {reply.inverse ? "←" : "→"} {reply.relation} {reply.property && <code>{reply.property}</code>} {reply.inverse ? "←" : "→"}
      </span>
      <span className="path-node">{objects}</span>
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

const clip = (t: string, n: number) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);

// SVG geometry in viewBox units. The panel shows the drawing at 0.94 to 1.14 times, so 12 px node text
// stays at 11.3 px or more; the gap between the node columns (88) fits a 10-character label pill.
const W = 300;
const NODE_W = 104;
const NODE_H = 26;
const ROW_H = 34;
const PAD_X = 2;

/** The answer drawn as a small graph: node(s), the relation as an edge, node(s). */
export function EvidenceGraph({ shape }: { shape: GraphShape }) {
  const markerId = `egraph-arrow-${useId().replace(/\W/g, "")}`;
  const rightRows = shape.right.length + (shape.more ? 1 : 0);
  const rows = Math.max(shape.left.length, rightRows);
  const h = Math.max(96, rows * ROW_H + 28);
  const ly = (i: number) => h / 2 + (i - (shape.left.length - 1) / 2) * ROW_H;
  const ry = (i: number) => h / 2 + (i - (rightRows - 1) / 2) * ROW_H;
  const lx = PAD_X + NODE_W; // edges leave the left nodes here
  const rx = W - PAD_X - NODE_W; // and reach the right nodes here
  const mid = W / 2;
  const label = clip(shape.edge, 10);
  const labelW = label.length * 6.9 + 14; // 11.5 px mono is 6.9 units per character
  return (
    <svg className="egraph" viewBox={`0 0 ${W} ${h}`} role="img" aria-label={describeShape(shape)}>
      <defs>
        <marker id={markerId} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 8 4 0 8z" className="egraph-head" />
        </marker>
      </defs>
      {shape.left.map((_, i) =>
        Array.from({ length: rightRows }, (_, j) => (
          <path
            key={`${i}-${j}`}
            className={`egraph-edge ${shape.more && j === rightRows - 1 ? "egraph-edge-more" : ""}`}
            d={`M${lx} ${ly(i)} C ${mid} ${ly(i)}, ${mid} ${ry(j)}, ${rx} ${ry(j)}`}
            markerEnd={shape.reverse ? undefined : `url(#${markerId})`}
            markerStart={shape.reverse ? `url(#${markerId})` : undefined}
          />
        )),
      )}
      <g transform={`translate(${mid} ${h / 2})`}>
        <rect className="egraph-label-bg" x={-labelW / 2} y={-10} width={labelW} height={20} rx={10} />
        <title>{shape.edge}</title>
        <text className="egraph-label" textAnchor="middle" dy="3.5">
          {label}
        </text>
      </g>
      {shape.left.map((t, i) => (
        <g key={`l${i}`} transform={`translate(${PAD_X} ${ly(i) - NODE_H / 2})`}>
          <title>{t}</title>
          <rect className="egraph-node egraph-node-subject" width={NODE_W} height={NODE_H} rx={6} />
          <text className="egraph-text" x={NODE_W / 2} y={17} textAnchor="middle">
            {clip(t, 14)}
          </text>
        </g>
      ))}
      {shape.right.map((t, j) => (
        <g key={`r${j}`} transform={`translate(${rx} ${ry(j) - NODE_H / 2})`}>
          <title>{t}</title>
          <rect className="egraph-node" width={NODE_W} height={NODE_H} rx={6} />
          <text className="egraph-text" x={NODE_W / 2} y={17} textAnchor="middle">
            {clip(t, 14)}
          </text>
        </g>
      ))}
      {shape.more > 0 && (
        <g transform={`translate(${rx} ${ry(rightRows - 1) - NODE_H / 2})`}>
          <rect className="egraph-node egraph-node-more" width={NODE_W} height={NODE_H} rx={6} />
          <text className="egraph-text egraph-text-more" x={NODE_W / 2} y={17} textAnchor="middle">
            +{shape.more} more
          </text>
        </g>
      )}
    </svg>
  );
}

/** Number of things the evidence panel lists for a reply (shown on the evidence button). */
export function evidenceCount(reply: Reply): number {
  return (reply.sparql ? 1 : 0) + (reply.trace.length ? 1 : 0) + reply.cards.length + reply.alternatives.length;
}

function EvidenceCard({ label, tone, children }: { label: string; tone?: "accent" | "red" | "amber"; children: ReactNode }) {
  return (
    <section className={`evidence-card ${tone ? `tone-${tone}` : ""}`}>
      <h3 className="evidence-head">{label}</h3>
      <div className="evidence-body">{children}</div>
    </section>
  );
}

/** Everything behind one answer: the drawn graph, how it was read, the path, the query and the agent's log. */
export function Evidence({ reply, onAsk }: { reply: Reply; onAsk?: (question: string) => void }) {
  const info = ROUTE_INFO[reply.route];
  const read = reply.reading ? readAs(reply.reading) : null;
  const path = reply.route !== "recommendation" && reply.route !== "multimedia" ? graphPath(reply) : null;
  const entities = reply.cards.filter((c) => c.qid);
  const shape = graphShape(reply);
  const tone = toneOf(reply);

  return (
    <div className="evidence">
      {shape && (
        <EvidenceCard label="In the graph" tone="red">
          <EvidenceGraph shape={shape} />
        </EvidenceCard>
      )}

      <EvidenceCard label="Answered by" tone={tone === "miss" ? "amber" : "accent"}>
        <p>
          <span className={`route route-${tone}`}>{routeName(reply)}</span>
        </p>
        <p className="evidence-sub">
          {info.method} · {formatLatency(reply.latency_ms)}
        </p>
      </EvidenceCard>

      {read && (
        <EvidenceCard label="Read as" tone="red">
          <p>{read}</p>
          {reply.rewritten && (
            <p className="evidence-sub">
              Rewritten as <q>{reply.rewritten}</q>
            </p>
          )}
        </EvidenceCard>
      )}

      {path && (
        <EvidenceCard label="Graph path" tone="red">
          <p>{path}</p>
        </EvidenceCard>
      )}

      {reply.route === "recommendation" && reply.seeds.length > 0 && (
        <EvidenceCard label={reply.seeds.length === 1 ? "Seed film" : "Seed films"} tone="amber">
          <ul className="chip-list">
            {reply.seeds.map((s) => (
              <li key={s.qid ?? s.label}>
                {s.qid ? (
                  <Link className="topic-chip" href={filmHref(s.qid)}>
                    {s.label}
                  </Link>
                ) : (
                  <span className="topic-chip">{s.label}</span>
                )}
              </li>
            ))}
          </ul>
        </EvidenceCard>
      )}

      {reply.alternatives.length > 0 && (
        <EvidenceCard label="Same name in the graph" tone="amber">
          <ul className="chip-list">
            {reply.alternatives.map((alt) => {
              const text = `${alt.year ? `${alt.label} (${alt.year})` : alt.label}${alt.kind && alt.kind !== "film" ? `, ${alt.kind}` : ""}`;
              return (
                <li key={alt.qid}>
                  {onAsk ? (
                    <button type="button" className="topic-chip topic-chip-action" onClick={() => onAsk(alt.ask)}>
                      {text}
                    </button>
                  ) : (
                    <Link className="topic-chip topic-chip-action" href={askHref(alt.ask)}>
                      {text}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </EvidenceCard>
      )}

      {entities.length > 0 && (
        <EvidenceCard label={`Entities · ${entities.length}`}>
          <ul className="entity-list">
            {entities.map((c) => (
              <li key={c.qid}>
                <Link href={c.type === "person" ? personHref(c.qid!) : filmHref(c.qid!)}>{c.label}</Link>
                <code>{c.qid}</code>
              </li>
            ))}
          </ul>
        </EvidenceCard>
      )}

      {reply.sparql && (
        <EvidenceCard label="SPARQL query">
          <pre tabIndex={0} role="region" aria-label="SPARQL query">
            {reply.sparql}
          </pre>
        </EvidenceCard>
      )}

      {reply.trace.length > 0 && (
        <EvidenceCard label="Agent log">
          <pre tabIndex={0} role="region" aria-label="Agent log">
            {reply.trace.join("\n")}
          </pre>
        </EvidenceCard>
      )}
    </div>
  );
}
