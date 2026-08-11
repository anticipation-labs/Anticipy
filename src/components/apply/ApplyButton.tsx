import Link from "next/link";

/**
 * The one way into the application, used everywhere it appears.
 *
 * A single component because the apply action was previously easy to miss:
 * it sat once, at the very bottom of a long page, styled like the rest of the
 * type. Now it is the only ink-filled shape on a cream page, which makes it
 * the darkest thing on screen and therefore the first thing the eye finds.
 */
export function ApplyButton({
  href,
  label = "Apply for this role",
  size = "lg",
  id,
  location = "final_cta",
  block,
}: {
  href: string;
  label?: string;
  size?: "lg" | "md";
  id: string;
  location?: string;
  block?: boolean;
}) {
  const lg = size === "lg";
  return (
    <Link
      href={href}
      className="apply-btn"
      data-cta-id={id}
      data-cta-location={location}
      data-cta-type="contact"
      data-cta-style="primary"
      style={{
        display: block ? "flex" : "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 10,
        width: block ? "100%" : undefined,
        background: "var(--ink)",
        color: "var(--paper)",
        padding: lg ? "17px 34px" : "13px 22px",
        fontSize: lg ? 16.5 : 14.5,
        fontWeight: 600,
        letterSpacing: "-0.005em",
        borderRadius: 999,
        textDecoration: "none",
        lineHeight: 1,
      }}
    >
      {label}
      <span className="apply-btn-arrow" aria-hidden>
        →
      </span>
    </Link>
  );
}

/** Shared by every page that renders an ApplyButton. */
export const APPLY_BUTTON_CSS = `
  .apply-btn { transition: background 160ms ease, transform 160ms ease; }
  .apply-btn:hover { background: #000; transform: translateY(-1px); }
  .apply-btn:active { transform: translateY(0); }
  .apply-btn:focus-visible { outline: 2px solid var(--accent-ink); outline-offset: 3px; }
  .apply-btn-arrow { transition: transform 160ms ease; }
  .apply-btn:hover .apply-btn-arrow { transform: translateX(3px); }
  @media (prefers-reduced-motion: reduce) {
    .apply-btn, .apply-btn-arrow { transition: none; }
    .apply-btn:hover { transform: none; }
  }
`;
