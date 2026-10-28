import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Shell } from "./components/Shell";
import "./styles/tokens.css";
import "./styles/shell.css";
import "./styles/components.css";
import "./styles/ask.css";
import "./styles/catalog.css";
import "./styles/detail.css";

// Quiet UI: Geist for reading, Geist Mono for example chips, the query, the log and QIDs.

const sans = Geist({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-geist-sans", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-geist-mono", display: "swap" });

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
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f4f1" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0c0e" },
  ],
  colorScheme: "light dark",
};

// Runs before first paint: the saved theme, else the system scheme.
const THEME_SCRIPT = `try{var t=localStorage.getItem("cg-theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="light"}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
