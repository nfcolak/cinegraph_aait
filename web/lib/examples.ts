import type { Route } from "./api";

export interface ExampleGroup {
  route: Route;
  title: string;
  blurb: string;
  questions: string[];
}

// Every question here was asked on the running API (POST /api/chat) on 2026-10-27 and came back on the route
// of its group with a correct answer. Dropped that day: "Who is the composer of Titanic?" (the graph holds only
// the 1953 film), "Who directed Galaxy Quest?" and "Who is the composer of Pulp Fiction?" (no prediction
// offered), "What is the genre of Central Station?" (no match) and the "A.I. Artificial Intelligence" request
// (title not found). A prediction here is the graph saying a fact is missing plus a flagged embedding guess.
export const EXAMPLES: ExampleGroup[] = [
  {
    route: "factual",
    title: "Facts",
    blurb: "Looked up directly in the graph.",
    questions: [
      "Who directed Inception?",
      "Which movies did Christopher Nolan direct?",
      "Who is the composer of Jaws?",
      "When was The Godfather released?",
    ],
  },
  {
    route: "prediction",
    title: "Predictions",
    blurb: "When the graph has no answer, embeddings guess one.",
    questions: [
      "Who is the composer of Once Upon a Time in Hollywood?",
      "Who is the composer of The Doors?",
      "Who is the composer of American Sniper?",
    ],
  },
  {
    route: "recommendation",
    title: "Recommendations",
    blurb: "Films that share genre, people and studio.",
    questions: [
      "Recommend movies like The Matrix and Blade Runner",
      "I loved Up, what next?",
      "Recommend me some horror movies",
    ],
  },
  {
    route: "multimedia",
    title: "Pictures",
    blurb: "Posters, portraits and scenes.",
    questions: [
      "Show me a picture of Halle Berry",
      "Show me the poster of Interstellar",
      "Show me Brad Pitt in a scene from Fight Club",
    ],
  },
];
