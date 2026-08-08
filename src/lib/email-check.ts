/**
 * Email plausibility checks for the application form.
 *
 * An honest framing, because it shapes the design: you cannot prove an
 * address is real without sending something to it. Every check short of that
 * is probabilistic, and the one people reach for first — an MX lookup — is
 * close to useless for the failure that actually matters here. `gmial.com`
 * has a live MX record. `hotmial.com` resolves to an active typosquat
 * catch-all. Both pass an MX check, and in both cases the candidate is gone.
 *
 * So the effort goes where the wins are:
 *   1. CATCH THE TYPO before they submit. One tap to fix. This is where
 *      nearly all the real-world benefit lives.
 *   2. Soft-warn on a domain that cannot receive mail at all, and only
 *      hard-block on a null MX, which is an explicit "this domain accepts no
 *      mail" declaration.
 *   3. Get actual proof for free and after the fact: the applicant receives a
 *      confirmation email anyway, so a hard bounce is ground truth at zero
 *      friction. No magic-link gate — double opt-in costs 20-30% of
 *      submissions, which on a funnel this small is unaffordable.
 */

/** Domains people mistype, and what they meant. */
const COMMON_DOMAINS = [
  "gmail.com",
  "googlemail.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "yahoo.com",
  "icloud.com",
  "me.com",
  "proton.me",
  "protonmail.com",
  "aol.com",
  "gmx.com",
  "fastmail.com",
  "hey.com",
  "zoho.com",
];

/** Levenshtein, capped — we only care about "one or two slips away". */
function distance(a: string, b: string, max = 2): number {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  const cur = new Array<number>(b.length + 1);
  for (let i = 1; i <= a.length; i++) {
    cur[0] = i;
    let best = cur[0];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(
        prev[j] + 1,
        cur[j - 1] + 1,
        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
      best = Math.min(best, cur[j]);
    }
    if (best > max) return max + 1;
    prev.splice(0, prev.length, ...cur);
  }
  return prev[b.length];
}

/**
 * Returns a corrected address if the domain looks like a near-miss of a
 * common one, otherwise null. Deliberately conservative: a wrong suggestion
 * on someone's real corporate domain is more annoying than no suggestion.
 */
export function suggestEmail(email: string): string | null {
  const at = email.lastIndexOf("@");
  if (at < 1) return null;
  const local = email.slice(0, at);
  const domain = email.slice(at + 1).toLowerCase();
  if (!domain || COMMON_DOMAINS.includes(domain)) return null;

  // Only consider domains of a similar shape; never "fix" a company address.
  for (const candidate of COMMON_DOMAINS) {
    const d = distance(domain, candidate);
    if (d > 0 && d <= 2) {
      // A single missing dot ("gmailcom") is a slip; a genuinely different
      // short domain is not. Require some length so "abc.io" is left alone.
      if (domain.length >= candidate.length - 3) {
        return `${local}@${candidate}`;
      }
    }
  }
  return null;
}

/** Obvious throwaway providers. Not exhaustive — lists go stale fast. */
const DISPOSABLE = new Set([
  "mailinator.com",
  "guerrillamail.com",
  "10minutemail.com",
  "tempmail.com",
  "temp-mail.org",
  "trashmail.com",
  "yopmail.com",
  "sharklasers.com",
  "getnada.com",
  "dispostable.com",
  "maildrop.cc",
  "fakeinbox.com",
  "throwawaymail.com",
]);

export function isDisposable(email: string): boolean {
  const domain = email.slice(email.lastIndexOf("@") + 1).toLowerCase();
  return DISPOSABLE.has(domain);
}
