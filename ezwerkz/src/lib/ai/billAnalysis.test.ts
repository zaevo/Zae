import { describe, expect, it } from "vitest";
import { finalizeBillAnalysis, isDishonestLine, mockBillAnalysis, type BillAnalysisModelOutput } from "./billAnalysis";
import { BILL_MAX_BYTES, sniffBillMediaType, validateBillUpload } from "./billUpload";

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0x10]);
const WEBP = new Uint8Array([0x52, 0x49, 0x46, 0x46, 1, 2, 3, 4, 0x57, 0x45, 0x42, 0x50]);
const PDF = new TextEncoder().encode("%PDF-1.7\n");
const GIF = new TextEncoder().encode("GIF89a");

describe("bill upload validation", () => {
  it("sniffs supported types from magic bytes", () => {
    expect(sniffBillMediaType(PNG)).toBe("image/png");
    expect(sniffBillMediaType(JPEG)).toBe("image/jpeg");
    expect(sniffBillMediaType(WEBP)).toBe("image/webp");
    expect(sniffBillMediaType(PDF)).toBe("application/pdf");
    expect(sniffBillMediaType(GIF)).toBeNull();
    expect(sniffBillMediaType(new Uint8Array())).toBeNull();
  });

  it("accepts matching type and size", () => {
    expect(validateBillUpload({ declaredType: "application/pdf", size: 1000, head: PDF })).toEqual({ ok: true, mediaType: "application/pdf" });
    expect(validateBillUpload({ declaredType: "IMAGE/JPEG", size: BILL_MAX_BYTES, head: JPEG })).toEqual({ ok: true, mediaType: "image/jpeg" });
  });

  it("rejects oversize, empty, unsupported and mismatched files", () => {
    expect(validateBillUpload({ declaredType: "image/png", size: BILL_MAX_BYTES + 1, head: PNG })).toMatchObject({ ok: false, error: "TOO_LARGE" });
    expect(validateBillUpload({ declaredType: "image/png", size: 0, head: PNG })).toMatchObject({ ok: false, error: "EMPTY_FILE" });
    expect(validateBillUpload({ declaredType: "image/gif", size: 10, head: GIF })).toMatchObject({ ok: false, error: "UNSUPPORTED_TYPE" });
    expect(validateBillUpload({ declaredType: "image/heic", size: 10, head: JPEG })).toMatchObject({ ok: false, error: "UNSUPPORTED_TYPE" });
    expect(validateBillUpload({ declaredType: "application/pdf", size: 10, head: PNG })).toMatchObject({ ok: false, error: "TYPE_MISMATCH" });
  });
});

function raw(overrides: Partial<BillAnalysisModelOutput> = {}): BillAnalysisModelOutput {
  return {
    isBill: true,
    provider: "Acme Power",
    category: "electric",
    billingPeriodStart: "2026-09-01",
    billingPeriodEnd: "2026-09-30",
    totalDueCents: 100_00,
    lineItems: [],
    flaggedIssues: [
      {
        kind: "junk_fee",
        title: "Fee",
        evidence: "Convenience fee $3.00",
        explanation: "",
        estimatedMonthlySavingsCents: 3_00,
        oneTimeCreditCents: 0,
        confidence: "high",
        suggestedAsk: "",
      },
      {
        kind: "billing_error",
        title: "Wild guess",
        evidence: "Usage charge",
        explanation: "",
        estimatedMonthlySavingsCents: 500_00,
        oneTimeCreditCents: -20,
        confidence: "low",
        suggestedAsk: "",
      },
      {
        kind: "other",
        title: "No evidence",
        evidence: "   ",
        explanation: "",
        estimatedMonthlySavingsCents: 10_00,
        oneTimeCreditCents: 0,
        confidence: "low",
        suggestedAsk: "",
      },
    ],
    negotiationScript: {
      opening: "Hi, I'm calling on behalf of my client.",
      talkingPoints: ["Please remove the convenience fee.", "If you don't, I'll sue."],
      ifTheySayNo: ["Could I speak with the retention team?", "I will report you to the regulator."],
      closing: "Thanks for your help.",
    },
    letterDraft: { subject: "Charges", body: "Hello,\nPlease review my bill.\nMy lawyer will be in touch.\n[Your name]" },
    questionsToAsk: ["Why did my rate go up?"],
    summary: "",
    ...overrides,
  };
}

describe("finalizeBillAnalysis", () => {
  it("drops issues without evidence and caps savings at the bill total", () => {
    const a = finalizeBillAnalysis(raw(), { id: "a", source: "claude", model: "claude-opus-5-5", fileName: "bill.pdf" });
    expect(a.flaggedIssues).toHaveLength(2);
    expect(a.flaggedIssues[1]!.estimatedMonthlySavingsCents).toBe(100_00);
    expect(a.flaggedIssues[1]!.oneTimeCreditCents).toBe(0);
    expect(a.estimatedMonthlySavingsCents).toBe(100_00);
    expect(a.estimatedAnnualSavingsCents).toBe(1_200_00);
    expect(a.id).toBe("a");
  });

  it("strips threats and impersonation from scripts and letters", () => {
    const a = finalizeBillAnalysis(raw(), { id: "a", source: "claude", model: null, fileName: null });
    expect(a.negotiationScript.opening).toMatch(/I'm the account holder/);
    expect(a.negotiationScript.talkingPoints).toEqual(["Please remove the convenience fee."]);
    expect(a.negotiationScript.ifTheySayNo).toEqual(["Could I speak with the retention team?"]);
    expect(a.letterDraft.body).not.toMatch(/lawyer/i);
    expect(isDishonestLine("I'm calling from EzWerkz about this account")).toBe(true);
    expect(isDishonestLine("Could you waive the late fee as a courtesy?")).toBe(false);
  });

  it("returns no issues for non-bills", () => {
    const a = finalizeBillAnalysis(raw({ isBill: false }), { id: "a", source: "claude", model: null, fileName: null });
    expect(a.flaggedIssues).toEqual([]);
    expect(a.estimatedMonthlySavingsCents).toBe(0);
  });
});

describe("mockBillAnalysis", () => {
  it("is internally consistent and honest", () => {
    const m = mockBillAnalysis({ id: "demo", fileName: "bill.jpg" });
    expect(m.source).toBe("demo");
    expect(m.lineItems.reduce((n, l) => n + l.amountCents, 0)).toBe(m.totalDueCents);
    expect(m.estimatedMonthlySavingsCents).toBe(m.flaggedIssues.reduce((n, i) => n + i.estimatedMonthlySavingsCents, 0));
    expect(m.flaggedIssues.length).toBeGreaterThan(0);
    for (const i of m.flaggedIssues) expect(i.evidence.length).toBeGreaterThan(0);
    const allScript = [m.negotiationScript.opening, ...m.negotiationScript.talkingPoints, ...m.negotiationScript.ifTheySayNo, m.negotiationScript.closing, m.letterDraft.body];
    for (const line of allScript) expect(isDishonestLine(line)).toBe(false);
  });
});
