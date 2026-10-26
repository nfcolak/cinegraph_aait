import type { Metadata } from "next";
import { SiteHeader } from "../components/SiteHeader";

export const metadata: Metadata = {
  title: "How it works · CineGraph",
  description: "How CineGraph routes a movie question to SPARQL, TransE embeddings, a recommender or an image index.",
};

const REPO = "https://github.com/nfcolak/cinegraph_aait";

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
        The relation (“directed”, “composer”, “released”) maps to a Wikidata property, the film or person is matched by label
        with typo tolerance, and a SPARQL query runs on the graph. Inverse questions (“Which films did Nolan direct?”) query the
        other direction.
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

export default function About() {
  return (
    <div className="app app-doc">
      <SiteHeader />

      <main className="doc" id="main">
        <h1>How CineGraph answers</h1>
        <p className="lede">
          No language model writes these answers. The agent parses a question with rules, picks one of four pipelines and runs it
          on a knowledge graph extracted from Wikidata.
        </p>

        <table className="facts">
          <caption className="sr-only">What the agent works with</caption>
          <tbody>
            <tr>
              <th scope="row">Facts in the graph</th>
              <td>2,413,825</td>
            </tr>
            <tr>
              <th scope="row">Entities with an English label</th>
              <td>129,673</td>
            </tr>
            <tr>
              <th scope="row">Entities with a TransE embedding</th>
              <td>175,660</td>
            </tr>
            <tr>
              <th scope="row">Films with a poster</th>
              <td>12,326</td>
            </tr>
          </tbody>
        </table>

        <h2>The order of the checks</h2>
        <p>The agent tries the pipelines in this order and answers with the first one that matches.</p>
        <ol className="pipeline">
          {ROUTES.map((r) => (
            <li key={r.name}>
              <h3>{r.name}</h3>
              <p>{r.body}</p>
            </li>
          ))}
        </ol>

        <h2>Reading an answer</h2>
        <p>
          The line under each answer names the pipeline and how long it took. Fact and prediction answers also print the triple
          that was queried: subject, Wikidata property and result, with their IDs. “Show query” opens the SPARQL query and the
          agent’s own log for that question.
        </p>

        <h2>Limits</h2>
        <p>
          The graph is a course snapshot of Wikidata. Recent films and some facts are missing, a few entities have no English
          label and appear as Q-IDs, and some labels were altered on purpose for the course. Questions are matched with patterns,
          so unusual phrasing can miss; naming the film exactly works best. Images come from TMDB’s CDN.
        </p>

        <h2>Who built it</h2>
        <p>
          Necati Furkan Çolak and Leyla Khasiyeva, University of Zurich. The agent first ran as a bot on UZH’s Speakeasy chat
          platform; this site puts the same code behind a web interface.
        </p>
        <p className="doc-links">
          <a href={REPO} target="_blank" rel="noreferrer">
            Source on GitHub
          </a>
          <a
            href={`${REPO}/blob/main/Report/Evaluation_Event_Final_Agent_SlateLeapingDeer_colakn_khasiyevl.pdf`}
            target="_blank"
            rel="noreferrer"
          >
            Final report (PDF)
          </a>
        </p>
      </main>
    </div>
  );
}
