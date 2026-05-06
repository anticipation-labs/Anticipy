"use client";

import { useEffect, useMemo, useState, ChangeEvent, DragEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Button, Card, Empty, Input, Label, Money, Section, Select, Textarea, Badge } from "@/components/crm/ui";
import { crmFetch, readPickedUser } from "@/lib/crm/userContext";
import type { CrmExpense, CrmUser, ReceiptExtraction, ExpenseCategory, PaymentMethod, ProductTag, ExpenseStatus } from "@/lib/crm/types";

const CATEGORIES: ExpenseCategory[] = [
  "hardware",
  "software_subscription",
  "services",
  "travel",
  "meals",
  "office",
  "marketing",
  "legal",
  "other",
];
const PAYMENT_METHODS: PaymentMethod[] = ["credit_card", "debit", "bank_transfer", "cash", "other"];
const PRODUCT_TAGS: ProductTag[] = ["anticipy", "aevoy", "both", "neither"];
const STATUSES: ExpenseStatus[] = ["pending_review", "confirmed", "missing_info"];

type ExpenseRow = CrmExpense & {
  vendor: { name: string } | null;
  paid_by: { name: string } | null;
};

export function ExpensesView() {
  const params = useSearchParams();
  const [expenses, setExpenses] = useState<ExpenseRow[]>([]);
  const [users, setUsers] = useState<CrmUser[]>([]);
  const [filters, setFilters] = useState({
    from: "",
    to: "",
    category: "",
    status: "",
    product_tag: "",
    paid_by: "",
  });
  const [showAdd, setShowAdd] = useState(params.get("new") === "1");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    const qs = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v));
    const r = await crmFetch(`/api/crm/expenses?${qs.toString()}`);
    if (!r.ok) {
      setError("Could not load expenses");
      setLoading(false);
      return;
    }
    const j = await r.json();
    setExpenses(j.expenses || []);
    setLoading(false);
  }

  async function loadUsers() {
    const r = await crmFetch("/api/crm/users");
    if (r.ok) setUsers((await r.json()).users || []);
  }

  useEffect(() => {
    loadUsers();
  }, []);
  useEffect(() => {
    load();
  }, [filters]);

  const totalCents = useMemo(
    () => expenses.reduce((acc, e) => acc + (e.amount_cents || 0), 0),
    [expenses]
  );

  async function exportFile(format: "csv" | "xlsx") {
    const qs = new URLSearchParams({ format });
    Object.entries(filters).forEach(([k, v]) => v && qs.set(k, v));
    window.location.href = `/api/crm/expenses/export?${qs.toString()}`;
  }

  return (
    <div>
      <Section
        title="Expenses"
        subtitle={`${expenses.length} expense${expenses.length === 1 ? "" : "s"} totaling ${(
          totalCents / 100
        ).toLocaleString("en-CA", { style: "currency", currency: "CAD" })}`}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="secondary" onClick={() => exportFile("csv")}>Export CSV</Button>
            <Button variant="secondary" onClick={() => exportFile("xlsx")}>Export XLSX</Button>
            <Button onClick={() => setShowAdd(true)}>+ New expense</Button>
          </div>
        }
      />

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 24 }}>
        <aside>
          <FilterRail filters={filters} setFilters={setFilters} users={users} />
        </aside>

        <div>
          {error && <p style={{ color: "#ff8a8a", marginBottom: 12 }}>{error}</p>}
          {loading ? (
            <Empty title="Loading expenses." />
          ) : expenses.length === 0 ? (
            <Empty title="No expenses yet." hint="Click + New expense to add your first one." />
          ) : (
            <div
              style={{
                background: "var(--dark-elevated)",
                border: "1px solid var(--dark-border)",
                borderRadius: 16,
                overflow: "hidden",
              }}
            >
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr style={{ textAlign: "left", color: "var(--text-on-dark-muted)" }}>
                    <Th>Date</Th>
                    <Th>Vendor</Th>
                    <Th>Category</Th>
                    <Th>Paid by</Th>
                    <Th>Status</Th>
                    <Th style={{ textAlign: "right" }}>Amount</Th>
                  </tr>
                </thead>
                <tbody>
                  {expenses.map((e) => (
                    <tr key={e.id} style={{ borderTop: "1px solid var(--dark-border)" }}>
                      <Td>{e.date ?? ""}</Td>
                      <Td>{e.vendor?.name ?? ""}</Td>
                      <Td>{e.category ?? ""}</Td>
                      <Td>{e.paid_by?.name ?? ""}</Td>
                      <Td>
                        <StatusBadge status={e.status} />
                      </Td>
                      <Td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        <Money cents={e.amount_cents} currency={e.currency} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {showAdd && (
        <AddExpensePanel
          onClose={() => setShowAdd(false)}
          users={users}
          onSaved={() => {
            setShowAdd(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function Th({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <th
      style={{
        padding: "12px 16px",
        fontSize: 11,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        fontWeight: 500,
        ...style,
      }}
    >
      {children}
    </th>
  );
}
function Td({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <td style={{ padding: "14px 16px", verticalAlign: "middle", ...style }}>{children}</td>
  );
}

function StatusBadge({ status }: { status: ExpenseStatus }) {
  const tone = status === "confirmed" ? "good" : status === "pending_review" ? "warn" : "bad";
  return <Badge tone={tone}>{status.replace("_", " ")}</Badge>;
}

function FilterRail({
  filters,
  setFilters,
  users,
}: {
  filters: any;
  setFilters: (f: any) => void;
  users: CrmUser[];
}) {
  function set(k: string, v: string) {
    setFilters((prev: any) => ({ ...prev, [k]: v }));
  }
  return (
    <Card>
      <h3
        style={{
          fontSize: 11,
          letterSpacing: "0.15em",
          textTransform: "uppercase",
          color: "var(--text-on-dark-muted)",
          marginBottom: 14,
        }}
      >
        Filter
      </h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <div>
          <Label>From</Label>
          <Input type="date" value={filters.from} onChange={(e) => set("from", e.target.value)} />
        </div>
        <div>
          <Label>To</Label>
          <Input type="date" value={filters.to} onChange={(e) => set("to", e.target.value)} />
        </div>
        <div>
          <Label>Category</Label>
          <Select value={filters.category} onChange={(e) => set("category", e.target.value)}>
            <option value="">All</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label>Paid by</Label>
          <Select value={filters.paid_by} onChange={(e) => set("paid_by", e.target.value)}>
            <option value="">Anyone</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </Select>
        </div>
        <div>
          <Label>Product tag</Label>
          <Select value={filters.product_tag} onChange={(e) => set("product_tag", e.target.value)}>
            <option value="">All</option>
            {PRODUCT_TAGS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </Select>
        </div>
        <div>
          <Label>Status</Label>
          <Select value={filters.status} onChange={(e) => set("status", e.target.value)}>
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s.replace("_", " ")}</option>
            ))}
          </Select>
        </div>
        <Button
          variant="ghost"
          onClick={() =>
            setFilters({ from: "", to: "", category: "", status: "", product_tag: "", paid_by: "" })
          }
        >
          Reset filters
        </Button>
      </div>
    </Card>
  );
}

function AddExpensePanel({
  onClose,
  users,
  onSaved,
}: {
  onClose: () => void;
  users: CrmUser[];
  onSaved: () => void;
}) {
  const me = readPickedUser();
  const [files, setFiles] = useState<File[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState("");
  const [storagePaths, setStoragePaths] = useState<string[]>([]);
  const [extraction, setExtraction] = useState<ReceiptExtraction | null>(null);
  const [missing, setMissing] = useState<string[]>([]);
  const [form, setForm] = useState<any>({
    vendor_name: "",
    amount_cents: 0,
    currency: "CAD",
    date: "",
    category: "other",
    payment_method: "credit_card",
    paid_by_user_id: me?.id || "",
    product_tag: "anticipy",
    reimbursable: false,
    gst_cents: null,
    pst_cents: null,
    status: "pending_review",
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files);
    if (dropped.length > 0) addFiles(dropped);
  }
  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const list = Array.from(e.target.files || []);
    if (list.length > 0) addFiles(list);
  }
  function addFiles(list: File[]) {
    const next = [...files, ...list].slice(0, 6);
    setFiles(next);
    runExtraction(next);
  }

  async function runExtraction(list: File[]) {
    setExtracting(true);
    setExtractError("");
    try {
      const fd = new FormData();
      list.forEach((f) => fd.append("files", f));
      const r = await crmFetch("/api/crm/extract-receipt", { method: "POST", body: fd });
      const j = await r.json();
      if (j.error && !j.extraction) {
        setExtractError(j.error);
      }
      setStoragePaths(j.storage_paths || []);
      if (j.extraction) {
        const x: ReceiptExtraction = j.extraction;
        setExtraction(x);
        setMissing(x.missing_fields || []);
        setForm((prev: any) => ({
          ...prev,
          vendor_name: x.vendor || prev.vendor_name,
          amount_cents: x.amount_cents ?? prev.amount_cents,
          currency: x.currency || prev.currency,
          date: x.date || prev.date,
          category: x.category || prev.category,
          payment_method: x.payment_method || prev.payment_method,
          gst_cents: x.gst_cents,
          pst_cents: x.pst_cents,
          status: x.confidence < 0.7 ? "pending_review" : "confirmed",
        }));
      }
    } catch (err: any) {
      setExtractError(err?.message || "Could not analyze the receipt");
    } finally {
      setExtracting(false);
    }
  }

  async function save() {
    setSaving(true);
    setSaveError("");
    const payload = {
      ...form,
      amount_cents: Math.round(Number(form.amount_cents) || 0),
      gst_cents: form.gst_cents == null ? null : Math.round(Number(form.gst_cents)),
      pst_cents: form.pst_cents == null ? null : Math.round(Number(form.pst_cents)),
      receipt_storage_paths: storagePaths,
      raw_extraction_jsonb: extraction,
      extraction_confidence: extraction?.confidence ?? null,
      missing_fields: missing,
    };
    const r = await crmFetch("/api/crm/expenses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setSaveError(j.error || "Save failed");
      setSaving(false);
      return;
    }
    onSaved();
  }

  function field(name: string, label: string, type = "text") {
    const isMissing = missing.includes(name);
    return (
      <div>
        <Label>
          {label}
          {isMissing && (
            <span style={{ color: "var(--gold)", marginLeft: 6, textTransform: "none", letterSpacing: 0 }}>
              please fill
            </span>
          )}
        </Label>
        <Input
          type={type}
          value={form[name] ?? ""}
          onChange={(e) => {
            const v = type === "number" ? Number(e.target.value) : e.target.value;
            setForm((prev: any) => ({ ...prev, [name]: v }));
            if (isMissing) setMissing((m) => m.filter((s) => s !== name));
          }}
          style={isMissing ? { borderColor: "var(--gold)" } : undefined}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        justifyContent: "flex-end",
        zIndex: 60,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(560px, 100%)",
          background: "var(--dark)",
          borderLeft: "1px solid var(--dark-border)",
          padding: 24,
          overflowY: "auto",
        }}
      >
        <header style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 28 }}>New expense</h2>
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </header>

        <div
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
          style={{
            border: "1px dashed var(--dark-border)",
            borderRadius: 14,
            padding: 24,
            textAlign: "center",
            marginBottom: 20,
            background: "var(--dark-elevated)",
          }}
        >
          <p style={{ color: "var(--text-on-dark-muted)", fontSize: 14 }}>
            Drop receipt photos here, or
          </p>
          <label
            style={{
              display: "inline-block",
              marginTop: 10,
              padding: "10px 16px",
              background: "var(--cream)",
              color: "var(--dark)",
              borderRadius: 10,
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 500,
            }}
          >
            Pick photos
            <input
              type="file"
              accept="image/*"
              multiple
              capture="environment"
              onChange={onPick}
              style={{ display: "none" }}
            />
          </label>
          {files.length > 0 && (
            <p style={{ marginTop: 10, fontSize: 13, color: "var(--text-on-dark-muted)" }}>
              {files.length} photo{files.length === 1 ? "" : "s"} attached
            </p>
          )}
          {extracting && (
            <p style={{ marginTop: 10, fontSize: 13, color: "var(--gold)" }}>
              Analyzing.
            </p>
          )}
          {extractError && (
            <p style={{ marginTop: 10, fontSize: 13, color: "#ff8a8a" }}>{extractError}</p>
          )}
          {extraction && (
            <p style={{ marginTop: 10, fontSize: 12, color: "var(--text-on-dark-muted)" }}>
              Confidence {(extraction.confidence * 100).toFixed(0)}%
            </p>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {field("vendor_name", "Vendor")}
          {field("date", "Date", "date")}
          {field("amount_cents", "Amount (cents)", "number")}
          <div>
            <Label>Currency</Label>
            <Select value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
              <option value="CAD">CAD</option>
              <option value="USD">USD</option>
            </Select>
          </div>
          <div>
            <Label>Category</Label>
            <Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Payment method</Label>
            <Select
              value={form.payment_method}
              onChange={(e) => setForm({ ...form, payment_method: e.target.value })}
            >
              {PAYMENT_METHODS.map((p) => (
                <option key={p} value={p}>
                  {p.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Paid by</Label>
            <Select
              value={form.paid_by_user_id}
              onChange={(e) => setForm({ ...form, paid_by_user_id: e.target.value })}
            >
              <option value="">Choose</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Product</Label>
            <Select
              value={form.product_tag}
              onChange={(e) => setForm({ ...form, product_tag: e.target.value })}
            >
              {PRODUCT_TAGS.map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Reimbursable</Label>
            <Select
              value={form.reimbursable ? "yes" : "no"}
              onChange={(e) => setForm({ ...form, reimbursable: e.target.value === "yes" })}
            >
              <option value="no">no</option>
              <option value="yes">yes</option>
            </Select>
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <Label>Notes</Label>
          <Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </div>

        {saveError && <p style={{ color: "#ff8a8a", marginTop: 12 }}>{saveError}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={saving}>{saving ? "Saving" : "Save expense"}</Button>
        </div>
      </div>
    </div>
  );
}
