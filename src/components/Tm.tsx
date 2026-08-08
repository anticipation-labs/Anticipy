/**
 * The trademark mark, kept deliberately quiet.
 *
 * Typographic choices, all of which exist to stop ™ from shouting:
 *
 *  - `font-size: 0.42em` is relative, so the mark scales with whatever it
 *    sits beside. On an 88px hero it stays proportionate; on 13px footer
 *    text it stays legible rather than collapsing to a smudge.
 *  - `line-height: 0` is the important one. A superscript normally grows the
 *    line box that contains it, which would push a heading's leading open by
 *    a few pixels and subtly break vertical rhythm everywhere it appears.
 *    Zeroing it means the mark cannot affect the layout it sits in.
 *  - `font-weight: 400` and `letter-spacing: 0` are explicit because the
 *    wordmark is often bold and tracked; without these the ™ inherits both
 *    and reads as heavy and detached.
 *  - `opacity: 0.55` softens it to a notice rather than a design element.
 *  - `user-select: none` keeps it out of the clipboard, so copying the brand
 *    name yields "Anticipy" and not "Anticipy™".
 *
 * Scope: brand marks only — headings, the wordmark, and legal footers. Not
 * running body copy, where repetition is both ugly and unnecessary for
 * notice.
 *
 * ™ rather than ®: ™ asserts an unregistered common-law mark and is always
 * available. ® is lawful only after registration actually issues, and using
 * it earlier is itself a misrepresentation. Swap only once registration is
 * granted.
 */
export function Tm({ className }: { className?: string }) {
  return (
    <sup
      className={className}
      aria-label="trademark"
      style={{
        fontSize: "0.42em",
        lineHeight: 0,
        verticalAlign: "super",
        fontWeight: 400,
        letterSpacing: 0,
        opacity: 0.55,
        marginLeft: "0.06em",
        userSelect: "none",
        fontStyle: "normal",
      }}
    >
      ™
    </sup>
  );
}

// The email equivalent lives in src/lib/tm.ts, deliberately kept out of this
// file so the server-side email path never imports a React component. The two
// must stay visually identical — change one, change the other.
