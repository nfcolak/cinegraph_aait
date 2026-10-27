import type { Metadata, Viewport } from "next";
import "./globals.css";

// Editorial system after the portfolio's Jesper gallery: black canvas, white reading sheet,
// Helvetica Neue throughout; the film imagery carries all the colour.

export const metadata: Metadata = {
  title: "CineGraph · Ask the film graph",
  description:
    "A movie question-answering agent built on a 2.4M-fact Wikidata knowledge graph: SPARQL answers, TransE predictions, recommendations and posters.",
  openGraph: {
    title: "CineGraph · Ask the film graph",
    description: "Ask a Wikidata film knowledge graph who made what, get recommendations, or see a poster.",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#000000",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
