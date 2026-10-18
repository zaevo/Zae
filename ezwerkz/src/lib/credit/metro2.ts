/**
 * Metro 2(R) character-format (426-byte) file generator.
 *
 * PREPARED FOR DELIVERY TO A CREDENTIALED FURNISHER PARTNER, WHO VALIDATES
 * AGAINST THE CURRENT CRRG. EzWerkz never transmits these files to the
 * consumer reporting agencies itself (SPEC §2 rule 6): the partner holds the
 * bureau subscriber codes, re-validates every field against the current
 * Credit Reporting Resource Guide (CRRG), and owns delivery.
 *
 * The layouts below follow the 426-character fixed-length record format:
 * one Header record, one Base Segment per account, one Trailer record.
 * Every field is generated from the position tables, so the tables are the
 * single source of truth for positions, lengths and padding:
 *   - N    numeric: right-justified, zero-filled
 *   - AN   alphanumeric: left-justified, space-filled, upper-cased
 *   - DATE MMDDYYYY, zero-filled when not applicable
 *   - TS   MMDDYYYYHHMMSS (UTC)
 * Monetary fields are whole dollars.
 *
 * SSNs and dates of birth are accepted as input but never logged: errors name
 * the field and the reason only, never the value.
 */

export const RECORD_LENGTH = 426;

export type Metro2FieldType = "N" | "AN" | "DATE" | "TS";

export interface Metro2FieldSpec {
  /** CRRG field number (e.g. "17A"). */
  readonly field: string;
  readonly name: string;
  /** 1-based starting position. */
  readonly start: number;
  readonly length: number;
  readonly type: Metro2FieldType;
  /** Fixed value written regardless of input. */
  readonly constant?: string | number;
  /** Reject (instead of truncate) values longer than the field. */
  readonly strict?: boolean;
  /** Personal data that must never be logged or displayed unmasked. */
  readonly sensitive?: boolean;
}

export const HEADER_FIELDS = [
  { field: "1", name: "recordDescriptorWord", start: 1, length: 4, type: "N", constant: RECORD_LENGTH },
  { field: "2", name: "recordIdentifier", start: 5, length: 6, type: "AN", constant: "HEADER" },
  { field: "3", name: "cycleIdentifier", start: 11, length: 2, type: "AN" },
  { field: "4", name: "innovisProgramIdentifier", start: 13, length: 10, type: "AN", strict: true },
  { field: "5", name: "equifaxProgramIdentifier", start: 23, length: 10, type: "AN", strict: true },
  { field: "6", name: "experianProgramIdentifier", start: 33, length: 5, type: "AN", strict: true },
  { field: "7", name: "transUnionProgramIdentifier", start: 38, length: 10, type: "AN", strict: true },
  { field: "8", name: "activityDate", start: 48, length: 8, type: "DATE" },
  { field: "9", name: "dateCreated", start: 56, length: 8, type: "DATE" },
  { field: "10", name: "programDate", start: 64, length: 8, type: "DATE" },
  { field: "11", name: "programRevisionDate", start: 72, length: 8, type: "DATE" },
  { field: "12", name: "reporterName", start: 80, length: 40, type: "AN" },
  { field: "13", name: "reporterAddress", start: 120, length: 96, type: "AN" },
  { field: "14", name: "reporterTelephoneNumber", start: 216, length: 10, type: "N" },
  { field: "15", name: "softwareVendorName", start: 226, length: 40, type: "AN" },
  { field: "16", name: "softwareVersionNumber", start: 266, length: 5, type: "AN" },
  { field: "17", name: "prbcProgramIdentifier", start: 271, length: 10, type: "AN" },
  { field: "18", name: "reserved", start: 281, length: 146, type: "AN" },
] as const satisfies readonly Metro2FieldSpec[];

export const BASE_SEGMENT_FIELDS = [
  { field: "1", name: "recordDescriptorWord", start: 1, length: 4, type: "N", constant: RECORD_LENGTH },
  { field: "2", name: "processingIndicator", start: 5, length: 1, type: "N", constant: 1 },
  { field: "3", name: "timeStamp", start: 6, length: 14, type: "TS" },
  { field: "4", name: "reserved1", start: 20, length: 1, type: "N" },
  { field: "5", name: "identificationNumber", start: 21, length: 20, type: "AN", strict: true },
  { field: "6", name: "cycleIdentifier", start: 41, length: 2, type: "AN" },
  { field: "7", name: "consumerAccountNumber", start: 43, length: 30, type: "AN", strict: true },
  { field: "8", name: "portfolioType", start: 73, length: 1, type: "AN", strict: true },
  { field: "9", name: "accountType", start: 74, length: 2, type: "AN", strict: true },
  { field: "10", name: "dateOpened", start: 76, length: 8, type: "DATE" },
  { field: "11", name: "creditLimit", start: 84, length: 9, type: "N" },
  { field: "12", name: "highestCredit", start: 93, length: 9, type: "N" },
  { field: "13", name: "termsDuration", start: 102, length: 3, type: "AN", strict: true },
  { field: "14", name: "termsFrequency", start: 105, length: 1, type: "AN", strict: true },
  { field: "15", name: "scheduledMonthlyPaymentAmount", start: 106, length: 9, type: "N" },
  { field: "16", name: "actualPaymentAmount", start: 115, length: 9, type: "N" },
  { field: "17A", name: "accountStatus", start: 124, length: 2, type: "AN", strict: true },
  { field: "17B", name: "paymentRating", start: 126, length: 1, type: "AN", strict: true },
  { field: "18", name: "paymentHistoryProfile", start: 127, length: 24, type: "AN", strict: true },
  { field: "19", name: "specialComment", start: 151, length: 2, type: "AN", strict: true },
  { field: "20", name: "complianceConditionCode", start: 153, length: 2, type: "AN", strict: true },
  { field: "21", name: "currentBalance", start: 155, length: 9, type: "N" },
  { field: "22", name: "amountPastDue", start: 164, length: 9, type: "N" },
  { field: "23", name: "originalChargeOffAmount", start: 173, length: 9, type: "N" },
  { field: "24", name: "dateOfAccountInformation", start: 182, length: 8, type: "DATE" },
  { field: "25", name: "dateOfFirstDelinquency", start: 190, length: 8, type: "DATE" },
  { field: "26", name: "dateClosed", start: 198, length: 8, type: "DATE" },
  { field: "27", name: "dateOfLastPayment", start: 206, length: 8, type: "DATE" },
  { field: "28", name: "interestTypeIndicator", start: 214, length: 1, type: "AN", strict: true },
  { field: "29", name: "reserved2", start: 215, length: 16, type: "AN" },
  { field: "30", name: "consumerTransactionType", start: 231, length: 1, type: "AN", strict: true },
  { field: "31", name: "surname", start: 232, length: 25, type: "AN" },
  { field: "32", name: "firstName", start: 257, length: 20, type: "AN" },
  { field: "33", name: "middleName", start: 277, length: 20, type: "AN" },
  { field: "34", name: "generationCode", start: 297, length: 1, type: "AN", strict: true },
  { field: "35", name: "socialSecurityNumber", start: 298, length: 9, type: "N", strict: true, sensitive: true },
  { field: "36", name: "dateOfBirth", start: 307, length: 8, type: "DATE", sensitive: true },
  { field: "37", name: "telephoneNumber", start: 315, length: 10, type: "N", strict: true },
  { field: "38", name: "ecoaCode", start: 325, length: 1, type: "AN", strict: true },
  { field: "39", name: "consumerInformationIndicator", start: 326, length: 2, type: "AN", strict: true },
  { field: "40", name: "countryCode", start: 328, length: 2, type: "AN", strict: true },
  { field: "41", name: "firstLineOfAddress", start: 330, length: 32, type: "AN" },
  { field: "42", name: "secondLineOfAddress", start: 362, length: 32, type: "AN" },
  { field: "43", name: "city", start: 394, length: 20, type: "AN" },
  { field: "44", name: "state", start: 414, length: 2, type: "AN", strict: true },
  { field: "45", name: "postalCode", start: 416, length: 9, type: "AN", strict: true },
  { field: "46", name: "addressIndicator", start: 425, length: 1, type: "AN", strict: true },
  { field: "47", name: "residenceCode", start: 426, length: 1, type: "AN", strict: true },
] as const satisfies readonly Metro2FieldSpec[];

export const TRAILER_FIELDS = [
  { field: "1", name: "recordDescriptorWord", start: 1, length: 4, type: "N", constant: RECORD_LENGTH },
  { field: "2", name: "recordIdentifier", start: 5, length: 7, type: "AN", constant: "TRAILER" },
  { field: "3", name: "totalBaseRecords", start: 12, length: 9, type: "N" },
  { field: "4", name: "reserved1", start: 21, length: 9, type: "N" },
  { field: "5", name: "totalStatusCodeDF", start: 30, length: 9, type: "N" },
  { field: "6", name: "totalConsumerSegmentsJ1", start: 39, length: 9, type: "N" },
  { field: "7", name: "totalConsumerSegmentsJ2", start: 48, length: 9, type: "N" },
  { field: "8", name: "blockCount", start: 57, length: 9, type: "N" },
  { field: "9", name: "totalStatusCodeDA", start: 66, length: 9, type: "N" },
  { field: "10", name: "totalStatusCode05", start: 75, length: 9, type: "N" },
  { field: "11", name: "totalStatusCode11", start: 84, length: 9, type: "N" },
  { field: "12", name: "totalStatusCode13", start: 93, length: 9, type: "N" },
  { field: "13", name: "totalStatusCode61", start: 102, length: 9, type: "N" },
  { field: "14", name: "totalStatusCode62", start: 111, length: 9, type: "N" },
  { field: "15", name: "totalStatusCode63", start: 120, length: 9, type: "N" },
  { field: "16", name: "totalStatusCode64", start: 129, length: 9, type: "N" },
  { field: "17", name: "totalStatusCode65", start: 138, length: 9, type: "N" },
  { field: "18", name: "totalStatusCode71", start: 147, length: 9, type: "N" },
  { field: "19", name: "totalStatusCode78", start: 156, length: 9, type: "N" },
  { field: "20", name: "totalStatusCode80", start: 165, length: 9, type: "N" },
  { field: "21", name: "totalStatusCode82", start: 174, length: 9, type: "N" },
  { field: "22", name: "totalStatusCode83", start: 183, length: 9, type: "N" },
  { field: "23", name: "totalStatusCode84", start: 192, length: 9, type: "N" },
  { field: "24", name: "totalStatusCode88", start: 201, length: 9, type: "N" },
  { field: "25", name: "totalStatusCode89", start: 210, length: 9, type: "N" },
  { field: "26", name: "totalStatusCode93", start: 219, length: 9, type: "N" },
  { field: "27", name: "totalStatusCode94", start: 228, length: 9, type: "N" },
  { field: "28", name: "totalStatusCode95", start: 237, length: 9, type: "N" },
  { field: "29", name: "totalStatusCode96", start: 246, length: 9, type: "N" },
  { field: "30", name: "totalStatusCode97", start: 255, length: 9, type: "N" },
  { field: "31", name: "totalEcoaCodeZ", start: 264, length: 9, type: "N" },
  { field: "32", name: "totalEmploymentSegments", start: 273, length: 9, type: "N" },
  { field: "33", name: "totalOriginalCreditorSegments", start: 282, length: 9, type: "N" },
  { field: "34", name: "totalPurchasedToSoldToSegments", start: 291, length: 9, type: "N" },
  { field: "35", name: "totalMortgageInformationSegments", start: 300, length: 9, type: "N" },
  { field: "36", name: "totalSpecializedPaymentInformationSegments", start: 309, length: 9, type: "N" },
  { field: "37", name: "totalChangeSegments", start: 318, length: 9, type: "N" },
  { field: "38", name: "totalSocialSecurityNumbersAllSegments", start: 327, length: 9, type: "N" },
  { field: "39", name: "totalSocialSecurityNumbersBaseSegments", start: 336, length: 9, type: "N" },
  { field: "40", name: "totalSocialSecurityNumbersJ1Segments", start: 345, length: 9, type: "N" },
  { field: "41", name: "totalSocialSecurityNumbersJ2Segments", start: 354, length: 9, type: "N" },
  { field: "42", name: "totalDatesOfBirthAllSegments", start: 363, length: 9, type: "N" },
  { field: "43", name: "totalDatesOfBirthBaseSegments", start: 372, length: 9, type: "N" },
  { field: "44", name: "totalDatesOfBirthJ1Segments", start: 381, length: 9, type: "N" },
  { field: "45", name: "totalDatesOfBirthJ2Segments", start: 390, length: 9, type: "N" },
  { field: "46", name: "totalTelephoneNumbersAllSegments", start: 399, length: 9, type: "N" },
  { field: "47", name: "reserved2", start: 408, length: 19, type: "AN" },
] as const satisfies readonly Metro2FieldSpec[];

/* ------------------------------------------------------------------ */
/* Codes                                                               */
/* ------------------------------------------------------------------ */

/** Account Status (field 17A) codes this generator emits or counts. */
export const ACCOUNT_STATUS = {
  transferred: "05",
  current: "11",
  paidOrClosedZeroBalance: "13",
  paidInFullWasCollection: "61",
  paidInFullWasChargeOff: "62",
  paidSettledWasCollection: "63",
  paidSettledWasChargeOff: "64",
  paidInFullForeclosureStarted: "65",
  pastDue30to59: "71",
  pastDue60to89: "78",
  pastDue90to119: "80",
  pastDue120to149: "82",
  pastDue150to179: "83",
  pastDue180Plus: "84",
  insuranceClaim: "88",
  deedInLieu: "89",
  collections: "93",
  foreclosureCompleted: "94",
  voluntarySurrender: "95",
  repossession: "96",
  chargeOff: "97",
  deleteAccount: "DA",
  deleteFraud: "DF",
} as const;

export type Metro2AccountStatus = (typeof ACCOUNT_STATUS)[keyof typeof ACCOUNT_STATUS];

/** Payment History Profile (field 18) characters. */
export type PaymentHistoryCode =
  | "0" // current (0-29 days past due)
  | "1" // 30-59 days past due
  | "2" // 60-89
  | "3" // 90-119
  | "4" // 120-149
  | "5" // 150-179
  | "6" // 180+
  | "B" // no history prior to this time (account not yet open)
  | "D" // no history reported this month
  | "E" // zero balance and current
  | "G" // collection
  | "H" // foreclosure completed
  | "J" // voluntary surrender
  | "K" // repossession
  | "L"; // charge-off

const HISTORY_CODES = new Set<string>(["0", "1", "2", "3", "4", "5", "6", "B", "D", "E", "G", "H", "J", "K", "L"]);

/** Compliance Condition Codes (field 20) relevant to a consumer line of credit. */
export const COMPLIANCE_CONDITION = {
  closedAtConsumerRequest: "XA",
  disputedFcra: "XB",
  disputeResolvedConsumerDisagrees: "XC",
  closedAtConsumerRequestDisputed: "XD",
  disputeResolved: "XH",
  removePrevious: "XR",
} as const;

export type ComplianceConditionCode = (typeof COMPLIANCE_CONDITION)[keyof typeof COMPLIANCE_CONDITION];

/** Statuses that carry a Payment Rating (17B); all others leave it blank. */
const STATUSES_WITH_PAYMENT_RATING = new Set<string>(["05", "13", "65", "88", "89", "94", "95"]);

/** Delinquency bucket for a number of days past due: 0 (current) … 6 (180+). */
export function delinquencyBucket(daysPastDue: number): 0 | 1 | 2 | 3 | 4 | 5 | 6 {
  if (!Number.isFinite(daysPastDue) || daysPastDue < 30) return 0;
  if (daysPastDue < 60) return 1;
  if (daysPastDue < 90) return 2;
  if (daysPastDue < 120) return 3;
  if (daysPastDue < 150) return 4;
  if (daysPastDue < 180) return 5;
  return 6;
}

export interface AccountStatusInput {
  daysPastDue: number;
  balanceCents: number;
  closed: boolean;
  chargedOff: boolean;
}

/**
 * Account Status for the reporting month: 97 charge-off, 13 closed/paid with
 * zero balance, otherwise 11 current or the 71–84 delinquency ladder.
 */
export function accountStatusFor(input: AccountStatusInput): Metro2AccountStatus {
  if (input.chargedOff) return ACCOUNT_STATUS.chargeOff;
  if (input.closed && input.balanceCents <= 0) return ACCOUNT_STATUS.paidOrClosedZeroBalance;
  switch (delinquencyBucket(input.daysPastDue)) {
    case 0:
      return ACCOUNT_STATUS.current;
    case 1:
      return ACCOUNT_STATUS.pastDue30to59;
    case 2:
      return ACCOUNT_STATUS.pastDue60to89;
    case 3:
      return ACCOUNT_STATUS.pastDue90to119;
    case 4:
      return ACCOUNT_STATUS.pastDue120to149;
    case 5:
      return ACCOUNT_STATUS.pastDue150to179;
    default:
      return ACCOUNT_STATUS.pastDue180Plus;
  }
}

/**
 * Payment Rating (17B): only for statuses that need it (e.g. 13), giving the
 * account's standing at the time of that status. Blank otherwise.
 */
export function paymentRatingFor(status: Metro2AccountStatus, daysPastDueAtStatus: number, chargedOff = false): string {
  if (!STATUSES_WITH_PAYMENT_RATING.has(status)) return "";
  if (chargedOff) return "L";
  return String(delinquencyBucket(daysPastDueAtStatus));
}

export interface HistoryMonthInput {
  daysPastDue: number;
  balanceCents: number;
  chargedOff?: boolean;
}

/** The Payment History Profile character for one month's standing. */
export function paymentHistoryCodeFor(month: HistoryMonthInput): PaymentHistoryCode {
  if (month.chargedOff) return "L";
  const bucket = delinquencyBucket(month.daysPastDue);
  if (bucket === 0) return month.balanceCents <= 0 ? "E" : "0";
  return String(bucket) as PaymentHistoryCode;
}

/** "YYYY-MM" for a date (UTC). */
export function monthKey(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function addMonths(key: string, delta: number): string {
  const [y, m] = key.split("-").map(Number) as [number, number];
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return monthKey(d);
}

/**
 * Build the 24-character Payment History Profile. Position 1 is the month
 * immediately before the Date of Account Information month, moving back one
 * month per position. Months before the account opened are "B"; open months
 * with no data are "D".
 */
export function buildPaymentHistoryProfile(input: {
  dateOfAccountInformation: Date;
  dateOpened: Date;
  months: Readonly<Record<string, PaymentHistoryCode>>;
}): string {
  const reportMonth = monthKey(input.dateOfAccountInformation);
  const openedMonth = monthKey(input.dateOpened);
  let profile = "";
  for (let i = 1; i <= 24; i++) {
    const key = addMonths(reportMonth, -i);
    if (key < openedMonth) profile += "B";
    else profile += input.months[key] ?? "D";
  }
  return profile;
}

/* ------------------------------------------------------------------ */
/* Field formatting                                                    */
/* ------------------------------------------------------------------ */

export class Metro2FieldError extends Error {
  constructor(
    public readonly fieldName: string,
    reason: string,
  ) {
    // Never include the offending value: it may be an SSN or a date of birth.
    super(`Metro 2 field ${fieldName}: ${reason}`);
    this.name = "Metro2FieldError";
  }
}

export type Metro2Value = string | number | Date | null | undefined;

const AN_ALLOWED = /[^A-Z0-9 \-/&'.,#]/g;

/** Upper-case, strip diacritics and characters outside the Metro 2 alphanumeric set. */
export function sanitizeAlphanumeric(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toUpperCase()
    .replace(AN_ALLOWED, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toDate(spec: Metro2FieldSpec, value: Metro2Value): Date | null {
  if (value === null || value === undefined || value === "") return null;
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) throw new Metro2FieldError(spec.name, "invalid date");
    return value;
  }
  if (typeof value === "string") {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
    const d = m ? new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))) : new Date(value);
    if (Number.isNaN(d.getTime())) throw new Metro2FieldError(spec.name, "invalid date");
    return d;
  }
  throw new Metro2FieldError(spec.name, "expected a date");
}

/** Format one value for its field spec: exact length, correct justification and fill. */
export function formatField(spec: Metro2FieldSpec, raw: Metro2Value): string {
  const value = spec.constant ?? raw;
  switch (spec.type) {
    case "N": {
      if (value === null || value === undefined || value === "") return "0".repeat(spec.length);
      let digits: string;
      if (typeof value === "number") {
        if (!Number.isInteger(value)) throw new Metro2FieldError(spec.name, "numeric value must be an integer");
        if (value < 0) throw new Metro2FieldError(spec.name, "numeric value cannot be negative");
        digits = String(value);
      } else if (typeof value === "string") {
        digits = value.replace(/[\s()+-]/g, "");
        if (!/^\d+$/.test(digits)) throw new Metro2FieldError(spec.name, "expected digits only");
      } else {
        throw new Metro2FieldError(spec.name, "expected a number");
      }
      if (digits.length > spec.length) throw new Metro2FieldError(spec.name, `exceeds ${spec.length} digits`);
      return digits.padStart(spec.length, "0");
    }
    case "AN": {
      if (value === null || value === undefined) return " ".repeat(spec.length);
      if (typeof value !== "string" && typeof value !== "number") throw new Metro2FieldError(spec.name, "expected text");
      const text = sanitizeAlphanumeric(String(value));
      if (text.length > spec.length) {
        if (spec.strict) throw new Metro2FieldError(spec.name, `exceeds ${spec.length} characters`);
        return text.slice(0, spec.length);
      }
      return text.padEnd(spec.length, " ");
    }
    case "DATE": {
      const d = toDate(spec, value);
      if (!d) return "0".repeat(spec.length);
      return `${pad2(d.getUTCMonth() + 1)}${pad2(d.getUTCDate())}${d.getUTCFullYear()}`;
    }
    case "TS": {
      const d = toDate(spec, value);
      if (!d) return "0".repeat(spec.length);
      return (
        `${pad2(d.getUTCMonth() + 1)}${pad2(d.getUTCDate())}${d.getUTCFullYear()}` +
        `${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}${pad2(d.getUTCSeconds())}`
      );
    }
  }
}

type FieldNames<T extends readonly Metro2FieldSpec[]> = T[number]["name"];
export type Metro2Values<T extends readonly Metro2FieldSpec[]> = Partial<Record<FieldNames<T>, Metro2Value>>;

/** Throws if a layout table has gaps, overlaps, or does not total 426 bytes. */
export function assertLayout(fields: readonly Metro2FieldSpec[]): void {
  let next = 1;
  for (const f of fields) {
    if (f.start !== next) throw new Error(`Metro 2 layout gap/overlap at ${f.name} (expected start ${next}, got ${f.start})`);
    next += f.length;
  }
  if (next - 1 !== RECORD_LENGTH) throw new Error(`Metro 2 layout totals ${next - 1} bytes, expected ${RECORD_LENGTH}`);
}

assertLayout(HEADER_FIELDS);
assertLayout(BASE_SEGMENT_FIELDS);
assertLayout(TRAILER_FIELDS);

/** Build one fixed-width record from a layout table. */
export function buildRecord<T extends readonly Metro2FieldSpec[]>(fields: T, values: Metro2Values<T>): string {
  const vals = values as Record<string, Metro2Value>;
  let out = "";
  for (const f of fields) {
    const piece = formatField(f, vals[f.name]);
    if (piece.length !== f.length) throw new Metro2FieldError(f.name, "formatted length mismatch");
    out += piece;
  }
  if (out.length !== RECORD_LENGTH) throw new Error(`Metro 2 record is ${out.length} bytes, expected ${RECORD_LENGTH}`);
  return out;
}

/** Split a record back into raw field strings (for validation, tests and redacted previews). */
export function parseRecord<T extends readonly Metro2FieldSpec[]>(fields: T, record: string): Record<FieldNames<T>, string> {
  if (record.length !== RECORD_LENGTH) throw new Error(`Metro 2 record is ${record.length} bytes, expected ${RECORD_LENGTH}`);
  const out: Record<string, string> = {};
  for (const f of fields) out[f.name] = record.slice(f.start - 1, f.start - 1 + f.length);
  return out as Record<FieldNames<T>, string>;
}

/* ------------------------------------------------------------------ */
/* Domain input                                                        */
/* ------------------------------------------------------------------ */

export interface Metro2ReporterProfile {
  /** Data-furnisher identification number assigned by the bureaus (via the partner). */
  identificationNumber: string;
  innovisProgramIdentifier?: string;
  equifaxProgramIdentifier?: string;
  experianProgramIdentifier?: string;
  transUnionProgramIdentifier?: string;
  reporterName: string;
  reporterAddress: string;
  reporterTelephone: string;
  /** Date the furnisher first reported in Metro 2. */
  programDate: Date | string;
  /** Date the reporting program was last revised. */
  programRevisionDate: Date | string;
  softwareVendorName: string;
  softwareVersionNumber: string;
}

export interface Metro2Consumer {
  surname: string;
  firstName: string;
  middleName?: string | null;
  /** J, S, 2–9, or blank. */
  generationCode?: string | null;
  /** 9 digits; dashes/spaces allowed. Never logged. */
  ssn?: string | null;
  dateOfBirth?: Date | string | null;
  /** 10-digit US number; E.164 "+1…" accepted. */
  telephone?: string | null;
  /** 1 individual, 2 joint, 3 authorized user, … Defaults to 1. */
  ecoaCode?: string;
  consumerInformationIndicator?: string | null;
  countryCode?: string;
  addressLine1: string;
  addressLine2?: string | null;
  city: string;
  state: string;
  postalCode: string;
  addressIndicator?: string | null;
  residenceCode?: string | null;
}

export interface Metro2Account {
  consumerAccountNumber: string;
  /** C line of credit, I installment, M mortgage, O open, R revolving. */
  portfolioType: "C" | "I" | "M" | "O" | "R";
  accountType: string;
  dateOpened: Date | string;
  creditLimitCents: number;
  highestCreditCents: number;
  termsDuration: string;
  termsFrequency: string;
  scheduledMonthlyPaymentCents: number;
  actualPaymentCents: number;
  accountStatus: Metro2AccountStatus;
  paymentRating?: string;
  paymentHistoryProfile: string;
  specialComment?: string;
  complianceConditionCode?: ComplianceConditionCode | "";
  currentBalanceCents: number;
  amountPastDueCents: number;
  originalChargeOffCents?: number;
  dateOfAccountInformation: Date | string;
  dateOfFirstDelinquency?: Date | string | null;
  dateClosed?: Date | string | null;
  dateOfLastPayment?: Date | string | null;
  interestTypeIndicator?: "" | "F" | "V";
  consumerTransactionType?: string;
  consumer: Metro2Consumer;
}

/**
 * Metro 2 amounts are whole dollars. Round half-up, but never report a
 * non-zero amount as $0 — a $0.40 balance is still a balance.
 */
export function centsToWholeDollars(cents: number): number {
  if (!Number.isFinite(cents) || cents <= 0) return 0;
  return Math.max(1, Math.round(cents / 100));
}

function normalizeSsn(ssn: string | null | undefined): string | null {
  if (!ssn) return null;
  const digits = ssn.replace(/[\s-]/g, "");
  if (!/^\d{9}$/.test(digits)) throw new Metro2FieldError("socialSecurityNumber", "must be 9 digits");
  return digits;
}

function normalizePhone(phone: string | null | undefined): string | null {
  if (!phone) return null;
  let digits = phone.replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) digits = digits.slice(1);
  if (digits.length !== 10) throw new Metro2FieldError("telephoneNumber", "must be a 10-digit US number");
  return digits;
}

function normalizePostal(postal: string): string {
  return postal.replace(/[\s-]/g, "");
}

function validateHistoryProfile(profile: string): void {
  if (profile.length !== 24) throw new Metro2FieldError("paymentHistoryProfile", "must be exactly 24 characters");
  for (const ch of profile) {
    if (!HISTORY_CODES.has(ch)) throw new Metro2FieldError("paymentHistoryProfile", "contains an invalid code");
  }
  // "B" means "no history prior to this time", so it can only trail older positions.
  const firstB = profile.indexOf("B");
  if (firstB !== -1 && /[^B]/.test(profile.slice(firstB))) {
    throw new Metro2FieldError("paymentHistoryProfile", "B may not be embedded within other values");
  }
}

/** Base Segment values for one account. */
export function baseSegmentValues(
  account: Metro2Account,
  reporter: Pick<Metro2ReporterProfile, "identificationNumber">,
  timeStamp: Date,
): Metro2Values<typeof BASE_SEGMENT_FIELDS> {
  validateHistoryProfile(account.paymentHistoryProfile);
  const c = account.consumer;
  const delinquentStatus = /^(71|78|80|82|83|84|97)$/.test(account.accountStatus);
  if (delinquentStatus && !account.dateOfFirstDelinquency) {
    throw new Metro2FieldError("dateOfFirstDelinquency", "required for delinquent or charged-off status");
  }
  return {
    timeStamp,
    identificationNumber: reporter.identificationNumber,
    consumerAccountNumber: account.consumerAccountNumber,
    portfolioType: account.portfolioType,
    accountType: account.accountType,
    dateOpened: account.dateOpened,
    creditLimit: centsToWholeDollars(account.creditLimitCents),
    highestCredit: centsToWholeDollars(account.highestCreditCents),
    termsDuration: account.termsDuration,
    termsFrequency: account.termsFrequency,
    scheduledMonthlyPaymentAmount: centsToWholeDollars(account.scheduledMonthlyPaymentCents),
    actualPaymentAmount: centsToWholeDollars(account.actualPaymentCents),
    accountStatus: account.accountStatus,
    paymentRating: account.paymentRating ?? "",
    paymentHistoryProfile: account.paymentHistoryProfile,
    specialComment: account.specialComment ?? "",
    complianceConditionCode: account.complianceConditionCode ?? "",
    // Credit balances are reported as zero; Metro 2 has no negative amounts.
    currentBalance: centsToWholeDollars(Math.max(0, account.currentBalanceCents)),
    amountPastDue: centsToWholeDollars(account.amountPastDueCents),
    originalChargeOffAmount: centsToWholeDollars(account.originalChargeOffCents ?? 0),
    dateOfAccountInformation: account.dateOfAccountInformation,
    dateOfFirstDelinquency: account.dateOfFirstDelinquency ?? null,
    dateClosed: account.dateClosed ?? null,
    dateOfLastPayment: account.dateOfLastPayment ?? null,
    interestTypeIndicator: account.interestTypeIndicator ?? "",
    consumerTransactionType: account.consumerTransactionType ?? "",
    surname: c.surname,
    firstName: c.firstName,
    middleName: c.middleName ?? "",
    generationCode: c.generationCode ?? "",
    socialSecurityNumber: normalizeSsn(c.ssn),
    dateOfBirth: c.dateOfBirth ?? null,
    telephoneNumber: normalizePhone(c.telephone),
    ecoaCode: c.ecoaCode ?? "1",
    consumerInformationIndicator: c.consumerInformationIndicator ?? "",
    countryCode: c.countryCode ?? "US",
    firstLineOfAddress: c.addressLine1,
    secondLineOfAddress: c.addressLine2 ?? "",
    city: c.city,
    state: c.state,
    postalCode: normalizePostal(c.postalCode),
    addressIndicator: c.addressIndicator ?? "",
    residenceCode: c.residenceCode ?? "",
  };
}

export function buildBaseSegment(account: Metro2Account, reporter: Pick<Metro2ReporterProfile, "identificationNumber">, timeStamp: Date): string {
  return buildRecord(BASE_SEGMENT_FIELDS, baseSegmentValues(account, reporter, timeStamp));
}

export function buildHeaderRecord(reporter: Metro2ReporterProfile, activityDate: Date, dateCreated: Date): string {
  return buildRecord(HEADER_FIELDS, {
    innovisProgramIdentifier: reporter.innovisProgramIdentifier ?? "",
    equifaxProgramIdentifier: reporter.equifaxProgramIdentifier ?? "",
    experianProgramIdentifier: reporter.experianProgramIdentifier ?? "",
    transUnionProgramIdentifier: reporter.transUnionProgramIdentifier ?? "",
    activityDate,
    dateCreated,
    programDate: reporter.programDate,
    programRevisionDate: reporter.programRevisionDate,
    reporterName: reporter.reporterName,
    reporterAddress: reporter.reporterAddress,
    reporterTelephoneNumber: normalizePhone(reporter.reporterTelephone),
    softwareVendorName: reporter.softwareVendorName,
    softwareVersionNumber: reporter.softwareVersionNumber,
  });
}

const TRAILER_STATUS_FIELDS: Record<string, FieldNames<typeof TRAILER_FIELDS>> = {
  DF: "totalStatusCodeDF",
  DA: "totalStatusCodeDA",
  "05": "totalStatusCode05",
  "11": "totalStatusCode11",
  "13": "totalStatusCode13",
  "61": "totalStatusCode61",
  "62": "totalStatusCode62",
  "63": "totalStatusCode63",
  "64": "totalStatusCode64",
  "65": "totalStatusCode65",
  "71": "totalStatusCode71",
  "78": "totalStatusCode78",
  "80": "totalStatusCode80",
  "82": "totalStatusCode82",
  "83": "totalStatusCode83",
  "84": "totalStatusCode84",
  "88": "totalStatusCode88",
  "89": "totalStatusCode89",
  "93": "totalStatusCode93",
  "94": "totalStatusCode94",
  "95": "totalStatusCode95",
  "96": "totalStatusCode96",
  "97": "totalStatusCode97",
};

/** Trailer totals derived from the generated base segments themselves. */
export function buildTrailerRecord(baseSegments: readonly string[]): string {
  const values: Record<string, number> = {
    totalBaseRecords: baseSegments.length,
    // Character format, unblocked: every physical record counts (header + bases + trailer).
    blockCount: baseSegments.length + 2,
  };
  let ssnCount = 0;
  let dobCount = 0;
  let phoneCount = 0;
  let ecoaZ = 0;
  for (const seg of baseSegments) {
    const f = parseRecord(BASE_SEGMENT_FIELDS, seg);
    const statusField = TRAILER_STATUS_FIELDS[f.accountStatus.trim()];
    if (statusField) values[statusField] = (values[statusField] ?? 0) + 1;
    if (/[1-9]/.test(f.socialSecurityNumber)) ssnCount++;
    if (/[1-9]/.test(f.dateOfBirth)) dobCount++;
    if (/[1-9]/.test(f.telephoneNumber)) phoneCount++;
    if (f.ecoaCode === "Z") ecoaZ++;
  }
  values.totalSocialSecurityNumbersAllSegments = ssnCount;
  values.totalSocialSecurityNumbersBaseSegments = ssnCount;
  values.totalDatesOfBirthAllSegments = dobCount;
  values.totalDatesOfBirthBaseSegments = dobCount;
  values.totalTelephoneNumbersAllSegments = phoneCount;
  values.totalEcoaCodeZ = ecoaZ;
  return buildRecord(TRAILER_FIELDS, values as Metro2Values<typeof TRAILER_FIELDS>);
}

export interface Metro2File {
  content: string;
  records: string[];
  baseRecordCount: number;
  statusCounts: Record<string, number>;
}

/** Header + one Base Segment per account + Trailer. */
export function generateMetro2File(input: {
  reporter: Metro2ReporterProfile;
  accounts: readonly Metro2Account[];
  activityDate: Date;
  createdAt?: Date;
  lineSeparator?: "\n" | "\r\n" | "";
}): Metro2File {
  const createdAt = input.createdAt ?? new Date();
  const header = buildHeaderRecord(input.reporter, input.activityDate, createdAt);
  const bases = input.accounts.map((a) => buildBaseSegment(a, input.reporter, createdAt));
  const trailer = buildTrailerRecord(bases);
  const records = [header, ...bases, trailer];
  const statusCounts: Record<string, number> = {};
  for (const a of input.accounts) statusCounts[a.accountStatus] = (statusCounts[a.accountStatus] ?? 0) + 1;
  const sep = input.lineSeparator ?? "\n";
  return { content: records.join(sep) + sep, records, baseRecordCount: bases.length, statusCounts };
}

/** Mask SSN and date of birth in a base segment for on-screen previews. Header/trailer pass through. */
export function redactRecord(record: string): string {
  if (record.length !== RECORD_LENGTH || record[4] !== "1") return record;
  let out = record;
  for (const f of BASE_SEGMENT_FIELDS as readonly Metro2FieldSpec[]) {
    if (!f.sensitive) continue;
    out = out.slice(0, f.start - 1) + "*".repeat(f.length) + out.slice(f.start - 1 + f.length);
  }
  return out;
}
