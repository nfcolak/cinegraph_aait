import type { Reply } from "@/lib/api";

// Pure and free of JSX so scripts/check-graph-shape.mts can load it with node --experimental-strip-types.

export const MAX_LEFT = 3;
export const MAX_RIGHT = 4;

export interface GraphShape {
  left: string[]; // subject side: amber nodes
  edge: string; // relation shown in the label pill
  right: string[]; // object side
  more: number; // objects not drawn: the dashed "+N more" node
  reverse: boolean; // arrows point from the right nodes to the left ones (inverse relation)
}

/** The answer as node(s), a relation edge and node(s); null when the reply has nothing to draw. */
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

/** The triple in words, for the SVG's aria-label. */
export function describeShape(shape: GraphShape): string {
  const left = shape.left.join(", ");
  const right = shape.right.join(", ") + (shape.more ? ` and ${shape.more} more` : "");
  return shape.reverse ? `${right} ${shape.edge} ${left}` : `${left} ${shape.edge} ${right}`;
}
