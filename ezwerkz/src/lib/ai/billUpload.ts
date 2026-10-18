/**
 * Upload validation for the AI Bill Negotiator. Pure (no I/O) so the route
 * handler and tests share it. The declared MIME type is never trusted on its
 * own: the file's magic bytes must agree with it.
 */

export const BILL_MEDIA_TYPES = ["image/png", "image/jpeg", "image/webp", "application/pdf"] as const;
export type BillMediaType = (typeof BILL_MEDIA_TYPES)[number];

export const BILL_MAX_BYTES = 10 * 1024 * 1024;

export const BILL_ACCEPT_ATTR = BILL_MEDIA_TYPES.join(",");

export function isBillMediaType(value: string): value is BillMediaType {
  return (BILL_MEDIA_TYPES as readonly string[]).includes(value);
}

function startsWith(bytes: Uint8Array, sig: readonly number[], offset = 0): boolean {
  if (bytes.length < offset + sig.length) return false;
  return sig.every((b, i) => bytes[offset + i] === b);
}

/** Identify a supported file from its first bytes. */
export function sniffBillMediaType(bytes: Uint8Array): BillMediaType | null {
  if (startsWith(bytes, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (startsWith(bytes, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (startsWith(bytes, [0x52, 0x49, 0x46, 0x46]) && startsWith(bytes, [0x57, 0x45, 0x42, 0x50], 8)) return "image/webp";
  if (startsWith(bytes, [0x25, 0x50, 0x44, 0x46, 0x2d])) return "application/pdf"; // %PDF-
  return null;
}

export type BillUploadError = "MISSING_FILE" | "EMPTY_FILE" | "UNSUPPORTED_TYPE" | "TOO_LARGE" | "TYPE_MISMATCH";

export const BILL_UPLOAD_MESSAGES: Record<BillUploadError, string> = {
  MISSING_FILE: "Choose a bill to upload.",
  EMPTY_FILE: "That file is empty.",
  UNSUPPORTED_TYPE: "Upload a PNG, JPEG or WebP photo, or a PDF.",
  TOO_LARGE: "Files must be 10 MB or smaller.",
  TYPE_MISMATCH: "That file's contents don't match its type. Try exporting it again as a PDF or JPEG.",
};

export function validateBillUpload(input: {
  declaredType: string;
  size: number;
  head: Uint8Array;
}): { ok: true; mediaType: BillMediaType } | { ok: false; error: BillUploadError; message: string } {
  const fail = (error: BillUploadError) => ({ ok: false as const, error, message: BILL_UPLOAD_MESSAGES[error] });
  if (input.size <= 0) return fail("EMPTY_FILE");
  if (input.size > BILL_MAX_BYTES) return fail("TOO_LARGE");
  const declared = input.declaredType.toLowerCase().split(";")[0]!.trim();
  if (!isBillMediaType(declared)) return fail("UNSUPPORTED_TYPE");
  const sniffed = sniffBillMediaType(input.head);
  if (sniffed !== declared) return fail("TYPE_MISMATCH");
  return { ok: true, mediaType: declared };
}

export function extensionFor(mediaType: BillMediaType): string {
  switch (mediaType) {
    case "image/png":
      return "png";
    case "image/jpeg":
      return "jpg";
    case "image/webp":
      return "webp";
    case "application/pdf":
      return "pdf";
  }
}
