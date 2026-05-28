import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Anticipy AI Wearable Pendant";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#0C0C0C",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "60px",
        }}
      >
        {/* Top accent line */}
        <div
          style={{
            width: 60,
            height: 2,
            background: "#C8A97E",
            marginBottom: 40,
          }}
        />

        {/* Brand name */}
        <div
          style={{
            fontSize: 80,
            color: "#F5F0EB",
            fontFamily: "serif",
            letterSpacing: "-0.02em",
            lineHeight: 1,
          }}
        >
          Anticipy
        </div>

        {/* Tagline */}
        <div
          style={{
            fontSize: 26,
            color: "#C8A97E",
            marginTop: 28,
            letterSpacing: "0.12em",
            textTransform: "uppercase" as const,
          }}
        >
          AI Wearable Pendant
        </div>

        {/* Description */}
        <div
          style={{
            fontSize: 22,
            color: "rgba(245, 240, 235, 0.5)",
            marginTop: 24,
            textAlign: "center" as const,
            maxWidth: 700,
            lineHeight: 1.5,
          }}
        >
          Listens to your life. Handles what needs handling.
        </div>

        {/* Bottom accent line */}
        <div
          style={{
            width: 60,
            height: 2,
            background: "#C8A97E",
            marginTop: 40,
          }}
        />
      </div>
    ),
    { ...size }
  );
}
