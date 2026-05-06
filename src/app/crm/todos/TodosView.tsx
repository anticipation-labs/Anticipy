"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Badge,
  Button,
  Card,
  Empty,
  Input,
  Label,
  Section,
  Select,
  Textarea,
} from "@/components/crm/ui";
import { crmFetch, readPickedUser } from "@/lib/crm/userContext";
import type { CrmTodo, CrmTodoComment, CrmUser, TodoPriority, TodoStatus } from "@/lib/crm/types";

type TodoRow = CrmTodo & {
  assignee?: { name: string; email: string | null } | null;
  creator?: { name: string } | null;
};
type CommentRow = CrmTodoComment & { author?: { name: string } | null };

type View = "list" | "kanban" | "calendar";
type ScopeFilter = "all" | "mine" | "shared" | "user";
type StatusFilter = "all" | TodoStatus;

export function TodosView() {
  const params = useSearchParams();
  const me = readPickedUser();
  const [todos, setTodos] = useState<TodoRow[]>([]);
  const [users, setUsers] = useState<CrmUser[]>([]);
  const [view, setView] = useState<View>("list");
  const [scope, setScope] = useState<ScopeFilter>("all");
  const [scopeUser, setScopeUser] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [showAdd, setShowAdd] = useState(false);
  const [focused, setFocused] = useState<TodoRow | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const r = await crmFetch("/api/crm/todos");
    const j = await r.json();
    setTodos(j.todos || []);
    setLoading(false);
  }
  useEffect(() => {
    load();
    crmFetch("/api/crm/users").then(async (r) => {
      if (r.ok) setUsers((await r.json()).users || []);
    });
  }, []);

  useEffect(() => {
    const focusId = params.get("focus");
    if (focusId && todos.length) {
      const found = todos.find((t) => t.id === focusId);
      if (found) setFocused(found);
    }
  }, [params, todos]);

  const visible = useMemo(() => {
    return todos.filter((t) => {
      if (statusFilter !== "all" && t.status !== statusFilter) return false;
      if (scope === "mine") return me && t.assignee_user_id === me.id;
      if (scope === "shared") return t.is_shared;
      if (scope === "user" && scopeUser) return t.assignee_user_id === scopeUser;
      return true;
    });
  }, [todos, scope, scopeUser, statusFilter, me]);

  return (
    <div>
      <Section
        title="Todos"
        subtitle={`${visible.length} of ${todos.length} todos`}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <ViewToggle value={view} onChange={setView} />
            <Button onClick={() => setShowAdd(true)}>+ New todo</Button>
          </div>
        }
      />

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
        <Chip active={scope === "all"} onClick={() => setScope("all")}>All</Chip>
        {me && (
          <Chip active={scope === "mine"} onClick={() => setScope("mine")}>Mine</Chip>
        )}
        <Chip active={scope === "shared"} onClick={() => setScope("shared")}>Shared</Chip>
        {users
          .filter((u) => !me || u.id !== me.id)
          .map((u) => (
            <Chip
              key={u.id}
              active={scope === "user" && scopeUser === u.id}
              onClick={() => {
                setScope("user");
                setScopeUser(u.id);
              }}
            >
              {u.name}
            </Chip>
          ))}
        <span style={{ width: 16 }} />
        <Chip active={statusFilter === "all"} onClick={() => setStatusFilter("all")}>All status</Chip>
        <Chip active={statusFilter === "todo"} onClick={() => setStatusFilter("todo")}>Todo</Chip>
        <Chip active={statusFilter === "doing"} onClick={() => setStatusFilter("doing")}>Doing</Chip>
        <Chip active={statusFilter === "done"} onClick={() => setStatusFilter("done")}>Done</Chip>
      </div>

      {loading ? (
        <Empty title="Loading todos." />
      ) : visible.length === 0 ? (
        <Empty title="Nothing here." hint="Add a todo with the button above." />
      ) : view === "list" ? (
        <ListView items={visible} onClick={setFocused} />
      ) : view === "kanban" ? (
        <KanbanView items={visible} onClick={setFocused} onMove={async (id, status) => {
          await crmFetch(`/api/crm/todos/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          });
          load();
        }} />
      ) : (
        <CalendarView items={visible} onClick={setFocused} />
      )}

      {showAdd && (
        <NewTodoPanel
          users={users}
          onClose={() => setShowAdd(false)}
          onSaved={() => {
            setShowAdd(false);
            load();
          }}
        />
      )}

      {focused && (
        <TodoDrawer
          todo={focused}
          users={users}
          onClose={() => setFocused(null)}
          onChanged={() => {
            load();
          }}
        />
      )}
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 12px",
        borderRadius: 999,
        background: active ? "var(--cream)" : "var(--dark-elevated)",
        color: active ? "var(--dark)" : "var(--text-on-dark-muted)",
        border: "1px solid var(--dark-border)",
        fontSize: 12,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function ViewToggle({ value, onChange }: { value: View; onChange: (v: View) => void }) {
  const opts: View[] = ["list", "kanban", "calendar"];
  return (
    <div
      style={{
        display: "inline-flex",
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        borderRadius: 10,
      }}
    >
      {opts.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          style={{
            padding: "8px 14px",
            background: value === o ? "var(--cream)" : "transparent",
            color: value === o ? "var(--dark)" : "var(--text-on-dark-muted)",
            border: "none",
            borderRadius: 10,
            fontSize: 12,
            cursor: "pointer",
            textTransform: "capitalize",
          }}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

function ListView({ items, onClick }: { items: TodoRow[]; onClick: (t: TodoRow) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {items.map((t) => (
        <TodoCard key={t.id} todo={t} onClick={() => onClick(t)} />
      ))}
    </div>
  );
}

function KanbanView({
  items,
  onClick,
  onMove,
}: {
  items: TodoRow[];
  onClick: (t: TodoRow) => void;
  onMove: (id: string, status: TodoStatus) => void;
}) {
  const cols: TodoStatus[] = ["todo", "doing", "done"];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
      {cols.map((c) => (
        <div
          key={c}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            const id = e.dataTransfer.getData("text/plain");
            if (id) onMove(id, c);
          }}
          style={{
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
            borderRadius: 14,
            padding: 12,
            minHeight: 280,
          }}
        >
          <h3
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--text-on-dark-muted)",
              marginBottom: 12,
            }}
          >
            {c} ({items.filter((i) => i.status === c).length})
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {items
              .filter((i) => i.status === c)
              .map((t) => (
                <div
                  key={t.id}
                  draggable
                  onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)}
                  onClick={() => onClick(t)}
                  style={{
                    background: "var(--dark)",
                    border: "1px solid var(--dark-border)",
                    borderRadius: 10,
                    padding: 12,
                    cursor: "pointer",
                  }}
                >
                  <p style={{ fontSize: 14 }}>{t.title}</p>
                  <p style={{ fontSize: 12, color: "var(--text-on-dark-muted)", marginTop: 4 }}>
                    {t.is_shared ? "Shared" : t.assignee?.name || "Unassigned"}
                    {t.due_date ? ` · ${t.due_date}` : ""}
                  </p>
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function CalendarView({ items, onClick }: { items: TodoRow[]; onClick: (t: TodoRow) => void }) {
  const grouped = useMemo(() => {
    const m: Record<string, TodoRow[]> = {};
    for (const t of items) {
      const key = t.due_date || "No due date";
      m[key] ??= [];
      m[key].push(t);
    }
    return Object.entries(m).sort(([a], [b]) => {
      if (a === "No due date") return 1;
      if (b === "No due date") return -1;
      return a.localeCompare(b);
    });
  }, [items]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {grouped.map(([day, list]) => (
        <Card key={day}>
          <h3
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--text-on-dark-muted)",
              marginBottom: 10,
            }}
          >
            {day}
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {list.map((t) => (
              <TodoCard key={t.id} todo={t} onClick={() => onClick(t)} />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function TodoCard({ todo, onClick }: { todo: TodoRow; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: "var(--dark-elevated)",
        border: "1px solid var(--dark-border)",
        borderRadius: 12,
        padding: "14px 16px",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <p
          style={{
            fontSize: 14,
            textDecoration: todo.status === "done" ? "line-through" : "none",
            color: todo.status === "done" ? "var(--text-on-dark-muted)" : "var(--text-on-dark)",
          }}
        >
          {todo.title}
        </p>
        <p style={{ fontSize: 12, color: "var(--text-on-dark-muted)", marginTop: 2 }}>
          {todo.is_shared ? "Shared" : todo.assignee?.name || "Unassigned"}
          {todo.due_date ? ` · ${todo.due_date}` : ""}
        </p>
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        {todo.priority && <Badge tone={todo.priority === "high" ? "warn" : "neutral"}>{todo.priority}</Badge>}
        <Badge tone={todo.status === "done" ? "good" : todo.status === "doing" ? "warn" : "neutral"}>
          {todo.status}
        </Badge>
      </div>
    </div>
  );
}

function NewTodoPanel({
  users,
  onClose,
  onSaved,
}: {
  users: CrmUser[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const me = readPickedUser();
  const [form, setForm] = useState({
    title: "",
    description: "",
    assignee: me?.id || "",
    is_shared: false,
    due_date: "",
    priority: "" as "" | TodoPriority,
  });
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    if (!form.title.trim()) {
      setError("Title required");
      return;
    }
    setSaving(true);
    const payload: any = {
      title: form.title,
      description: form.description || null,
      is_shared: form.is_shared,
      assignee_user_id: form.is_shared ? null : form.assignee || null,
      due_date: form.due_date || null,
      priority: form.priority || null,
    };
    const r = await crmFetch("/api/crm/todos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      setError("Save failed");
      setSaving(false);
      return;
    }
    onSaved();
  }

  return (
    <Drawer onClose={onClose} title="New todo">
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div>
          <Label>Title</Label>
          <Input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            autoFocus
          />
        </div>
        <div>
          <Label>Description</Label>
          <Textarea
            rows={4}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <Label>Assignee</Label>
            <Select
              value={form.is_shared ? "_shared" : form.assignee}
              onChange={(e) => {
                if (e.target.value === "_shared") {
                  setForm({ ...form, is_shared: true });
                } else {
                  setForm({ ...form, is_shared: false, assignee: e.target.value });
                }
              }}
            >
              <option value="">Unassigned</option>
              <option value="_shared">Shared</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.name}</option>
              ))}
            </Select>
          </div>
          <div>
            <Label>Due date</Label>
            <Input
              type="date"
              value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
            />
          </div>
          <div>
            <Label>Priority</Label>
            <Select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value as any })}
            >
              <option value="">None</option>
              <option value="low">Low</option>
              <option value="normal">Normal</option>
              <option value="high">High</option>
            </Select>
          </div>
        </div>
        {error && <p style={{ color: "#ff8a8a" }}>{error}</p>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving" : "Add todo"}
          </Button>
        </div>
      </div>
    </Drawer>
  );
}

function TodoDrawer({
  todo,
  users,
  onClose,
  onChanged,
}: {
  todo: TodoRow;
  users: CrmUser[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const [comments, setComments] = useState<CommentRow[]>([]);
  const [text, setText] = useState("");
  const [edit, setEdit] = useState(false);
  const [draft, setDraft] = useState({
    title: todo.title,
    description: todo.description || "",
    assignee_user_id: todo.assignee_user_id || "",
    is_shared: todo.is_shared,
    due_date: todo.due_date || "",
    priority: todo.priority || "",
    status: todo.status,
  });

  async function loadComments() {
    const r = await crmFetch(`/api/crm/todos/${todo.id}/comments`);
    const j = await r.json();
    setComments(j.comments || []);
  }
  useEffect(() => { loadComments(); }, [todo.id]);

  async function postComment() {
    if (!text.trim()) return;
    await crmFetch(`/api/crm/todos/${todo.id}/comments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: text }),
    });
    setText("");
    loadComments();
  }

  async function saveEdit() {
    const payload: any = {
      title: draft.title,
      description: draft.description || null,
      assignee_user_id: draft.is_shared ? null : draft.assignee_user_id || null,
      is_shared: draft.is_shared,
      due_date: draft.due_date || null,
      priority: draft.priority || null,
      status: draft.status,
    };
    await crmFetch(`/api/crm/todos/${todo.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setEdit(false);
    onChanged();
    onClose();
  }

  async function setStatus(s: TodoStatus) {
    await crmFetch(`/api/crm/todos/${todo.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: s }),
    });
    onChanged();
  }

  async function remove() {
    await crmFetch(`/api/crm/todos/${todo.id}`, { method: "DELETE" });
    onClose();
    onChanged();
  }

  return (
    <Drawer onClose={onClose} title={edit ? "Edit todo" : todo.title}>
      {edit ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <Label>Title</Label>
            <Input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea
              rows={4}
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <Label>Assignee</Label>
              <Select
                value={draft.is_shared ? "_shared" : draft.assignee_user_id || ""}
                onChange={(e) => {
                  if (e.target.value === "_shared") setDraft({ ...draft, is_shared: true });
                  else setDraft({ ...draft, is_shared: false, assignee_user_id: e.target.value });
                }}
              >
                <option value="">Unassigned</option>
                <option value="_shared">Shared</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.name}</option>
                ))}
              </Select>
            </div>
            <div>
              <Label>Due date</Label>
              <Input
                type="date"
                value={draft.due_date}
                onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
              />
            </div>
            <div>
              <Label>Priority</Label>
              <Select
                value={draft.priority || ""}
                onChange={(e) => setDraft({ ...draft, priority: (e.target.value as any) || "" })}
              >
                <option value="">None</option>
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </Select>
            </div>
            <div>
              <Label>Status</Label>
              <Select
                value={draft.status}
                onChange={(e) => setDraft({ ...draft, status: e.target.value as TodoStatus })}
              >
                <option value="todo">Todo</option>
                <option value="doing">Doing</option>
                <option value="done">Done</option>
              </Select>
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <Button variant="danger" onClick={remove}>Delete</Button>
            <div style={{ display: "flex", gap: 8 }}>
              <Button variant="secondary" onClick={() => setEdit(false)}>Cancel</Button>
              <Button onClick={saveEdit}>Save</Button>
            </div>
          </div>
        </div>
      ) : (
        <div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
            <Badge>{todo.is_shared ? "Shared" : todo.assignee?.name || "Unassigned"}</Badge>
            {todo.due_date && <Badge>{todo.due_date}</Badge>}
            {todo.priority && <Badge tone={todo.priority === "high" ? "warn" : "neutral"}>{todo.priority}</Badge>}
            <Badge tone={todo.status === "done" ? "good" : todo.status === "doing" ? "warn" : "neutral"}>
              {todo.status}
            </Badge>
          </div>
          {todo.description && (
            <div
              style={{
                marginTop: 8,
                fontSize: 14,
                color: "var(--text-on-dark)",
                lineHeight: 1.6,
              }}
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{todo.description}</ReactMarkdown>
            </div>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
            <Button variant="secondary" onClick={() => setStatus("todo")}>Todo</Button>
            <Button variant="secondary" onClick={() => setStatus("doing")}>Doing</Button>
            <Button variant="secondary" onClick={() => setStatus("done")}>Done</Button>
            <Button variant="ghost" onClick={() => setEdit(true)}>Edit</Button>
          </div>

          <hr style={{ borderTop: "1px solid var(--dark-border)", border: 0, margin: "24px 0" }} />

          <h3
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "var(--text-on-dark-muted)",
              marginBottom: 10,
            }}
          >
            Comments
          </h3>
          {comments.length === 0 ? (
            <p style={{ fontSize: 13, color: "var(--text-on-dark-muted)" }}>No comments yet.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {comments.map((c) => (
                <div key={c.id}>
                  <div style={{ fontSize: 12, color: "var(--text-on-dark-muted)", marginBottom: 4 }}>
                    {c.author?.name || "?"} · {new Date(c.created_at).toLocaleString()}
                  </div>
                  <div style={{ fontSize: 14, lineHeight: 1.6 }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{c.body}</ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <Textarea
              rows={3}
              placeholder="Add a comment. Markdown ok."
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div style={{ marginTop: 6, display: "flex", justifyContent: "flex-end" }}>
              <Button onClick={postComment} disabled={!text.trim()}>Post</Button>
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}

function Drawer({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        justifyContent: "flex-end",
        zIndex: 60,
      }}
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
        <header style={{ display: "flex", justifyContent: "space-between", marginBottom: 16, gap: 12 }}>
          <h2 style={{ fontFamily: "var(--font-serif)", fontSize: 24, lineHeight: 1.2 }}>{title}</h2>
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </header>
        {children}
      </div>
    </div>
  );
}
