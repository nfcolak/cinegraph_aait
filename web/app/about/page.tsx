import type { CSSProperties, ReactNode } from "react";
import type { Metadata } from "next";
import { ROUTE_INFO, type Route } from "@/lib/api";
import { Page, SectionTabs, StatBox } from "../components/PageLayout";
import { REPO } from "@/lib/site";
import { Sheet } from "../components/Console";

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
        to the film vector and returns the nearest entity. These answers are labelled as predictions because they are often
        wrong.
      </>
    ),
  },
];

const STEPS = [
  { name: "Question", text: "Typed in the box, up to 300 characters." },
  { name: "Intent", text: "Rules read the relation, the subject and any year hint." },
  { name: "Entity link", text: "The named film or person is matched to a Wikidata entity, with typo tolerance." },
];

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "pipelines", label: "Pipelines" },
  { id: "reading", label: "Reading an answer" },
  { id: "limits", label: "Limits" },
  { id: "credits", label: "Who built it" },
];

const routeColour = (r: Route) => ({ "--route": `var(--route-${r})` }) as CSSProperties;

/** The answer pipeline drawn as step cards joined by red connectors; it stacks vertically on narrow screens. */
function Flow() {
  return (
    <ol className="flow" aria-label="From a question to an answer">
      {STEPS.map((s, i) => (
        <li key={s.name} className="flow-step">
          <span className="flow-n">{String(i + 1).padStart(2, "0")}</span>
          <h3>{s.name}</h3>
          <p>{s.text}</p>
        </li>
      ))}
      <li className="flow-fan">
        <span className="flow-n">04 · first match wins</span>
        <ol className="flow-routes" aria-label="Pipelines in the order they are tried">
          {ROUTES.map((r, i) => (
            <li key={r.route} className="flow-route" style={routeColour(r.route)}>
              <div className="flow-card">
                <span className="flow-route-n">{i + 1}</span>
                <div>
                  <h3>{r.name}</h3>
                  <p>{ROUTE_INFO[r.route].method}</p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </li>
      <li className="flow-step flow-end">
        <span className="flow-n">05</span>
        <h3>Answer</h3>
        <p>The text, with its path, query and log as evidence.</p>
      </li>
    </ol>
  );
}

export default function About() {
  return (
    <Sheet title="How it works">
      <Page>
        <header className="about-intro">
          <p className="page-kicker">Wikidata film graph · 2.4M facts</p>
          <h1 className="about-title">How CineGraph answers</h1>
          <p className="lede lede-large">
            No language model writes these answers. The agent parses a question with rules, picks one of four pipelines and runs it
            on a knowledge graph extracted from Wikidata.
          </p>
          <StatBox
            label="The graph in numbers"
            items={[
              { label: "Facts in the graph", value: "2,413,825" },
              { label: "Entities with an English label", value: "129,673" },
              { label: "Entities with a TransE embedding", value: "175,660" },
              { label: "Films with a poster", value: "12,326" },
            ]}
          />
          <dl className="kv kv-inline">
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
        </header>

        <SectionTabs sections={SECTIONS} label="On this page" />

        <div className="about-body">
          <section className="block" id="overview">
            <h2 className="block-title">Overview</h2>
            <p className="prose">
              Every question takes the same road: it is read, its subject is linked to the graph, and the first pipeline that
              fits answers it.
            </p>
            <Flow />
          </section>

          <section className="block" id="pipelines">
            <h2 className="block-title">The order of the checks</h2>
            <p className="prose">The agent tries the pipelines in this order and answers with the first one that matches.</p>
            <ol className="pipeline">
              {ROUTES.map((r, i) => (
                <li key={r.name} style={routeColour(r.route)}>
                  <span className="pipeline-n">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <h3>{r.name}</h3>
                    <p>{r.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className="block" id="reading">
            <h2 className="block-title">Reading an answer</h2>
            <p className="prose">
              Under each answer, the “evidence · N” button opens the evidence panel (a bottom sheet on phones). It draws the
              answer as a small graph, “Answered by” names the pipeline and how long it took, “Read as” says how the question was
              understood and “Graph path” prints the triple that was queried (subject, Wikidata property and result, with their
              IDs). The panel ends with the SPARQL query and the agent’s own log for that question.
            </p>
          </section>

          <section className="block" id="limits">
            <h2 className="block-title">Limits</h2>
            <p className="prose">
              The graph is a course snapshot of Wikidata. Recent films and some facts are missing, a few entities have no English
              label and appear as Q-IDs, and some labels were altered on purpose for the course. Questions are matched with
              patterns, so unusual phrasing can miss; naming the film exactly works best. Images come from TMDB’s CDN.
            </p>
          </section>

          <section className="block" id="credits">
            <h2 className="block-title">Who built it</h2>
            <p className="prose">
              Necati Furkan Çolak and Leyla Khasiyeva, University of Zurich. The agent first ran as a bot on UZH’s Speakeasy chat
              platform; this site puts the same code behind a web interface.
            </p>
            <p className="link-row">
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
        </div>
      </Page>
    </Sheet>
  );
}
