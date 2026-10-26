import type { Metadata } from "next";
import { FilmsBrowser } from "../components/FilmsBrowser";

export const metadata: Metadata = {
  title: "Films · CineGraph",
  description: "Browse all 12,237 films in the CineGraph knowledge graph, with posters, stills, cast and crew.",
};

export default function FilmsPage() {
  return <FilmsBrowser />;
}
