"use client";

import { useEffect, useRef, useState } from "react";

/**
 * City autocomplete, ARIA 1.2 combobox.
 *
 * DOM focus never leaves the input — the highlighted option is communicated
 * through `aria-activedescendant`. Moving real focus into the list is the
 * common mistake and it breaks typing entirely for screen-reader users.
 *
 * The load-bearing detail in a one-question-per-screen flow: when the list is
 * open, Enter must select the highlighted city AND call preventDefault, or the
 * same keypress also advances to the next screen and the person never sees
 * what they picked.
 */
export function LocationInput({
  value,
  onChange,
  invalid,
  onEnterWhenClosed,
}: {
  value: string;
  onChange: (v: string) => void;
  invalid?: boolean;
  onEnterWhenClosed: () => void;
}) {
  const [results, setResults] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [focused, setFocused] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);
  const justPicked = useRef(false);

  useEffect(() => {
    if (justPicked.current) {
      justPicked.current = false;
      return;
    }
    const q = value.trim();
    if (q.length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    const ctrl = new AbortController();
    // Debounced: a request per keystroke would be both wasteful and racy.
    const t = window.setTimeout(async () => {
      try {
        const res = await fetch(`/api/places?q=${encodeURIComponent(q)}`, {
          signal: ctrl.signal,
        });
        if (!res.ok) return;
        const d = await res.json();
        setResults(d.results ?? []);
        setOpen((d.results ?? []).length > 0);
        setActive(-1);
      } catch {
        /* aborted or offline — the field still accepts free text */
      }
    }, 140);
    return () => {
      window.clearTimeout(t);
      ctrl.abort();
    };
  }, [value]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const pick = (v: string) => {
    justPicked.current = true;
    onChange(v);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || !results.length) {
      if (e.key === "Enter") {
        e.preventDefault();
        onEnterWhenClosed();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? results.length - 1 : a - 1));
    } else if (e.key === "Enter") {
      // Always preventDefault while the list is open, whether or not an option
      // is highlighted — otherwise this same Enter advances the screen.
      e.preventDefault();
      if (active >= 0) pick(results[active]);
      else setOpen(false);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls="loc-listbox"
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `loc-opt-${active}` : undefined}
        aria-label="Where are you?"
        aria-invalid={invalid}
        autoComplete="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => {
          setFocused(true);
          if (results.length) setOpen(true);
        }}
        onBlur={() => setFocused(false)}
        placeholder="Start typing a city…"
        style={{
          background: "transparent",
          border: "none",
          borderBottom: `1px solid ${invalid ? "var(--danger)" : focused ? "var(--accent)" : "var(--rule)"}`,
          color: "var(--ink)",
          padding: "10px 0 12px",
          fontSize: 18,
          width: "100%",
          outline: "none",
          transition: "border-color 260ms ease",
          fontFamily: "inherit",
          borderRadius: 0,
        }}
      />

      {open && results.length > 0 && (
        <ul
          id="loc-listbox"
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            marginTop: 6,
            background: "#FFFFFF",
            border: "1px solid var(--rule)",
            // A white panel on cream is only a few percent lighter than the
            // page, so without a shadow it reads as part of the form rather
            // than as something floating above it.
            boxShadow: "0 12px 28px rgba(23, 21, 18, 0.10)",
            borderRadius: 10,
            listStyle: "none",
            padding: 5,
            zIndex: 20,
            maxHeight: 260,
            overflowY: "auto",
          }}
        >
          {results.map((r, i) => (
            <li
              key={r}
              id={`loc-opt-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              // mousedown, not click: click fires after blur, which would
              // close the list before the selection registers.
              onMouseDown={(e) => {
                e.preventDefault();
                pick(r);
              }}
              style={{
                padding: "10px 12px",
                borderRadius: 7,
                fontSize: 15,
                cursor: "pointer",
                color: i === active ? "var(--paper)" : "var(--ink)",
                background: i === active ? "var(--accent)" : "transparent",
              }}
            >
              {r}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
