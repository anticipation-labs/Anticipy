/**
 * TypeScript types mirroring the crm_* schema.
 * Keep in sync with the migration in supabase/migrations.
 */

export type CrmUser = {
  id: string;
  name: string;
  email: string | null;
  is_admin?: boolean;
  has_password?: boolean;
  created_at: string;
};

export type ContactSource = "gmail" | "outreach" | "manual" | "vendor";

export type CrmContact = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  role: string | null;
  source: ContactSource;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CrmVendor = {
  id: string;
  name: string;
  contact_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type ExpenseCategory =
  | "hardware"
  | "software_subscription"
  | "services"
  | "travel"
  | "meals"
  | "office"
  | "marketing"
  | "legal"
  | "other";

export type PaymentMethod =
  | "credit_card"
  | "debit"
  | "bank_transfer"
  | "cash"
  | "other";

export type ProductTag = "anticipy" | "aevoy" | "both" | "neither";
export type ExpenseStatus = "pending_review" | "confirmed" | "missing_info";

export type CrmExpense = {
  id: string;
  vendor_id: string | null;
  amount_cents: number;
  currency: string;
  date: string | null;
  category: ExpenseCategory | null;
  payment_method: PaymentMethod | null;
  paid_by_user_id: string | null;
  product_tag: ProductTag;
  reimbursable: boolean;
  gst_cents: number | null;
  pst_cents: number | null;
  receipt_storage_paths: string[];
  raw_extraction_jsonb: ReceiptExtraction | null;
  extraction_confidence: number | null;
  status: ExpenseStatus;
  missing_fields: string[];
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type TodoStatus = "todo" | "doing" | "done";
export type TodoPriority = "low" | "normal" | "high";

export type CrmTodo = {
  id: string;
  title: string;
  description: string | null;
  assignee_user_id: string | null;
  is_shared: boolean;
  created_by_user_id: string | null;
  due_date: string | null;
  status: TodoStatus;
  priority: TodoPriority | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type CrmTodoComment = {
  id: string;
  todo_id: string;
  author_user_id: string | null;
  body: string;
  created_at: string;
};

export type CrmFile = {
  id: string;
  project_folder: string;
  filename: string;
  storage_path: string;
  mime_type: string | null;
  size_bytes: number | null;
  uploaded_by_user_id: string | null;
  description: string | null;
  vendor_id: string | null;
  created_at: string;
};

export type CrmFileComment = {
  id: string;
  file_id: string;
  author_user_id: string | null;
  body: string;
  created_at: string;
};

export type CrmVoiceMemo = {
  id: string;
  user_id: string | null;
  audio_storage_path: string;
  transcript: string | null;
  duration_seconds: number | null;
  recorded_date: string;
  created_at: string;
};

export type CrmDecision = {
  id: string;
  title: string;
  body: string | null;
  decided_at: string;
  decided_by_user_id: string | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
};

export type CrmAgentEvent = {
  id: string;
  agent_name: string;
  action: string;
  summary: string;
  payload_jsonb: unknown | null;
  related_entity_type: string | null;
  related_entity_id: string | null;
  created_at: string;
};

export type ReceiptExtraction = {
  vendor: string | null;
  amount_cents: number | null;
  currency: "CAD" | "USD" | null;
  date: string | null;
  category: ExpenseCategory | null;
  payment_method: PaymentMethod | null;
  gst_cents: number | null;
  pst_cents: number | null;
  line_items: { description: string; amount_cents: number }[];
  confidence: number;
  missing_fields: string[];
};

export const DEFAULT_FOLDERS = [
  "aurora-hardware",
  "aurora-shells",
  "packaging",
  "bom",
  "datasheets",
  "supplier-quotes",
  "other",
] as const;
