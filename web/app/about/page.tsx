import type { Metadata } from "next";
import { Reader, REPO, Sheet } from "../components/SiteHeader";

export const metadata: Metadata = {
  title: "How it works · CineGraph",
  description: "How CineGraph routes a movie question to SPARQL, TransE embeddings, a recommender or an image index.",
};

const ROUTES = [
  {
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
    name: "Recommendation",
    body: (
      <>
        Seed films are split out of the question (“The Matrix and Blade Runner”). Every candidate film is scored by the people
        and attributes it shares with them, weighted from costume designer (6), composer (5), genre and studio (4) and director
        (3) down to cast (0.8), and that score is blended 65/35 with embedding similarity. Requests that are really lists, such
        as “films with Meryl Streep”, become a graph query instead.
      </>
    ),
  },
  {
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

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "pipelines", label: "Pipelines" },
  { id: "reading", label: "Reading an answer" },
  { id: "limits", label: "Limits" },
  { id: "credits", label: "Who built it" },
];

export default function About() {
  return (
    <Sheet title="How it works">
      <Reader
        back={{ href: "/", label: "Gallery" }}
        title="How CineGraph answers"
        meta={[
          { label: "Type", value: "Conversational agent · UZH AI Core project" },
          { label: "Stack", value: "Python / RDFLib / SPARQL / TransE" },
          {
            label: "Source",
            value: (
              <a href={REPO} target="_blank" rel="noreferrer">
                GitHub ↗
              </a>
            ),
          },
        ]}
        sections={SECTIONS}
      >
        <section className="block" id="overview">
          <p className="lede lede-large">
            No language model writes these answers. The agent parses a question with rules, picks one of four pipelines and runs it
            on a knowledge graph extracted from Wikidata.
          </p>
          <dl className="figures">
            <div>
              <dt>Facts in the graph</dt>
              <dd>2,413,825</dd>
            </div>
            <div>
              <dt>Entities with an English label</dt>
              <dd>129,673</dd>
            </div>
            <div>
              <dt>Entities with a TransE embedding</dt>
              <dd>175,660</dd>
            </div>
            <div>
              <dt>Films with a poster</dt>
              <dd>12,326</dd>
            </div>
          </dl>
        </section>

        <section className="block" id="pipelines">
          <h2 className="block-title">The order of the checks</h2>
          <p className="prose">The agent tries the pipelines in this order and answers with the first one that matches.</p>
          <ol className="pipeline">
            {ROUTES.map((r, i) => (
              <li key={r.name}>
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
            Under each answer, “Read as” says how the question was understood, “Path” prints the triple that was queried
            (subject, Wikidata property and result, with their IDs) and “Answered by” names the pipeline and how long it took.
            “Show query” opens the SPARQL query and the agent’s own log for that question.
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
      </Reader>
    </Sheet>
  );
}
