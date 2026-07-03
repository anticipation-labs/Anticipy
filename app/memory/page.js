import { redirect } from "next/navigation";

// UI_SPEC step 8: /memory is retired. Memory (facts / inferred / open loops / history + the
// forget-me control) now lives folded inside Settings. Anyone landing on the old route is sent
// straight to the memory group there. Redirect, not a delete, so old links never 404.
export default function MemoryPage() {
  redirect("/settings#memory");
}
