/**
 * A photo slot.
 *
 * Deliberately renders an empty box with the shot description in it rather
 * than a stock or generated stand-in. Every one of these shows something real
 * — the actual bench, the actual rejected samples, the actual filming setup —
 * so a plausible-looking substitute would be a lie about the company, and the
 * kind of lie a hardware candidate would spot immediately.
 *
 * Swapping one in later is a one-line change: pass `src`, and the caption
 * becomes the alt text.
 */
export function Photo({
  ratio = "16:9",
  caption,
  src,
  priority,
}: {
  ratio?: "16:9" | "4:3";
  /** The shot description. Doubles as alt text once a real photo lands. */
  caption: string;
  src?: string;
  priority?: boolean;
}) {
  const aspect = ratio === "4:3" ? "4 / 3" : "16 / 9";

  return (
    <figure
      style={{
        margin: "36px 0",
        width: "100%",
        aspectRatio: aspect,
        borderRadius: 10,
        overflow: "hidden",
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={caption}
          loading={priority ? "eager" : "lazy"}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : (
        <figcaption
          style={{
            fontSize: 12.5,
            lineHeight: 1.7,
            color: "#5A5A5A",
            textAlign: "center",
            maxWidth: 460,
          }}
        >
          <span
            className="tracking-wide-label"
            style={{
              display: "block",
              fontSize: 9.5,
              textTransform: "uppercase",
              color: "#3E3E3E",
              marginBottom: 8,
            }}
          >
            Photo
          </span>
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
