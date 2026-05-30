// B061 + B064: replaced the legacy sessionStorage-only client-side gate
// with the real PasswordGate that calls /api/internal-gate (server-side
// constant-time compare + signed httpOnly cookie). The middleware in
// src/middleware.ts already blocks unauthenticated requests before any
// page renders, so this client form is purely a UX surface for users
// who land here through a normal browser.

import PasswordGate from "./PasswordGate";

export default function InternalLayout({ children }: { children: React.ReactNode }) {
  return <PasswordGate>{children}</PasswordGate>;
}
