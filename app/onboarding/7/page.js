import { redirect } from "next/navigation";

// The old Layer-3 stage folded into the deep read on /onboarding/5.
export default function OnboardingSevenPage() {
  redirect("/onboarding/8");
}
