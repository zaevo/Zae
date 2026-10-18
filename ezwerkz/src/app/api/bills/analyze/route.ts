import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { requireRole } from "@/lib/auth";
import { isDemoMode } from "@/lib/env";
import { analyzeBill, BillAnalysisError } from "@/lib/ai/billNegotiator";
import { BILL_MAX_BYTES, BILL_UPLOAD_MESSAGES, extensionFor, validateBillUpload } from "@/lib/ai/billUpload";
import { getDemoCreditState } from "@/lib/demo/credit";
import { CreditActionError, handleCredit } from "@/lib/credit/errors";
import { billAnalysisBundle } from "@/lib/credit/queries";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
export const maxDuration = 120;

const DAILY_LIMIT = 20;

/**
 * AI Bill Negotiator upload. multipart/form-data with a `file` field:
 * image/png, image/jpeg, image/webp or application/pdf, at most 10 MB.
 * The result suggests what the member can say; EzWerkz never contacts the
 * provider or speaks for the member.
 */
export async function POST(req: Request) {
  return handleCredit(async () => {
    const user = await requireRole("member", "worker", "admin");

    const declaredLength = Number(req.headers.get("content-length") ?? 0);
    // Multipart overhead is small; reject clearly oversized bodies before buffering them.
    if (declaredLength > BILL_MAX_BYTES + 64 * 1024) {
      throw new CreditActionError("UPLOAD_INVALID", BILL_UPLOAD_MESSAGES.TOO_LARGE, 413);
    }

    let form: FormData;
    try {
      form = await req.formData();
    } catch {
      throw new CreditActionError("UPLOAD_INVALID", "Send the bill as multipart/form-data in a field named \"file\".", 400);
    }
    const file = form.get("file");
    if (!(file instanceof File)) throw new CreditActionError("UPLOAD_INVALID", BILL_UPLOAD_MESSAGES.MISSING_FILE, 400);
    if (file.size > BILL_MAX_BYTES) throw new CreditActionError("UPLOAD_INVALID", BILL_UPLOAD_MESSAGES.TOO_LARGE, 413);

    const bytes = new Uint8Array(await file.arrayBuffer());
    const check = validateBillUpload({ declaredType: file.type, size: bytes.byteLength, head: bytes.subarray(0, 16) });
    if (!check.ok) {
      const status = check.error === "TOO_LARGE" ? 413 : check.error === "UNSUPPORTED_TYPE" || check.error === "TYPE_MISMATCH" ? 415 : 400;
      throw new CreditActionError("UPLOAD_INVALID", check.message, status);
    }

    const id = randomUUID();
    const fileName = file.name ? file.name.slice(0, 200) : null;

    if (!isDemoMode()) {
      const supabase = await createSupabaseServerClient();
      const since = new Date(Date.now() - 86_400_000).toISOString();
      const recent = await supabase.from("bill_analyses").select("id", { count: "exact", head: true }).eq("user_id", user.id).gte("created_at", since);
      if ((recent.count ?? 0) >= DAILY_LIMIT) {
        return NextResponse.json({ error: "RATE_LIMITED", message: "You've analyzed a lot of bills today. Try again tomorrow." }, { status: 429 });
      }
    }

    let analysis;
    try {
      analysis = await analyzeBill({ id, bytes, mediaType: check.mediaType, fileName });
    } catch (err) {
      if (err instanceof BillAnalysisError) {
        throw new CreditActionError("ANALYSIS_FAILED", err.message, err.code === "UPSTREAM" ? 502 : 422);
      }
      throw err;
    }

    if (isDemoMode()) {
      getDemoCreditState(user).billAnalyses.push(analysis);
      return { analysis };
    }

    // Server-chosen path under the member's own folder (the bucket policy allows only that folder).
    const storagePath = `${user.id}/${id}.${extensionFor(check.mediaType)}`;
    const supabase = await createSupabaseServerClient();
    const upload = await supabase.storage.from("bill-uploads").upload(storagePath, bytes, { contentType: check.mediaType, upsert: false });
    if (upload.error) throw new Error(`Failed to store bill: ${upload.error.message}`);

    const ins = await supabase.from("bill_analyses").insert({
      id,
      user_id: user.id,
      storage_path: storagePath,
      provider_name: analysis.provider.slice(0, 120),
      bill_category: analysis.category,
      status: "complete",
      billed_amount_cents: analysis.totalDueCents,
      potential_savings_cents: analysis.estimatedMonthlySavingsCents,
      findings: analysis.flaggedIssues,
      negotiation_script: billAnalysisBundle(analysis),
      model: analysis.model,
    });
    if (ins.error) throw new Error(`Failed to save analysis: ${ins.error.message}`);
    return { analysis };
  });
}
