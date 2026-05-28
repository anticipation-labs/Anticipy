"use client";

export default function OrderPage() {
  return (
    <div style={{ background: "#0C0C0C", minHeight: "100vh" }}>
      <div style={{ padding: "12px 24px", borderBottom: "1px solid #222" }}>
        <a href="/internal" style={{ color: "#C8A97E", textDecoration: "none", fontSize: 14 }}>← Internal Dashboard</a>
      </div>
      <iframe
        src="/order.html"
        style={{ width: "100%", height: "calc(100vh - 48px)", border: "none" }}
        title="Component Order Sheet"
      />
    </div>
  );
}
