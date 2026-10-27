import type { Metadata } from "next";
import Link from "next/link";
import { Sheet } from "./components/Console";

export const metadata: Metadata = {
  title: "Not in the graph · CineGraph",
};

export default function NotFound() {
  return (
    <Sheet title="404">
      <main id="main" className="notfound">
        <div className="notfound-code" aria-hidden="true">
          404
        </div>
        <h1 className="notfound-title">Not in the graph</h1>
        <p className="notfound-text">That page does not exist. Ask the graph a question instead, or browse the films it knows.</p>
        <div className="notfound-actions">
          <Link href="/" className="ghost-button">
            Ask
          </Link>
          <Link href="/films" className="ghost-button">
            Films
          </Link>
        </div>
      </main>
    </Sheet>
  );
}
