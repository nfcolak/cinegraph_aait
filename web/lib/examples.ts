export interface QuestionKind {
  title: string; // the kind of question, in sentence case
  blurb: string; // one muted line on what the graph does for it
  questions: string[]; // each one is sent as is when clicked
}

// Shown on the empty ask page. Every question here was asked on the running API (POST /api/chat) on
// 2026-10-28 and came back on the right route with a correct answer.
export const QUESTION_KINDS: QuestionKind[] = [
  {
    title: "Facts about a film",
    blurb: "Director, cast, composer, release date, genre.",
    questions: ["Who directed Inception?", "When was The Godfather released?", "Who composed the music for Jaws?"],
  },
  {
    title: "People and their films",
    blurb: "Filmographies and the roles people played.",
    questions: [
      "Which movies did Christopher Nolan direct?",
      "In which movies did Daniel Radcliffe play?",
      "Who played Jack Sparrow?",
    ],
  },
  {
    title: "Series",
    blurb: "The first, third or last film of a series.",
    questions: ["Who directed the third Harry Potter film?", "What is the first Star Wars movie?"],
  },
  {
    title: "Recommendations",
    blurb: "Films that share genre, people and studio.",
    questions: ["I loved Up, what next?", "Recommend movies like The Matrix"],
  },
  {
    title: "Pictures",
    blurb: "Posters, stills and portraits.",
    questions: ["Show me the poster of Jaws", "What does Keanu Reeves look like?"],
  },
  {
    title: "When the graph has no answer",
    blurb: "A guess from graph embeddings, marked as a guess.",
    questions: ["Who is the composer of Once Upon a Time in Hollywood?"],
  },
  {
    title: "Two questions at once",
    blurb: "Ask about one film twice in one sentence.",
    questions: ["Who directed and wrote Good Will Hunting?"],
  },
];
