import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Newsreader, Schibsted_Grotesk } from "next/font/google";
import "./globals.css";

// Newsreader carries questions, answers and titles (film-criticism register, as on Criterion and Letterboxd);
// Schibsted Grotesk carries the interface; JetBrains Mono only Wikidata IDs, SPARQL and the agent log.
const serif = Newsreader({
  variable: "--font-serif",
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
});

const sans = Schibsted_Grotesk({
  variable: "--font-sans",
  subsets: ["latin"],
});

const mono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400"],
});

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
  themeColor: "#fbfbfa",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable} ${mono.variable}`}>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
