"use client";

import { useState, useMemo } from "react";

type Category = "All" | "Hardware" | "Software" | "Research" | "Orders" | "Testing" | "Links";

interface DocItem {
  title: string;
  description: string;
  category: Exclude<Category, "All">;
  href: string;
  external?: boolean;
  badge?: string;
}

const DOCS: DocItem[] = [
  // Hardware docs — now internal pages
  {
    title: "Firmware Design Doc",
    description: "Complete hardware spec: ESP32-S3, block diagram, pin assignments, state machine, audio pipeline, API contract",
    category: "Hardware",
    href: "/internal/docs/hardware",
    badge: "Full spec",
  },
  {
    title: "PCB Schematic",
    description: "Full pin mapping: U1 (XIAO), MIC1 (INMP441), LED1 (SK6812), U2 (TP4056), all passives, net summary, design notes",
    category: "Hardware",
    href: "/internal/docs/schematic",
    badge: "All components",
  },
  {
    title: "PCB Assembly Guide",
    description: "Step-by-step hand-solder instructions, pre-battery continuity checks, power-on test sequence, QA checklist",
    category: "Hardware",
    href: "/internal/docs/assembly",
    badge: "10 functional tests",
  },
  {
    title: "Packaging Design",
    description: "Box specs (100×70×35mm matte black rigid), branding, quick-start card, accessories, print specs, sustainability",
    category: "Hardware",
    href: "/internal/docs/packaging",
    badge: "$2.97 at 1k units",
  },
  {
    title: "Manufacturing Order Guide",
    description: "JLCPCB, PCBWay, Seeed Fusion, MacroFab, Bittele (Toronto) — 7-day sample checklist with direct order links",
    category: "Hardware",
    href: "/internal/docs/manufacturing",
    badge: "~$37 USD/unit",
  },
  {
    title: "3D Case Design",
    description: "OpenSCAD parametric case, 38×25×11mm. Print at JLCPCB 3D or Shapeways/Xometry for titanium premium.",
    category: "Hardware",
    href: "https://raw.githubusercontent.com/omize10/Anticipy/main/firmware/case/anticipy_pendant.scad",
    external: true,
  },
  {
    title: "3D Product Render",
    description: "Interactive 3D render for presentations and investor decks",
    category: "Hardware",
    href: "/internal/render",
    external: true,
  },
  {
    title: "KiCad Project Files",
    description: "KiCad schematic (.kicad_sch) and project files for PCB layout",
    category: "Hardware",
    href: "https://github.com/omize10/Anticipy/blob/main/firmware/pcb/",
    external: true,
  },
  {
    title: "Firmware Upload (Web Flash)",
    description: "Flash firmware to the ESP32-S3 pendant directly from Chrome — no drivers, no CLI. Web Serial API one-click upload.",
    category: "Hardware",
    href: "/internal/docs/pendant-upload",
    badge: "Web Serial",
  },

  // Research docs — now internal pages
  {
    title: "Bill of Materials",
    description: "All 16 components with verified prices and direct buy links. ~$77 CAD prototype. 72% under $100 CAD budget.",
    category: "Research",
    href: "/internal/docs/bom",
    badge: "$77 CAD",
  },
  {
    title: "Competitive Analysis",
    description: "8 competitors: Humane (dead), Rabbit R1, Meta Ray-Ban, Plaud, Limitless (acquired), Friend (backlash), Bee AI (Amazon). $310B market by 2033.",
    category: "Research",
    href: "/internal/docs/competitive",
    badge: "$310B by 2033",
  },

  // Software
  {
    title: "Engine Architecture",
    description: "Full system overview: Next.js, Supabase, Chrome extension, Browser Use, Gemini + Groq fallback",
    category: "Software",
    href: "https://github.com/omize10/Anticipy/blob/main/CLAUDE.md",
    external: true,
  },
  {
    title: "Action Engine (FastAPI)",
    description: "Python FastAPI server, WebSocket handler, rate limiting, Browser Use integration",
    category: "Software",
    href: "https://github.com/omize10/Anticipy/blob/main/engine/app/main.py",
    external: true,
  },
  {
    title: "Intent Detection Prompt",
    description: "Chain-of-thought reasoning, context-aware importance, task classification",
    category: "Software",
    href: "https://github.com/omize10/Anticipy/blob/main/src/lib/intent-prompt.ts",
    external: true,
  },
  {
    title: "Chrome Extension Agent",
    description: "LLM-powered browser automation in user's Chrome — DOM manipulation, form filling",
    category: "Software",
    href: "https://github.com/omize10/Anticipy/blob/main/extension/agent.js",
    external: true,
  },
  {
    title: "Extension Install Page",
    description: "User-facing extension download and setup at /engine/extension",
    category: "Software",
    href: "https://www.anticipy.ai/engine/extension",
    external: true,
  },

  // Orders
  {
    title: "Order PCBs from JLCPCB",
    description: "2-layer, 40×25mm, black HASL, 5 pcs + SMT assembly. ~$30–50 USD. 3–5 day production + DHL Express.",
    category: "Orders",
    href: "https://cart.jlcpcb.com/quote",
    external: true,
    badge: "~$40 USD/5 pcs",
  },
  {
    title: "Order 3D Cases from JLCPCB",
    description: "PETG or SLA resin, matte black, 10 pieces (5 fronts + 5 backs). ~$15–30 USD.",
    category: "Orders",
    href: "https://jlcpcb.com/3d-printing",
    external: true,
    badge: "~$20 USD/10 pcs",
  },
  {
    title: "Order XIAO ESP32-S3",
    description: "From Seeed Studio — $10.33 CAD each. 5+ recommended. Ships from Shenzhen via DHL.",
    category: "Orders",
    href: "https://www.seeedstudio.com/XIAO-ESP32S3-p-5627.html",
    external: true,
    badge: "$10.33 CAD",
  },
  {
    title: "Order via Bittele (Toronto) — Zero Touch",
    description: "Ship all files + components to Toronto. They assemble, test, flash, ship to West Vancouver. 5–10 days.",
    category: "Orders",
    href: "https://www.7pcb.com/",
    external: true,
    badge: "Full service",
  },
  {
    title: "Order Packaging (Packlane)",
    description: "Custom printed boxes from qty 10. ~$5–8/box. Or: noissue.co (eco), arka.com (mailers).",
    category: "Orders",
    href: "https://www.packlane.com/",
    external: true,
    badge: "$5–8/box",
  },
  {
    title: "ShipBob Fulfillment — Surrey, BC",
    description: "30 min from West Vancouver. Receives from manufacturer, stores inventory, ships to customers.",
    category: "Orders",
    href: "https://www.shipbob.com/",
    external: true,
    badge: "Surrey, BC",
  },

  // Testing
  {
    title: "Browser Test Suite",
    description: "10 real-world browser automation tests. Target: 9/10 pass rate.",
    category: "Testing",
    href: "https://github.com/omize10/Anticipy/blob/main/engine/test_real.py",
    external: true,
  },
  {
    title: "Stress Test Results",
    description: "5/5 complex tasks passing: Wikipedia, flights, forms, checkout, tables",
    category: "Testing",
    href: "#stress-tests",
  },
  {
    title: "Proactive Engine Tests",
    description: "9/9 intents correctly detected from realistic transcripts",
    category: "Testing",
    href: "#proactive-tests",
  },

  // Links
  {
    title: "GitHub — Anticipy",
    description: "Source code repository",
    category: "Links",
    href: "https://github.com/omize10/Anticipy",
    external: true,
  },
  {
    title: "Live Site",
    description: "Production website at anticipy.ai",
    category: "Links",
    href: "https://www.anticipy.ai",
    external: true,
  },
  {
    title: "Action Engine",
    description: "Live engine interface at anticipy.ai/engine",
    category: "Links",
    href: "https://www.anticipy.ai/engine",
    external: true,
  },
  {
    title: "Supabase Dashboard",
    description: "Database, auth, and storage for project ogbxpqkmsdrcuilafycn",
    category: "Links",
    href: "https://supabase.com/dashboard/project/ogbxpqkmsdrcuilafycn",
    external: true,
  },
  {
    title: "Vercel Dashboard",
    description: "Deployments and environment variables",
    category: "Links",
    href: "https://vercel.com/omar-ebrahims-projects-022b18ec/anticipy",
    external: true,
  },
];

const CATEGORY_ICONS: Record<Category, string> = {
  All: "◈",
  Hardware: "⬡",
  Software: "⌘",
  Research: "◎",
  Orders: "◻",
  Testing: "◆",
  Links: "↗",
};

const CATEGORY_COLORS: Record<Exclude<Category, "All">, string> = {
  Hardware: "bg-amber-900/40 text-amber-300 border border-amber-800/50",
  Software: "bg-blue-900/40 text-blue-300 border border-blue-800/50",
  Research: "bg-purple-900/40 text-purple-300 border border-purple-800/50",
  Orders: "bg-green-900/40 text-green-300 border border-green-800/50",
  Testing: "bg-rose-900/40 text-rose-300 border border-rose-800/50",
  Links: "bg-zinc-800/60 text-zinc-300 border border-zinc-700/50",
};

function fuzzyMatch(text: string, query: string): boolean {
  if (!query) return true;
  const t = text.toLowerCase();
  const q = query.toLowerCase();
  if (t.includes(q)) return true;
  let qi = 0;
  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] === q[qi]) qi++;
  }
  return qi === q.length;
}

const CATEGORIES: Category[] = ["All", "Hardware", "Software", "Research", "Orders", "Testing", "Links"];

export default function InternalPage() {
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<Category>("All");

  const filtered = useMemo(() => {
    return DOCS.filter((doc) => {
      const categoryMatch = activeCategory === "All" || doc.category === activeCategory;
      if (!categoryMatch) return false;
      if (!query.trim()) return true;
      return (
        fuzzyMatch(doc.title, query) ||
        fuzzyMatch(doc.description, query) ||
        fuzzyMatch(doc.category, query)
      );
    });
  }, [query, activeCategory]);

  const countByCategory = useMemo(() => {
    const counts: Partial<Record<Category, number>> = { All: DOCS.length };
    for (const doc of DOCS) {
      counts[doc.category] = (counts[doc.category] ?? 0) + 1;
    }
    return counts;
  }, []);

  return (
    <div
      className="min-h-screen"
      style={{ background: "#0C0C0C", color: "#F5F0EB", fontFamily: "var(--font-sans, sans-serif)" }}
    >
      {/* Header */}
      <div className="sticky top-0 z-10 border-b" style={{ background: "#0C0C0C", borderColor: "#252525" }}>
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
            <div className="flex items-center gap-2">
              <span style={{ color: "#C8A97E", fontSize: "1.1rem" }}>◈</span>
              <h1 className="text-lg font-semibold tracking-tight" style={{ color: "#F5F0EB" }}>
                Anticipy Internal
              </h1>
              <span
                className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{ background: "rgba(200,169,126,0.15)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.3)" }}
              >
                Team Only
              </span>
            </div>
            <div className="sm:ml-auto text-xs" style={{ color: "#8A8A8A" }}>
              {filtered.length} of {DOCS.length} documents
            </div>
          </div>

          {/* Search */}
          <div className="relative mb-4">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm pointer-events-none" style={{ color: "#8A8A8A" }}>
              ⌕
            </span>
            <input
              type="text"
              placeholder="Search documents, specs, guides…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none transition-all"
              style={{ background: "#161616", border: "1px solid #252525", color: "#F5F0EB" }}
              onFocus={(e) => { e.currentTarget.style.borderColor = "#C8A97E"; }}
              onBlur={(e) => { e.currentTarget.style.borderColor = "#252525"; }}
            />
            {query && (
              <button onClick={() => setQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-xs" style={{ color: "#8A8A8A" }}>
                ✕
              </button>
            )}
          </div>

          {/* Category tabs */}
          <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
            {CATEGORIES.map((cat) => {
              const isActive = activeCategory === cat;
              const count = countByCategory[cat] ?? 0;
              return (
                <button
                  key={cat}
                  onClick={() => setActiveCategory(cat)}
                  className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
                  style={{
                    background: isActive ? "rgba(200,169,126,0.15)" : "#161616",
                    color: isActive ? "#C8A97E" : "#8A8A8A",
                    border: isActive ? "1px solid rgba(200,169,126,0.4)" : "1px solid #252525",
                  }}
                >
                  <span>{CATEGORY_ICONS[cat]}</span>
                  <span>{cat}</span>
                  <span
                    className="rounded-full px-1.5 py-0.5 text-xs"
                    style={{
                      background: isActive ? "rgba(200,169,126,0.2)" : "#252525",
                      color: isActive ? "#C8A97E" : "#5A5A5A",
                    }}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-4 py-6">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3">
            <span className="text-4xl" style={{ color: "#252525" }}>◎</span>
            <p className="text-sm" style={{ color: "#8A8A8A" }}>No documents match &ldquo;{query}&rdquo;</p>
            <button onClick={() => { setQuery(""); setActiveCategory("All"); }} className="text-xs underline" style={{ color: "#C8A97E" }}>
              Clear filters
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map((doc) => (
              <DocCard key={`${doc.category}-${doc.title}`} doc={doc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function DocCard({ doc }: { doc: DocItem }) {
  const isExternal = doc.external || (doc.href.startsWith("http") && doc.external !== false);
  const isPlaceholder = doc.href.startsWith("#");
  const isInternal = !isExternal && !isPlaceholder;

  return (
    <a
      href={isPlaceholder ? undefined : doc.href}
      target={isExternal ? "_blank" : undefined}
      rel={isExternal ? "noopener noreferrer" : undefined}
      onClick={isPlaceholder ? (e) => e.preventDefault() : undefined}
      className="group flex flex-col gap-2.5 p-4 rounded-xl transition-all"
      style={{
        background: "#161616",
        border: isInternal ? "1px solid rgba(200,169,126,0.2)" : "1px solid #252525",
        cursor: isPlaceholder ? "default" : "pointer",
        textDecoration: "none",
      }}
      onMouseEnter={(e) => {
        if (!isPlaceholder) {
          e.currentTarget.style.borderColor = "rgba(200,169,126,0.45)";
          e.currentTarget.style.background = "#1A1A1A";
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = isInternal ? "rgba(200,169,126,0.2)" : "#252525";
        e.currentTarget.style.background = "#161616";
      }}
    >
      {/* Top row: category badge + indicator */}
      <div className="flex items-center justify-between gap-2">
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${CATEGORY_COLORS[doc.category]}`}>
          {CATEGORY_ICONS[doc.category]} {doc.category}
        </span>
        <div className="flex items-center gap-1.5">
          {doc.badge && (
            <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: "rgba(200,169,126,0.1)", color: "#C8A97E", border: "1px solid rgba(200,169,126,0.2)" }}>
              {doc.badge}
            </span>
          )}
          {isExternal && <span className="text-xs" style={{ color: "#5A5A5A" }}>↗</span>}
          {isInternal && <span className="text-xs" style={{ color: "#C8A97E" }}>→</span>}
          {isPlaceholder && <span className="text-xs" style={{ color: "#5A5A5A" }}>internal</span>}
        </div>
      </div>

      {/* Title */}
      <p className="text-sm font-medium leading-snug" style={{ color: "#F5F0EB" }}>
        {doc.title}
      </p>

      {/* Description */}
      <p className="text-xs leading-relaxed flex-1" style={{ color: "#8A8A8A" }}>
        {doc.description}
      </p>

      {/* Path hint */}
      {isInternal && (
        <p className="text-xs font-mono truncate mt-auto" style={{ color: "#C8A97E", opacity: 0.6 }}>
          {doc.href}
        </p>
      )}
      {isExternal && (
        <p className="text-xs font-mono truncate mt-auto" style={{ color: "#5A5A5A" }}>
          {doc.href.replace("https://", "")}
        </p>
      )}
    </a>
  );
}
