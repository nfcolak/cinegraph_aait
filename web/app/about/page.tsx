import type { ReactNode } from "react";
import type { Metadata } from "next";
import { ROUTE_INFO, type Route } from "@/lib/api";
import { REPO } from "@/lib/site";
import { Sheet } from "../components/Shell";

export const metadata: Metadata = {
  title: "How it works · CineGraph",
  description: "How CineGraph routes a movie question to SPARQL, TransE embeddings, a recommender or an image index.",
};

// in the order the agent tries them
const ROUTES: { route: Route; name: string; body: ReactNode }[] = [
  {
    route: "multimedia",
    name: "Picture",
    body: (
      <>
        Phrases such as “show me”, “poster of” or “scene from” send the question here. The named person or film is resolved to
        a Wikidata entity, then to its IMDb ID (<code>P345</code>), and looked up in an index of 347k posters, portraits and
        stills.
      </>
    ),
  },
  {
    route: "recommendation",
    name: "Recommendation",
    body: (
      <>
        Seed films are split out of the question (“The Matrix and Blade Runner”, “something like Chicken Little”) and linked
        to the graph with typo tolerance; a series or character such as “Star Wars” stands for its films. Every candidate
        film is scored by the facets it shares with them: genre (5), director (3.5), screenwriter, studio and cast (2.5),
        composer and producer (1.2), down to country and language (0.4), normalised over everything the seed has, so one
        shared name alone does not decide. That score is blended 65/35 with embedding similarity. Requests that are really
        lists, such as “films with Meryl Streep”, become a graph query instead.
      </>
    ),
  },
  {
    route: "factual",
    name: "Stored fact",
    body: (
      <>
        A rule-based parser reads the relation (“directed”, “scored”, “who played in”), the subject and any year hint, and splits
        questions with two parts. The subject is linked to a graph entity by label with typo tolerance; characters and series
        are answered through the films linked to them. A SPARQL query then runs on the graph, in the inverse direction for
        questions such as “Which films did Nolan direct?”.
      </>
    ),
  },
  {
    route: "prediction",
    name: "Prediction",
    body: (
      <>
        If the graph holds no value, the agent falls back to TransE embeddings with 256 dimensions: it adds the relation vector
        to the film vector and returns the nearest entity. These answers are marked as guesses because they are often wrong.
      </>
    ),
  },
];

const STEPS = [
  { name: "Question", text: "Typed in the box, up to 300 characters." },
  { name: "Intent", text: "Rules read the relation, the subject and any year hint." },
  { name: "Entity link", text: "The named film or person is matched to a Wikidata entity, with typo tolerance." },
];

const FACTS = [
  { label: "Facts in the graph", value: "2,413,825" },
  { label: "Entities with an English label", value: "129,673" },
  { label: "Entities with a TransE embedding", value: "175,660" },
  { label: "Films with a poster", value: "12,326" },
];

export default function About() {
  return (
    <Sheet>
      <main id="main" className="about">
        <header className="about-head">
          <h1>How CineGraph answers</h1>
          <p className="about-lede">
            No language model writes these answers. The agent parses a question with rules, picks one of four pipelines and runs it
            on a knowledge graph extracted from Wikidata.
          </p>
        </header>

        <dl className="kv about-facts" aria-label="The graph in numbers">
          {FACTS.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>

        <dl className="kv about-facts" aria-label="About the project">
          <div>
            <dt>Type</dt>
            <dd>Conversational agent · UZH AI Core project</dd>
          </div>
          <div>
            <dt>Stack</dt>
            <dd>Python / RDFLib / SPARQL / TransE</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>
              <a href={REPO} target="_blank" rel="noreferrer">
                GitHub ↗
              </a>
            </dd>
          </div>
        </dl>

        <section className="about-section" id="overview">
          <h2>Overview</h2>
          <p>
            Every question takes the same road: it is read, its subject is linked to the graph, and the first pipeline that
            fits answers it.
          </p>
          <ol className="about-steps" aria-label="From a question to an answer">
            {STEPS.map((s) => (
              <li key={s.name}>
                <strong>{s.name}.</strong> {s.text}
              </li>
            ))}
            <li>
              <strong>First match wins.</strong> The pipelines are tried in this order:
              <ol className="about-sub" aria-label="Pipelines in the order they are tried">
                {ROUTES.map((r) => (
                  <li key={r.route}>
                    {r.name}, {ROUTE_INFO[r.route].method}
                  </li>
                ))}
              </ol>
            </li>
            <li>
              <strong>Answer.</strong> The text, with its path, query and log as evidence.
            </li>
          </ol>
        </section>

        <section className="about-section" id="pipelines">
          <h2>The order of the checks</h2>
          <p>The agent tries the pipelines in this order and answers with the first one that matches.</p>
          <ol className="about-steps">
            {ROUTES.map((r) => (
              <li key={r.name}>
                <strong>{r.name}.</strong> {r.body}
              </li>
            ))}
          </ol>
        </section>

        <section className="about-section" id="reading">
          <h2>Reading an answer</h2>
          <p>
            Under each answer, “How it was found” opens the evidence inline, and the time the answer took sits beside it. “Read
            as” says how the question was understood, “Path” prints the triple that was queried (subject, Wikidata property and
            result), and “Entities” links the films and people it found. The disclosure ends with the SPARQL query and the
            agent’s own log for that question.
          </p>
        </section>

        <section className="about-section" id="limits">
          <h2>Limits</h2>
          <p>
            The graph is a course snapshot of Wikidata. Recent films and some facts are missing, a few entities have no English
            label and appear as Q-IDs, and some labels were altered on purpose for the course. Questions are matched with
            patterns, so unusual phrasing can miss; naming the film exactly works best. Images come from TMDB’s CDN.
          </p>
        </section>

        <section className="about-section" id="credits">
          <h2>Who built it</h2>
          <p>
            Necati Furkan Çolak and Leyla Khasiyeva, University of Zurich. The agent first ran as a bot on UZH’s Speakeasy chat
            platform; this site puts the same code behind a web interface.
          </p>
          <p className="about-links">
            <a href={REPO} target="_blank" rel="noreferrer">
              Source on GitHub ↗
            </a>
            <a
              href={`${REPO}/blob/main/Report/Evaluation_Event_Final_Agent_SlateLeapingDeer_colakn_khasiyevl.pdf`}
              target="_blank"
              rel="noreferrer"
            >
              Final report (PDF) ↗
            </a>
          </p>
        </section>
      </main>
    </Sheet>
  );
}
