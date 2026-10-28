import type { Reply } from "@/lib/api";

// Pure and free of JSX so scripts/check-graph-shape.mts can load it with node --experimental-strip-types.
// The answer's path through the graph; the disclosure shows it as one text line (pathText).

export const MAX_LEFT = 3;
export const MAX_RIGHT = 4;

export interface GraphShape {
  left: string[]; // subject side
  edge: string; // relation
  right: string[]; // object side
  more: number; // objects beyond right
  reverse: boolean; // the arrows point from the right items to the left ones (inverse relation)
}

/** The answer as item(s), a relation and item(s); null when the reply has no path to show. */
export function graphShape(reply: Reply): GraphShape | null {
  if (reply.route === "recommendation" && reply.seeds.length) {
    const films = reply.cards.filter((c) => c.type === "film").map((c) => c.label);
    if (!films.length) return null;
    return {
      left: reply.seeds.map((s) => s.label).slice(0, MAX_LEFT),
      edge: "similar to",
      right: films.slice(0, MAX_RIGHT),
      more: Math.max(0, films.length - MAX_RIGHT),
      reverse: false,
    };
  }
  if (reply.route === "multimedia") {
    if (!reply.image) return null;
    return { left: [reply.image.label ?? "entity"], edge: "image", right: [reply.image.kind], more: 0, reverse: false };
  }
  if (!reply.ok || !reply.relation || !reply.subject?.label) return null;
  let objects = reply.objects.length ? reply.objects : reply.cards.map((c) => c.label);
  if (!objects.length) {
    // a date answer has no object entity: draw the date itself
    const date = reply.answer.match(/\d{4}-\d{2}-\d{2}/)?.[0];
    if (!date) return null;
    objects = [date];
  }
  const shown = Math.min(MAX_RIGHT, objects.length);
  const total = Math.max(reply.count, objects.length);
  return { left: [reply.subject.label], edge: reply.relation, right: objects.slice(0, shown), more: Math.max(0, total - shown), reverse: reply.inverse };
}

/** The triple in words. */
export function describeShape(shape: GraphShape): string {
  const left = shape.left.join(", ");
  const right = shape.right.join(", ") + (shape.more ? ` and ${shape.more} more` : "");
  return shape.reverse ? `${right} ${shape.edge} ${left}` : `${left} ${shape.edge} ${right}`;
}

export const PATH_SHOWN = 3;

function listText(items: string[], extra: number): string {
  const shown = items.slice(0, PATH_SHOWN);
  const rest = items.length + extra - shown.length;
  return shown.join(", ") + (rest > 0 ? ` and ${rest} more` : "");
}

/** The path as one text line: "Inception → director → Christopher Nolan"; a list shows its first 3 items, then "and N more". */
export function pathText(shape: GraphShape): string {
  const left = listText(shape.left, 0);
  const right = listText(shape.right, shape.more);
  return shape.reverse ? `${right} → ${shape.edge} → ${left}` : `${left} → ${shape.edge} → ${right}`;
}
