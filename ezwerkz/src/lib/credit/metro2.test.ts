import { describe, expect, it, vi } from "vitest";
import {
  ACCOUNT_STATUS,
  BASE_SEGMENT_FIELDS,
  HEADER_FIELDS,
  Metro2FieldError,
  RECORD_LENGTH,
  TRAILER_FIELDS,
  accountStatusFor,
  assertLayout,
  buildBaseSegment,
  buildHeaderRecord,
  buildPaymentHistoryProfile,
  buildTrailerRecord,
  centsToWholeDollars,
  delinquencyBucket,
  formatField,
  generateMetro2File,
  parseRecord,
  paymentHistoryCodeFor,
  paymentRatingFor,
  redactRecord,
  sanitizeAlphanumeric,
  type Metro2Account,
  type Metro2FieldSpec,
  type Metro2ReporterProfile,
} from "./metro2";

const reporter: Metro2ReporterProfile = {
  identificationNumber: "SSV0000001",
  equifaxProgramIdentifier: "EQ12345678",
  experianProgramIdentifier: "EX123",
  transUnionProgramIdentifier: "TU12345678",
  innovisProgramIdentifier: "IN12345678",
  reporterName: "EzWerkz Inc",
  reporterAddress: "100 Market St, Suite 5, San Francisco CA 94105",
  reporterTelephone: "+14155550100",
  programDate: "2026-05-01",
  programRevisionDate: "2026-10-01",
  softwareVendorName: "EzWerkz",
  softwareVersionNumber: "1.0",
};

const SSN = "666-12-3456"; // 666 area numbers are never issued

function account(overrides: Partial<Metro2Account> = {}): Metro2Account {
  return {
    consumerAccountNumber: "SSV1000000000042",
    portfolioType: "C",
    accountType: "15",
    dateOpened: "2026-04-16",
    creditLimitCents: 1_000_00,
    highestCreditCents: 54_00,
    termsDuration: "LOC",
    termsFrequency: "M",
    scheduledMonthlyPaymentCents: 5_00,
    actualPaymentCents: 5_00,
    accountStatus: ACCOUNT_STATUS.current,
    paymentHistoryProfile: "00000DBBBBBBBBBBBBBBBBBB",
    complianceConditionCode: "",
    currentBalanceCents: 5_00,
    amountPastDueCents: 0,
    dateOfAccountInformation: "2026-10-15",
    dateOfLastPayment: "2026-10-03",
    consumer: {
      surname: "Johnson",
      firstName: "Maya",
      middleName: "Renée",
      ssn: SSN,
      dateOfBirth: "1998-03-07",
      telephone: "+14155550123",
      addressLine1: "742 Evergreen Terrace Apt 3",
      city: "Oakland",
      state: "CA",
      postalCode: "94607-1234",
    },
    ...overrides,
  };
}

const NOW = new Date(Date.UTC(2026, 9, 16, 9, 5, 7));

describe("layout tables", () => {
  it.each([
    ["header", HEADER_FIELDS],
    ["base", BASE_SEGMENT_FIELDS],
    ["trailer", TRAILER_FIELDS],
  ] as const)("%s layout is contiguous and totals 426 bytes", (_name, fields) => {
    expect(() => assertLayout(fields)).not.toThrow();
    const total = (fields as readonly Metro2FieldSpec[]).reduce((n, f) => n + f.length, 0);
    expect(total).toBe(RECORD_LENGTH);
  });

  it("rejects a broken layout", () => {
    expect(() =>
      assertLayout([
        { field: "1", name: "a", start: 1, length: 4, type: "N" },
        { field: "2", name: "b", start: 6, length: 422, type: "AN" },
      ]),
    ).toThrow(/gap/);
  });

  it("places key base-segment fields at their CRRG positions", () => {
    const pos = Object.fromEntries((BASE_SEGMENT_FIELDS as readonly Metro2FieldSpec[]).map((f) => [f.name, [f.start, f.length]]));
    expect(pos.identificationNumber).toEqual([21, 20]);
    expect(pos.consumerAccountNumber).toEqual([43, 30]);
    expect(pos.accountStatus).toEqual([124, 2]);
    expect(pos.paymentHistoryProfile).toEqual([127, 24]);
    expect(pos.complianceConditionCode).toEqual([153, 2]);
    expect(pos.currentBalance).toEqual([155, 9]);
    expect(pos.dateOfAccountInformation).toEqual([182, 8]);
    expect(pos.surname).toEqual([232, 25]);
    expect(pos.socialSecurityNumber).toEqual([298, 9]);
    expect(pos.ecoaCode).toEqual([325, 1]);
    expect(pos.postalCode).toEqual([416, 9]);
    expect(pos.residenceCode).toEqual([426, 1]);
  });
});

describe("formatField padding", () => {
  const n: Metro2FieldSpec = { field: "x", name: "amount", start: 1, length: 9, type: "N" };
  const an: Metro2FieldSpec = { field: "x", name: "name", start: 1, length: 10, type: "AN" };
  const strictAn: Metro2FieldSpec = { ...an, name: "acct", strict: true };
  const date: Metro2FieldSpec = { field: "x", name: "d", start: 1, length: 8, type: "DATE" };
  const ts: Metro2FieldSpec = { field: "x", name: "ts", start: 1, length: 14, type: "TS" };

  it("right-justifies and zero-fills numerics", () => {
    expect(formatField(n, 1234)).toBe("000001234");
    expect(formatField(n, null)).toBe("000000000");
    expect(formatField(n, "12-34")).toBe("000001234");
  });

  it("rejects negative, fractional and overflowing numerics", () => {
    expect(() => formatField(n, -1)).toThrow(Metro2FieldError);
    expect(() => formatField(n, 1.5)).toThrow(Metro2FieldError);
    expect(() => formatField(n, 1_000_000_000)).toThrow(/exceeds 9 digits/);
    expect(() => formatField(n, "12a")).toThrow(/digits only/);
  });

  it("left-justifies, space-fills and upper-cases alphanumerics", () => {
    expect(formatField(an, "abc")).toBe("ABC       ");
    expect(formatField(an, undefined)).toBe("          ");
    expect(formatField(an, "José Núñez")).toBe("JOSE NUNEZ");
  });

  it("truncates free text but rejects overlong strict fields", () => {
    expect(formatField(an, "Bartholomew-Smythe")).toBe("BARTHOLOME");
    expect(() => formatField(strictAn, "ABCDEFGHIJK")).toThrow(/exceeds 10 characters/);
  });

  it("formats dates as MMDDYYYY and zero-fills missing dates", () => {
    expect(formatField(date, "2026-03-07")).toBe("03072026");
    expect(formatField(date, new Date(Date.UTC(2025, 11, 31)))).toBe("12312025");
    expect(formatField(date, null)).toBe("00000000");
    expect(() => formatField(date, "not a date")).toThrow(Metro2FieldError);
  });

  it("formats time stamps as MMDDYYYYHHMMSS (UTC)", () => {
    expect(formatField(ts, NOW)).toBe("10162026090507");
  });

  it("strips characters outside the Metro 2 set", () => {
    expect(sanitizeAlphanumeric("o'brien & sons #4, apt. 2/b ✓")).toBe("O'BRIEN & SONS #4, APT. 2/B");
  });
});

describe("status and history mapping", () => {
  it("buckets days past due", () => {
    expect([0, 29, 30, 59, 60, 89, 90, 119, 120, 149, 150, 179, 180, 400].map(delinquencyBucket)).toEqual([
      0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6,
    ]);
  });

  it.each([
    [0, "11"],
    [15, "11"],
    [30, "71"],
    [65, "78"],
    [95, "80"],
    [125, "82"],
    [155, "83"],
    [200, "84"],
  ])("%i days past due -> status %s", (dpd, code) => {
    expect(accountStatusFor({ daysPastDue: dpd, balanceCents: 500, closed: false, chargedOff: false })).toBe(code);
  });

  it("maps closed zero-balance accounts to 13 and charge-offs to 97", () => {
    expect(accountStatusFor({ daysPastDue: 0, balanceCents: 0, closed: true, chargedOff: false })).toBe("13");
    expect(accountStatusFor({ daysPastDue: 200, balanceCents: 5000, closed: true, chargedOff: true })).toBe("97");
    // Closed at the consumer's request but still owing: keep reporting standing, not 13.
    expect(accountStatusFor({ daysPastDue: 0, balanceCents: 500, closed: true, chargedOff: false })).toBe("11");
  });

  it("sets Payment Rating only where the CRRG requires it", () => {
    expect(paymentRatingFor("13", 0)).toBe("0");
    expect(paymentRatingFor("13", 45)).toBe("1");
    expect(paymentRatingFor("11", 0)).toBe("");
    expect(paymentRatingFor("71", 40)).toBe("");
  });

  it("maps monthly standing to history characters", () => {
    expect(paymentHistoryCodeFor({ daysPastDue: 0, balanceCents: 500 })).toBe("0");
    expect(paymentHistoryCodeFor({ daysPastDue: 0, balanceCents: 0 })).toBe("E");
    expect(paymentHistoryCodeFor({ daysPastDue: 31, balanceCents: 500 })).toBe("1");
    expect(paymentHistoryCodeFor({ daysPastDue: 181, balanceCents: 500 })).toBe("6");
    expect(paymentHistoryCodeFor({ daysPastDue: 181, balanceCents: 500, chargedOff: true })).toBe("L");
  });

  it("builds a 24-month profile, most recent prior month first", () => {
    const profile = buildPaymentHistoryProfile({
      dateOfAccountInformation: new Date(Date.UTC(2026, 9, 15)),
      dateOpened: new Date(Date.UTC(2026, 3, 16)),
      months: { "2026-09": "0", "2026-08": "1", "2026-07": "0", "2026-06": "0", "2026-05": "0" },
    });
    expect(profile).toHaveLength(24);
    // Sep, Aug, Jul, Jun, May, Apr (opened, no data), then B for months before opening.
    expect(profile).toBe("01000D" + "B".repeat(18));
  });

  it("uses D for open months with no data and handles year boundaries", () => {
    const profile = buildPaymentHistoryProfile({
      dateOfAccountInformation: new Date(Date.UTC(2027, 0, 31)),
      dateOpened: new Date(Date.UTC(2024, 0, 1)),
      months: { "2026-12": "0", "2026-11": "E" },
    });
    expect(profile.slice(0, 3)).toBe("0ED");
    expect(profile).not.toContain("B");
  });
});

describe("records", () => {
  it("builds a 426-byte header with HEADER identifier and dates", () => {
    const rec = buildHeaderRecord(reporter, new Date(Date.UTC(2026, 9, 15)), NOW);
    expect(rec).toHaveLength(426);
    const f = parseRecord(HEADER_FIELDS, rec);
    expect(f.recordDescriptorWord).toBe("0426");
    expect(f.recordIdentifier).toBe("HEADER");
    expect(f.experianProgramIdentifier).toBe("EX123");
    expect(f.activityDate).toBe("10152026");
    expect(f.dateCreated).toBe("10162026");
    expect(f.programDate).toBe("05012026");
    expect(f.reporterTelephoneNumber).toBe("4155550100");
    expect(f.reporterName).toBe("EZWERKZ INC".padEnd(40, " "));
    expect(f.reserved).toBe(" ".repeat(146));
  });

  it("builds a 426-byte base segment with every field in place", () => {
    const rec = buildBaseSegment(account(), reporter, NOW);
    expect(rec).toHaveLength(426);
    const f = parseRecord(BASE_SEGMENT_FIELDS, rec);
    expect(f.recordDescriptorWord).toBe("0426");
    expect(f.processingIndicator).toBe("1");
    expect(f.timeStamp).toBe("10162026090507");
    expect(f.reserved1).toBe("0");
    expect(f.identificationNumber).toBe("SSV0000001          ");
    expect(f.consumerAccountNumber).toBe("SSV1000000000042".padEnd(30, " "));
    expect(f.portfolioType).toBe("C");
    expect(f.accountType).toBe("15");
    expect(f.dateOpened).toBe("04162026");
    expect(f.creditLimit).toBe("000001000");
    expect(f.highestCredit).toBe("000000054");
    expect(f.termsDuration).toBe("LOC");
    expect(f.termsFrequency).toBe("M");
    expect(f.scheduledMonthlyPaymentAmount).toBe("000000005");
    expect(f.actualPaymentAmount).toBe("000000005");
    expect(f.accountStatus).toBe("11");
    expect(f.paymentRating).toBe(" ");
    expect(f.paymentHistoryProfile).toBe("00000DBBBBBBBBBBBBBBBBBB");
    expect(f.specialComment).toBe("  ");
    expect(f.complianceConditionCode).toBe("  ");
    expect(f.currentBalance).toBe("000000005");
    expect(f.amountPastDue).toBe("000000000");
    expect(f.originalChargeOffAmount).toBe("000000000");
    expect(f.dateOfAccountInformation).toBe("10152026");
    expect(f.dateOfFirstDelinquency).toBe("00000000");
    expect(f.dateClosed).toBe("00000000");
    expect(f.dateOfLastPayment).toBe("10032026");
    expect(f.surname).toBe("JOHNSON".padEnd(25, " "));
    expect(f.firstName).toBe("MAYA".padEnd(20, " "));
    expect(f.middleName).toBe("RENEE".padEnd(20, " "));
    expect(f.socialSecurityNumber).toBe("666123456");
    expect(f.dateOfBirth).toBe("03071998");
    expect(f.telephoneNumber).toBe("4155550123");
    expect(f.ecoaCode).toBe("1");
    expect(f.countryCode).toBe("US");
    expect(f.firstLineOfAddress).toBe("742 EVERGREEN TERRACE APT 3".padEnd(32, " "));
    expect(f.city).toBe("OAKLAND".padEnd(20, " "));
    expect(f.state).toBe("CA");
    expect(f.postalCode).toBe("946071234");
  });

  it("reports XB while a dispute is open", () => {
    const rec = buildBaseSegment(account({ complianceConditionCode: "XB" }), reporter, NOW);
    expect(rec.slice(152, 154)).toBe("XB");
  });

  it("requires a date of first delinquency for delinquent statuses", () => {
    expect(() => buildBaseSegment(account({ accountStatus: "71", amountPastDueCents: 500 }), reporter, NOW)).toThrow(
      /dateOfFirstDelinquency/,
    );
    const rec = buildBaseSegment(
      account({ accountStatus: "71", amountPastDueCents: 500, dateOfFirstDelinquency: "2026-09-09" }),
      reporter,
      NOW,
    );
    expect(parseRecord(BASE_SEGMENT_FIELDS, rec).dateOfFirstDelinquency).toBe("09092026");
  });

  it("rejects invalid history profiles", () => {
    expect(() => buildBaseSegment(account({ paymentHistoryProfile: "000" }), reporter, NOW)).toThrow(/24 characters/);
    expect(() => buildBaseSegment(account({ paymentHistoryProfile: "0B0" + "B".repeat(21) }), reporter, NOW)).toThrow(
      /embedded/,
    );
    expect(() => buildBaseSegment(account({ paymentHistoryProfile: "X".repeat(24) }), reporter, NOW)).toThrow(/invalid code/);
  });

  it("never puts the SSN in error messages and never logs it", () => {
    const log = vi.spyOn(console, "log");
    const err = vi.spyOn(console, "error");
    let message = "";
    try {
      buildBaseSegment(account({ consumer: { ...account().consumer, ssn: "666-12-345" } }), reporter, NOW);
    } catch (e) {
      message = (e as Error).message;
    }
    expect(message).toMatch(/socialSecurityNumber/);
    expect(message).not.toContain("66612345");
    expect(message).not.toContain("666-12-345");
    expect(log).not.toHaveBeenCalled();
    expect(err).not.toHaveBeenCalled();
    log.mockRestore();
    err.mockRestore();
  });

  it("zero-fills a missing SSN", () => {
    const rec = buildBaseSegment(account({ consumer: { ...account().consumer, ssn: null } }), reporter, NOW);
    expect(parseRecord(BASE_SEGMENT_FIELDS, rec).socialSecurityNumber).toBe("000000000");
  });

  it("rounds to whole dollars without zeroing small non-zero amounts", () => {
    expect(centsToWholeDollars(0)).toBe(0);
    expect(centsToWholeDollars(40)).toBe(1);
    expect(centsToWholeDollars(149)).toBe(1);
    expect(centsToWholeDollars(150)).toBe(2);
    expect(centsToWholeDollars(-500)).toBe(0);
  });

  it("builds a trailer whose totals come from the base segments", () => {
    const bases = [
      buildBaseSegment(account(), reporter, NOW),
      buildBaseSegment(account({ consumerAccountNumber: "B2" }), reporter, NOW),
      buildBaseSegment(
        account({
          consumerAccountNumber: "B3",
          accountStatus: "78",
          amountPastDueCents: 1000,
          dateOfFirstDelinquency: "2026-08-10",
          consumer: { ...account().consumer, ssn: null, telephone: null },
        }),
        reporter,
        NOW,
      ),
    ];
    const rec = buildTrailerRecord(bases);
    expect(rec).toHaveLength(426);
    const f = parseRecord(TRAILER_FIELDS, rec);
    expect(f.recordIdentifier).toBe("TRAILER");
    expect(f.totalBaseRecords).toBe("000000003");
    expect(f.blockCount).toBe("000000005");
    expect(f.totalStatusCode11).toBe("000000002");
    expect(f.totalStatusCode78).toBe("000000001");
    expect(f.totalStatusCode97).toBe("000000000");
    expect(f.totalSocialSecurityNumbersAllSegments).toBe("000000002");
    expect(f.totalSocialSecurityNumbersBaseSegments).toBe("000000002");
    expect(f.totalDatesOfBirthBaseSegments).toBe("000000003");
    expect(f.totalTelephoneNumbersAllSegments).toBe("000000002");
    expect(f.reserved2).toBe(" ".repeat(19));
  });
});

describe("generateMetro2File", () => {
  it("emits header, one base per account and trailer, each 426 bytes", () => {
    const file = generateMetro2File({
      reporter,
      accounts: [account(), account({ consumerAccountNumber: "B2", accountStatus: "13", paymentRating: "0", currentBalanceCents: 0 })],
      activityDate: new Date(Date.UTC(2026, 9, 15)),
      createdAt: NOW,
    });
    expect(file.records).toHaveLength(4);
    expect(file.baseRecordCount).toBe(2);
    for (const r of file.records) expect(r).toHaveLength(426);
    expect(file.records[0]!.slice(4, 10)).toBe("HEADER");
    expect(file.records[3]!.slice(4, 11)).toBe("TRAILER");
    expect(file.content.split("\n").filter(Boolean)).toHaveLength(4);
    expect(file.statusCounts).toEqual({ "11": 1, "13": 1 });
  });

  it("supports unseparated fixed-length output", () => {
    const file = generateMetro2File({ reporter, accounts: [account()], activityDate: NOW, createdAt: NOW, lineSeparator: "" });
    expect(file.content).toHaveLength(426 * 3);
  });
});

describe("redactRecord", () => {
  it("masks SSN and DOB in base segments only", () => {
    const base = buildBaseSegment(account(), reporter, NOW);
    const red = redactRecord(base);
    expect(red).toHaveLength(426);
    expect(red.slice(297, 306)).toBe("*********");
    expect(red.slice(306, 314)).toBe("********");
    expect(red).not.toContain("666123456");
    expect(red.slice(0, 297)).toBe(base.slice(0, 297));
    const header = buildHeaderRecord(reporter, NOW, NOW);
    expect(redactRecord(header)).toBe(header);
  });
});
