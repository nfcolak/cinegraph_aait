import { Suspense } from "react";
import { PersonView } from "../../components/PersonView";

export default function PersonPage() {
  return (
    <Suspense>
      <PersonView />
    </Suspense>
  );
}
