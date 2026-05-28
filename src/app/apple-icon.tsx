import { ImageResponse } from "next/og";

export const runtime = "edge";
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#0C0C0C",
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: 66,
            height: 150,
            border: "8px solid #F5F0EB",
            borderRadius: 36,
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            paddingBottom: 34,
          }}
        >
          <div
            style={{
              width: 14,
              height: 14,
              background: "#C8A97E",
              borderRadius: 999,
            }}
          />
        </div>
      </div>
    ),
    { ...size }
  );
}
