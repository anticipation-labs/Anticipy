import { redirect } from "next/navigation";

// The old Call-2 stage folded into the single call + Who-I-Am flow.
export default function OnboardingSixPage() {
  redirect("/onboarding/8");
}
