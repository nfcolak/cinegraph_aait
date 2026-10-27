// Feeds graphShape the reply JSON of real API answers (scripts/fixtures/*.json) and checks the drawn graph.
// Run from web/:  node --experimental-strip-types scripts/check-graph-shape.mts
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Reply } from "../lib/api";

type Mod = typeof import("../app/components/graphShape");
type Shape = ReturnType<Mod["graphShape"]>;

const here = dirname(fileURLToPath(import.meta.url));
// A computed URL keeps tsc from asking for allowImportingTsExtensions; node loads the .ts file as is.
const { graphShape, describeShape } = (await import(new URL("../app/components/graphShape.ts", import.meta.url).href)) as Mod;

const fixture = (name: string): Reply => JSON.parse(readFileSync(join(here, "fixtures", `${name}.json`), "utf8"));

interface Case {
  name: string; // fixture file and what it covers
  expect: Shape; // null: nothing is drawn
}

const CASES: Case[] = [
  { name: "factual-single", expect: { left: ["Inception"], edge: "director", right: ["Christopher Nolan"], more: 0, reverse: false } },
  {
    // inverse films-of: 10 titles, 4 drawn, arrows point from the films to the person
    name: "factual-inverse-films-of",
    expect: { left: ["Christopher Nolan"], edge: "director", right: ["The Dark Knight", "Oppenheimer", "The Dark Knight Rises", "Batman Begins"], more: 6, reverse: true },
  },
  { name: "factual-multi-object", expect: { left: ["City of God"], edge: "director", right: ["Fernando Meirelles", "Kátia Lund"], more: 0, reverse: false } },
  { name: "factual-date", expect: { left: ["The Godfather"], edge: "publication date", right: ["1972-03-15"], more: 0, reverse: false } },
  { name: "factual-no-answer", expect: null },
  { name: "prediction-guess", expect: null },
  {
    // 6 recommended films: 4 drawn and "+2 more"; seeds on the left, arrows from seeds to films
    name: "recommendation-seeds",
    expect: { left: ["The Matrix", "Blade Runner"], edge: "similar to", right: ["The Matrix Reloaded", "The Matrix Revolutions", "Blade Runner 2049", "The Invasion"], more: 2, reverse: false },
  },
  { name: "recommendation-one-seed", expect: { left: ["Up"], edge: "similar to", right: ["Soul", "Cars 3", "Toy Story 4", "Coco"], more: 2, reverse: false } },
  { name: "recommendation-genre", expect: null },
  { name: "recommendation-title-not-found", expect: null },
  { name: "multimedia-portrait", expect: { left: ["Halle Berry"], edge: "image", right: ["profile"], more: 0, reverse: false } },
  { name: "multimedia-poster", expect: { left: ["Interstellar"], edge: "image", right: ["poster"], more: 0, reverse: false } },
];

let passed = 0;
let total = 0;

function report(name: string, problems: string[]) {
  total++;
  if (problems.length === 0) {
    passed++;
    console.log(`PASS ${name}`);
  } else {
    console.log(`FAIL ${name}: ${problems.join("; ")}`);
  }
}

for (const c of CASES) {
  const reply = fixture(c.name);
  const got = graphShape(reply);
  const problems: string[] = [];

  if (JSON.stringify(got) !== JSON.stringify(c.expect)) {
    problems.push(`expected ${JSON.stringify(c.expect)}, got ${JSON.stringify(got)}`);
  }
  if (got) {
    // limits of design.md section 4 and a readable aria-label, whatever the answer
    if (got.left.length < 1 || got.left.length > 3) problems.push(`${got.left.length} left nodes (1 to 3 allowed)`);
    if (got.right.length < 1 || got.right.length > 4) problems.push(`${got.right.length} right nodes (1 to 4 allowed)`);
    if (got.more < 0) problems.push(`negative +more (${got.more})`);
    if ([...got.left, ...got.right, got.edge].some((t) => !t.trim())) problems.push("empty label");
    const words = describeShape(got);
    if (!words.includes(got.edge) || !got.left.every((t) => words.includes(t))) problems.push(`aria-label misses a node: ${words}`);
  }
  report(c.name, problems);
}

// The reply must not be changed by drawing it.
{
  const reply = fixture("recommendation-seeds");
  const before = JSON.stringify(reply);
  graphShape(reply);
  report("graphShape leaves the reply untouched", JSON.stringify(reply) === before ? [] : ["reply was mutated"]);
}

console.log(`${passed}/${total} passed`);
process.exit(passed === total ? 0 : 1);
