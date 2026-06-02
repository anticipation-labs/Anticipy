export default function Home() {
  return (
    <main
      style={{
        textAlign: "center",
        padding: "2rem",
        maxWidth: 640,
      }}
    >
      <p
        style={{
          letterSpacing: "0.35em",
          textTransform: "uppercase",
          fontSize: "0.75rem",
          color: "#c9a227",
          margin: 0,
        }}
      >
        Anticipy · Executor
      </p>
      <h1
        style={{
          fontFamily: "'DM Serif Display', Georgia, serif",
          fontSize: "clamp(2.75rem, 8vw, 5rem)",
          lineHeight: 1.05,
          margin: "1.25rem 0 0.75rem",
          fontWeight: 400,
        }}
      >
        Vibe your life.
      </h1>
      <p style={{ color: "#a8a194", fontSize: "1rem", margin: 0 }}>
        Working environment is live and wired up. ✦
      </p>
      <div
        style={{
          marginTop: "2.5rem",
          fontSize: "0.8rem",
          color: "#6f6a60",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}
      >
        anticipy-executor-working · deployed on Vercel
      </div>
    </main>
  );
}
