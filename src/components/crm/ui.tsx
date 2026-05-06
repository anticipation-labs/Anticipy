/**
 * Tiny CRM UI primitives. No component library: just typed wrappers around
 * Tailwind-friendly inline styles using brand tokens. Keeps the CRM visually
 * coherent without dragging in shadcn or another framework.
 */
"use client";

import { CSSProperties, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const baseButton: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 8,
  borderRadius: 10,
  fontSize: 14,
  fontWeight: 500,
  cursor: "pointer",
  border: "1px solid transparent",
  padding: "10px 16px",
  textDecoration: "none",
  whiteSpace: "nowrap",
  fontFamily: "var(--font-jakarta), sans-serif",
};

export function Button({
  variant = "primary",
  size = "md",
  type = "button",
  disabled,
  onClick,
  children,
  style,
  title,
}: {
  variant?: Variant;
  size?: Size;
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
  onClick?: () => void;
  children: ReactNode;
  style?: CSSProperties;
  title?: string;
}) {
  const sizes: Record<Size, CSSProperties> = {
    sm: { padding: "6px 12px", fontSize: 12 },
    md: { padding: "10px 16px", fontSize: 14 },
    lg: { padding: "14px 22px", fontSize: 15 },
  };
  const variants: Record<Variant, CSSProperties> = {
    primary: { background: "var(--cream)", color: "var(--dark)" },
    secondary: {
      background: "transparent",
      color: "var(--text-on-dark)",
      borderColor: "var(--dark-border)",
    },
    ghost: { background: "transparent", color: "var(--text-on-dark-muted)" },
    danger: { background: "transparent", color: "#ff6b6b", borderColor: "#3a2222" },
  };
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      title={title}
      style={{
        ...baseButton,
        ...sizes[size],
        ...variants[variant],
        opacity: disabled ? 0.45 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      style={{
        width: "100%",
        padding: "12px 14px",
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        borderRadius: 10,
        color: "var(--text-on-dark)",
        fontSize: 14,
        outline: "none",
        ...props.style,
      }}
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      style={{
        width: "100%",
        padding: "12px 14px",
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        borderRadius: 10,
        color: "var(--text-on-dark)",
        fontSize: 14,
        outline: "none",
        resize: "vertical",
        fontFamily: "inherit",
        ...props.style,
      }}
    />
  );
}

export function Select(
  props: React.SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }
) {
  return (
    <select
      {...props}
      style={{
        width: "100%",
        padding: "12px 14px",
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        borderRadius: 10,
        color: "var(--text-on-dark)",
        fontSize: 14,
        outline: "none",
        appearance: "none",
        ...props.style,
      }}
    >
      {props.children}
    </select>
  );
}

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label
      htmlFor={htmlFor}
      style={{
        display: "block",
        fontSize: 11,
        letterSpacing: "0.15em",
        textTransform: "uppercase",
        color: "var(--text-on-dark-muted)",
        marginBottom: 6,
      }}
    >
      {children}
    </label>
  );
}

export function Card({
  children,
  style,
  onClick,
}: {
  children: ReactNode;
  style?: CSSProperties;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        borderRadius: 16,
        padding: 24,
        cursor: onClick ? "pointer" : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export function Section({
  title,
  subtitle,
  right,
  children,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section style={{ marginBottom: 40 }}>
      <header
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          marginBottom: 16,
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 32, lineHeight: 1.1 }}>
            {title}
          </h2>
          {subtitle && (
            <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14, marginTop: 4 }}>
              {subtitle}
            </p>
          )}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "warn" | "good" | "bad";
}) {
  const tones: Record<string, CSSProperties> = {
    neutral: { background: "var(--dark-hover)", color: "var(--text-on-dark-muted)" },
    warn: { background: "rgba(200, 169, 126, 0.15)", color: "var(--gold)" },
    good: { background: "rgba(120, 200, 130, 0.15)", color: "#7dca8b" },
    bad: { background: "rgba(255, 107, 107, 0.15)", color: "#ff8a8a" },
  };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "3px 8px",
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 500,
        letterSpacing: "0.04em",
        ...tones[tone],
      }}
    >
      {children}
    </span>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div
      style={{
        padding: 40,
        textAlign: "center",
        border: "1px dashed var(--dark-border)",
        borderRadius: 14,
        color: "var(--text-on-dark-muted)",
      }}
    >
      <p style={{ fontFamily: "var(--font-serif)", fontSize: 18, color: "var(--text-on-dark)" }}>
        {title}
      </p>
      {hint && <p style={{ fontSize: 13, marginTop: 6 }}>{hint}</p>}
    </div>
  );
}

export function Divider() {
  return <hr style={{ border: 0, borderTop: "1px solid var(--dark-border)", margin: "16px 0" }} />;
}

export function Money({ cents, currency = "CAD" }: { cents: number; currency?: string }) {
  const v = (cents / 100).toLocaleString("en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });
  return <span style={{ fontVariantNumeric: "tabular-nums" }}>{v}</span>;
}
