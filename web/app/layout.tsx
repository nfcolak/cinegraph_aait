import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./styles/tokens.css";
import "./styles/shell.css";
import "./styles/components.css";
import "./styles/ask.css";
import "./styles/pages.css";

// Cinema console: warm dark panels, IBM Plex Sans for reading, IBM Plex Mono for labels
// and data, projector amber as the accent and screen red for evidence.

const sans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-plex-sans", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-mono", display: "swap" });

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
  themeColor: "#0e0c0a",
  colorScheme: "dark",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
