import Link from "next/link";

export function Footer() {
  return (
    <footer
      className="px-6 py-10 border-t"
      style={{
        background: "var(--dark)",
        borderColor: "var(--dark-border)",
      }}
    >
      <div className="max-w-container mx-auto">
        <div className="flex flex-col md:flex-row justify-between items-center gap-6">
          <p className="text-[13px] text-[var(--text-on-dark-muted)]">
            &copy; 2026 Anticipation Labs.
          </p>
          <nav className="flex gap-4">
            <Link
              href="/privacy"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Privacy Policy
            </Link>
            <Link
              href="/terms"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Terms of Service
            </Link>
            <Link
              href="/refund"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors"
            >
              Refund Policy
            </Link>
            <Link
              href="/engine"
              className="text-[13px] text-[var(--text-on-dark-muted)] hover:text-gold transition-colors opacity-50"
            >
              Engine
            </Link>
          </nav>
          <p className="text-[13px] text-[var(--text-on-dark-muted)]">
            omar@anticipy.ai
          </p>
        </div>
      </div>
    </footer>
  );
}
