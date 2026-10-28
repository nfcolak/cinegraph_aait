import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Not in the graph · CineGraph",
};

export default function NotFound() {
  return (
    <main id="main" className="notfound">
      <h1 className="notfound-title">This page is not in the graph.</h1>
      <Link href="/" className="quiet">
        Back to Ask
      </Link>
    </main>
  );
}
