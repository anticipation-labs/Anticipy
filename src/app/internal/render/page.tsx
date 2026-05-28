"use client";

export default function RenderPage() {
  return (
    <div style={{ background: "#0C0C0C", minHeight: "100vh" }}>
      <div style={{ padding: "12px 24px", borderBottom: "1px solid #222" }}>
        <a href="/internal" style={{ color: "#C8A97E", textDecoration: "none", fontSize: 14 }}>← Internal Dashboard</a>
      </div>
      <iframe
        src="/render_product.html"
        style={{ width: "100%", height: "calc(100vh - 48px)", border: "none" }}
        title="Anticipy 3D Product Render"
      />
    </div>
  );
}
