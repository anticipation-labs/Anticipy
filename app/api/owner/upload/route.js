import { randomUUID } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { ENGINE_URL, engineHeaders } from "../../_engine";

const UPLOAD_ROOT = process.env.ANTICIPY_UPLOAD_ROOT || path.join(os.tmpdir(), "anticipy-owner-uploads");
const MAX_UPLOAD_BYTES = Number(process.env.ANTICIPY_MAX_UPLOAD_BYTES || 100 * 1024 * 1024);

function safeFilename(name) {
  return (name || "owner-upload.txt").replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 160);
}

export async function POST(request) {
  let uploadDir = "";
  try {
    const form = await request.formData();
    const file = form.get("file");
    if (!file || typeof file.arrayBuffer !== "function") {
      return Response.json({ error: "missing_file", message: "Upload a transcript or audio file." }, { status: 400 });
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      return Response.json(
        {
          error: "upload_too_large",
          message: `Upload is too large (${file.size} bytes > ${MAX_UPLOAD_BYTES}).`,
        },
        { status: 413 },
      );
    }

    uploadDir = path.join(UPLOAD_ROOT, randomUUID());
    await mkdir(uploadDir, { recursive: true });
    const filename = safeFilename(file.name);
    const localPath = path.join(uploadDir, filename);
    await writeFile(localPath, Buffer.from(await file.arrayBuffer()));

    const response = await fetch(`${ENGINE_URL}/owner/ingest-file`, {
      method: "POST",
      headers: engineHeaders({ "content-type": "application/json" }),
      body: JSON.stringify({
        path: localPath,
        filename,
        source: String(form.get("source") || "upload"),
        execute_actions: String(form.get("execute_actions") || "false") === "true",
        meta: { ui: "owner_mode", uploaded_via: "next_api" },
      }),
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    return Response.json(data, { status: response.status });
  } catch (error) {
    return Response.json(
      {
        error: "upload_failed",
        message: `Could not process upload through Anticipy Engine at ${ENGINE_URL}`,
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 },
    );
  } finally {
    if (uploadDir) {
      await rm(uploadDir, { recursive: true, force: true });
    }
  }
}
