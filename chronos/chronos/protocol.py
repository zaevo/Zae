"""The Chronos Verification Protocol (CVP).

The hard part of 'a message from 2036' is not sending it, it is *proving* it
came from 2036. CVP makes that proof mechanical:

 1. ORIGIN.  The message is defined as a deterministic function of a public,
    signed randomness-beacon value that does not yet exist when the receiver
    acts (NIST Randomness Beacon 2.0; fallback drand). Nobody can predict,
    plant, or reconstruct it in advance, so a correct reception is
    evidence of a future origin.
       message = f"CHRONOS-{year}-{int(outputValue,16) % 100000:05d}"
 2. COMMITMENT.  Before the target pulse exists, the receiver publishes its
    decoded guess, plus the hash of the record, plus the *latest* beacon pulse
    it saw (this proves the commitment was made no earlier than that pulse).
    Publishing to git/GitHub gives an independent timestamp.
 3. NO POST-COMMIT INFORMATION.  Decoding may not use any data produced after
    the commitment (for example a postselection herald). Results that do are
    reported separately and labelled 'conditional', never as Level 5.
 4. STATISTICS.  Each 5-digit message is matched by chance with p = 1e-5;
    bits by Binomial(n, 1/2). Evidence is reported as p-values over all
    pre-registered trials (no optional stopping: the trial count is fixed in
    the commitment)."""
import hashlib, json, time, urllib.request
from math import comb

BEACON = "https://beacon.nist.gov/beacon/2.0"


def fetch(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.load(r)["pulse"]
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 * (k + 1))


def last_pulse():
    return fetch(f"{BEACON}/pulse/last")


def pulse(index, chain=2):
    return fetch(f"{BEACON}/chain/{chain}/pulse/{index}")


def message_from_pulse(p):
    year = p["timeStamp"][:4]
    n = int(p["outputValue"], 16) % 100000
    return f"CHRONOS-{year}-{n:05d}", n


def to_bits(n, k=17):
    return [(n >> i) & 1 for i in range(k)]


def from_bits(bits):
    return sum(b << i for i, b in enumerate(bits)) % 100000


def commit(record):
    blob = json.dumps(record, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def binom_sf(k, n, p=0.5):
    """P(X >= k)."""
    return sum(comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1))
