import { Suspense } from "react";
import { FilmView } from "../../components/FilmView";

export default function FilmPage() {
  return (
    <Suspense>
      <FilmView />
    </Suspense>
  );
}
