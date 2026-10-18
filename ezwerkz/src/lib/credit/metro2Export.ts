/**
 * Builds the monthly Metro 2 file for a reporting period and records it in
 * metro2_exports. Admin-only (the route checks the role first).
 *
 * The file is PREPARED FOR DELIVERY TO A CREDENTIALED FURNISHER PARTNER, WHO
 * VALIDATES AGAINST THE CURRENT CRRG — never sent to bureaus directly. It
 * contains SSNs: it is stored only in a private bucket, its contents are
 * never logged, and API responses carry a redacted preview only.
 */
import { createHash, randomUUID } from "node:crypto";
import { DEMO_USERS } from "@/lib/auth";
import { env, isDemoMode } from "@/lib/env";
import { createSupabaseServiceClient } from "@/lib/supabase/server";
import type { SessionUser } from "@/lib/types";
import { getDemoCreditState } from "@/lib/demo/credit";
import { utcDay } from "./engine";
import { generateMetro2File, redactRecord, type Metro2Account, type Metro2Consumer, type Metro2ReporterProfile } from "./metro2";
import { mapLine, type CreditLineRow } from "./queries";
import { buildMetro2Account, type DisputeState } from "./reporting";
import { loadLineLedger } from "./service";

export const METRO2_BUCKET = "metro2-exports";

export interface Metro2ExportResult {
  id: string;
  periodEnd: string;
  baseRecordCount: number;
  statusCounts: Record<string, number>;
  sha256: string;
  byteLength: number;
  status: "prepared" | "delivered";
  storagePath: string | null;
  skipped: Array<{ creditLineId: string; reason: string }>;
  /** Header, first base segment and trailer with SSN/DOB masked. */
  preview: string[];
  demo: boolean;
  notice: string;
}

const NOTICE = "Prepared for delivery to a credentialed furnisher partner, who validates against the current CRRG. EzWerkz does not send files to the bureaus directly.";

/** Reporter profile: values come from the furnisher partner's onboarding. */
export function reporterProfileFromEnv(): Metro2ReporterProfile {
  const e = process.env;
  return {
    identificationNumber: e.METRO2_IDENTIFICATION_NUMBER ?? "PENDINGPARTNERID",
    innovisProgramIdentifier: e.METRO2_INNOVIS_ID ?? "",
    equifaxProgramIdentifier: e.METRO2_EQUIFAX_ID ?? "",
    experianProgramIdentifier: e.METRO2_EXPERIAN_ID ?? "",
    transUnionProgramIdentifier: e.METRO2_TRANSUNION_ID ?? "",
    reporterName: e.METRO2_REPORTER_NAME ?? "EzWerkz",
    reporterAddress: e.METRO2_REPORTER_ADDRESS ?? "Address on file with furnisher partner",
    reporterTelephone: e.METRO2_REPORTER_PHONE ?? "0000000000",
    programDate: e.METRO2_PROGRAM_DATE ?? "2026-05-01",
    programRevisionDate: e.METRO2_PROGRAM_REVISION_DATE ?? "2026-10-01",
    softwareVendorName: "EzWerkz",
    softwareVersionNumber: "1.0",
  };
}

function sha256(content: string): string {
  return createHash("sha256").update(content, "utf8").digest("hex");
}

function previewOf(records: string[]): string[] {
  const picks = records.length > 2 ? [records[0]!, records[1]!, records[records.length - 1]!] : records;
  return picks.map(redactRecord);
}

/** Synthetic identities for the demo file (666 area numbers are never issued). */
const DEMO_IDENTITIES: Record<string, Metro2Consumer> = {
  [DEMO_USERS.member.id]: { surname: "Johnson", firstName: "Maya", ssn: "666-01-0001", dateOfBirth: "1998-03-07", telephone: "4155550101", addressLine1: "742 Evergreen Ter Apt 3", city: "Oakland", state: "CA", postalCode: "94607" },
  [DEMO_USERS.worker.id]: { surname: "Carter", firstName: "Devon", ssn: "666-01-0002", dateOfBirth: "1995-11-21", telephone: "4155550102", addressLine1: "18 Harbor Way", city: "Oakland", state: "CA", postalCode: "94606" },
  [DEMO_USERS.admin.id]: { surname: "Ops", firstName: "Sample", ssn: "666-01-0004", dateOfBirth: "1990-01-01", telephone: "4155550104", addressLine1: "100 Market St", city: "San Francisco", state: "CA", postalCode: "94105" },
};

function demoExport(periodEnd: string): Metro2ExportResult {
  const users: SessionUser[] = [DEMO_USERS.member, DEMO_USERS.worker, DEMO_USERS.admin];
  const accounts: Metro2Account[] = users.map((u) => {
    const s = getDemoCreditState(u);
    return buildMetro2Account(
      {
        line: s.line!,
        accountNumber: s.line!.accountNumber,
        closedAt: s.line!.closedAt,
        closedAtConsumerRequest: s.line!.closedAtConsumerRequest,
        chargedOffAt: null,
        chargeOffAmountCents: null,
        statements: s.statements,
        payments: s.payments,
        dispute: "none",
        consumer: DEMO_IDENTITIES[u.id]!,
        firstReport: false,
      },
      periodEnd,
    );
  });
  const file = generateMetro2File({ reporter: reporterProfileFromEnv(), accounts, activityDate: new Date(utcDay(periodEnd)) });
  return {
    id: `demo-export-${periodEnd}`,
    periodEnd,
    baseRecordCount: file.baseRecordCount,
    statusCounts: file.statusCounts,
    sha256: sha256(file.content),
    byteLength: Buffer.byteLength(file.content, "utf8"),
    status: "prepared",
    storagePath: null,
    skipped: [],
    preview: previewOf(file.records),
    demo: true,
    notice: NOTICE,
  };
}

interface ProfileRow {
  user_id: string;
  legal_first_name: string;
  legal_middle_name: string | null;
  legal_last_name: string;
  generation_code: string | null;
  ssn: string | null;
  date_of_birth: string | null;
  phone_e164: string | null;
  address_line1: string;
  address_line2: string | null;
  city: string;
  state: string;
  postal_code: string;
}

interface DisputeRow {
  credit_line_id: string;
  status: "received" | "investigating" | "resolved_corrected" | "resolved_verified" | "rejected_frivolous";
  resolved_at: string | null;
}

/** FCRA dispute state for one account in the reporting period (XB while open, XH the cycle it resolves). */
export function disputeStateFor(rows: readonly DisputeRow[], periodStart: number): DisputeState {
  if (rows.some((d) => d.status === "received" || d.status === "investigating")) return "open";
  if (rows.some((d) => d.resolved_at && utcDay(d.resolved_at) >= periodStart)) return "resolved";
  return "none";
}

/** Report each closed account once more after it closes (status 13/97), then stop. */
function isReportable(line: CreditLineRow, periodStart: number): boolean {
  if (line.status === "open") return true;
  return Boolean(line.closed_at && utcDay(line.closed_at) >= periodStart);
}

/** Postgres "relation does not exist": the identity table hasn't been provisioned yet. */
const UNDEFINED_TABLE = "42P01";

export async function exportMetro2(admin: SessionUser, input: { periodEnd: string; deliver: boolean }): Promise<Metro2ExportResult> {
  if (isDemoMode()) return demoExport(input.periodEnd);

  const service = createSupabaseServiceClient();
  const periodEndDay = utcDay(input.periodEnd);
  const periodStart = periodEndDay - 31 * 86_400_000;

  const linesRes = await service.from("virtual_credit_lines").select("*").lte("opened_at", new Date(periodEndDay + 86_399_999).toISOString());
  if (linesRes.error) throw new Error(`Failed to load credit lines: ${linesRes.error.message}`);
  const lines = ((linesRes.data ?? []) as CreditLineRow[]).filter((l) => isReportable(l, periodStart));
  const userIds = lines.map((l) => l.user_id);
  const lineIds = lines.map((l) => l.id);

  const none = { data: [], error: null };
  const [profilesRes, disputesRes, membershipsRes] = await Promise.all([
    userIds.length ? service.from("credit_reporting_profiles").select("*").in("user_id", userIds) : none,
    lineIds.length ? service.from("credit_reporting_disputes").select("credit_line_id, status, resolved_at").in("credit_line_id", lineIds) : none,
    userIds.length ? service.from("membership_subscriptions").select("user_id, status").in("user_id", userIds) : none,
  ]);
  const profilesMissing = profilesRes.error?.code === UNDEFINED_TABLE;
  if (profilesRes.error && !profilesMissing) throw new Error(`Failed to load reporting profiles: ${profilesRes.error.message}`);
  if (disputesRes.error) throw new Error(`Failed to load disputes: ${disputesRes.error.message}`);
  if (membershipsRes.error) throw new Error(`Failed to load memberships: ${membershipsRes.error.message}`);
  const profiles = new Map(((profilesRes.data ?? []) as ProfileRow[]).map((p) => [p.user_id, p]));
  const disputes = (disputesRes.data ?? []) as DisputeRow[];
  const canceledMembers = new Set(
    ((membershipsRes.data ?? []) as Array<{ user_id: string; status: string }>).filter((m) => m.status === "canceled").map((m) => m.user_id),
  );

  const accounts: Metro2Account[] = [];
  const skipped: Metro2ExportResult["skipped"] = [];
  for (const row of lines) {
    const profile = profiles.get(row.user_id);
    if (!profile) {
      skipped.push({
        creditLineId: row.id,
        reason: profilesMissing ? "Reporting identities aren't set up yet (credit_reporting_profiles)" : "No identity on file for reporting",
      });
      continue;
    }
    const { statements, payments } = await loadLineLedger(service, row.id);
    const inPeriod = statements.filter((s) => utcDay(s.periodEnd) <= periodEndDay);
    if (!inPeriod.length) {
      skipped.push({ creditLineId: row.id, reason: "No statement closed yet" });
      continue;
    }
    const dispute = disputeStateFor(
      disputes.filter((d) => d.credit_line_id === row.id),
      periodStart,
    );
    const closedAtConsumerRequest = canceledMembers.has(row.user_id);
    const line = mapLine(row, closedAtConsumerRequest);
    const chargedOff = row.status === "charged_off";
    try {
      accounts.push(
        buildMetro2Account(
          {
            line,
            accountNumber: line.accountNumber,
            closedAt: chargedOff ? null : row.closed_at,
            closedAtConsumerRequest,
            // The line's closed_at marks the charge-off date; the balance then is what was charged off.
            chargedOffAt: chargedOff ? row.closed_at : null,
            chargeOffAmountCents: chargedOff ? Number(row.balance_cents) : null,
            statements: inPeriod,
            payments,
            dispute,
            consumer: {
              surname: profile.legal_last_name,
              firstName: profile.legal_first_name,
              middleName: profile.legal_middle_name,
              generationCode: profile.generation_code,
              ssn: profile.ssn,
              dateOfBirth: profile.date_of_birth,
              telephone: profile.phone_e164,
              addressLine1: profile.address_line1,
              addressLine2: profile.address_line2,
              city: profile.city,
              state: profile.state,
              postalCode: profile.postal_code,
            },
            firstReport: inPeriod.length === 1,
          },
          input.periodEnd,
        ),
      );
    } catch (err) {
      // Field errors name the field only (never the value), so this is safe to surface.
      skipped.push({ creditLineId: row.id, reason: err instanceof Error ? err.message : "Invalid data" });
    }
  }

  const file = generateMetro2File({ reporter: reporterProfileFromEnv(), accounts, activityDate: new Date(periodEndDay) });
  const id = randomUUID();
  const digest = sha256(file.content);
  const storagePath = `${input.periodEnd}/${id}.txt`;
  const upload = await service.storage.from(METRO2_BUCKET).upload(storagePath, new Blob([file.content], { type: "text/plain" }), { contentType: "text/plain", upsert: false });
  if (upload.error) throw new Error(`Failed to store Metro 2 file: ${upload.error.message}`);

  const notes = JSON.stringify({ base_records: file.baseRecordCount, status_counts: file.statusCounts, skipped: skipped.length, bytes: Buffer.byteLength(file.content, "utf8") });
  const ins = await service.from("metro2_exports").insert({
    id,
    period_end: input.periodEnd,
    record_count: file.baseRecordCount,
    file_path: `${METRO2_BUCKET}/${storagePath}`,
    file_sha256: digest,
    prepared_by: admin.id,
    notes,
  });
  if (ins.error) throw new Error(`Failed to record export: ${ins.error.message}`);

  let status: Metro2ExportResult["status"] = "prepared";
  if (input.deliver) {
    if (!env.furnisherApiUrl || !env.furnisherApiKey) throw new Error("Furnisher partner API is not configured (FURNISHER_API_URL / FURNISHER_API_KEY)");
    const res = await fetch(env.furnisherApiUrl, {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.furnisherApiKey}`,
        "content-type": "text/plain; charset=utf-8",
        "x-metro2-period-end": input.periodEnd,
        "x-content-sha256": digest,
        "idempotency-key": id,
      },
      body: file.content,
    });
    if (!res.ok) {
      await service.from("metro2_exports").update({ status: "rejected", notes: `${notes} partner_http_${res.status}` }).eq("id", id);
      throw new Error(`Furnisher partner rejected the file (HTTP ${res.status})`);
    }
    const reference = res.headers.get("x-furnisher-reference") ?? res.headers.get("x-request-id");
    const upd = await service.from("metro2_exports").update({ status: "delivered", furnisher_reference: reference }).eq("id", id);
    if (upd.error) throw new Error(`Delivered, but failed to update the export record: ${upd.error.message}`);
    status = "delivered";
  }

  return {
    id,
    periodEnd: input.periodEnd,
    baseRecordCount: file.baseRecordCount,
    statusCounts: file.statusCounts,
    sha256: digest,
    byteLength: Buffer.byteLength(file.content, "utf8"),
    status,
    storagePath,
    skipped,
    preview: previewOf(file.records),
    demo: false,
    notice: NOTICE,
  };
}
