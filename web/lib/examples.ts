import type { Route } from "./api";

export interface ExampleGroup {
  route: Route;
  title: string;
  blurb: string;
  questions: string[];
}

// Every question here was answered by the running agent before it was listed.
export const EXAMPLES: ExampleGroup[] = [
  {
    route: "factual",
    title: "Facts",
    blurb: "Looked up directly in the graph.",
    questions: [
      "Who directed Inception?",
      "Which movies did Christopher Nolan direct?",
      "Who is the composer of Titanic?",
      "When was The Godfather released?",
    ],
  },
  {
    route: "prediction",
    title: "Predictions",
    blurb: "When the graph has no answer, embeddings guess one.",
    questions: [
      "Who directed Galaxy Quest?",
      "What is the genre of Central Station?",
      "Who is the composer of Pulp Fiction?",
    ],
  },
  {
    route: "recommendation",
    title: "Recommendations",
    blurb: "Films that share genre, people and studio.",
    questions: [
      "Recommend movies like The Matrix and Blade Runner",
      "Given that I like A.I. Artificial Intelligence, can you recommend some movies?",
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
