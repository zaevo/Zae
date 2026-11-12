"""E12: the actual CHRONOS-2036 experiment, pre-registered on 2026-11-12.

Your scenario, made verifiable:
  * On 2036-11-11 the message is CHRONOS-2036-NNNNN, where NNNNN is derived
    from the NIST Randomness Beacon pulse at 2036-11-11T00:00:00Z (primary)
    or the drand 'quicknet' round at that instant (fallback). Both are public,
    signed, and unpredictable today, so the message provably originates in 2036.
  * TODAY the receiver records what it 'receives' and the record is committed
    to git and pushed to GitHub (independent timestamp). Any mechanism,
    present or future, that claims to have received the 2036 message in 2026
    must point to a commitment like this one made BEFORE 2036.
  * Chance of an exact match: 1e-5 per commitment.

Usage:
  python e12_chronos_2036.py commit [label]   # make a 2026 receiver record
  python e12_chronos_2036.py verify           # run on/after 2036-11-11
"""
import sys, os, json, time, glob, urllib.request, calendar
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from chronos import protocol as P

TARGET_UTC = "2036-11-11T00:00:00Z"
TARGET_EPOCH = calendar.timegm(time.strptime(TARGET_UTC, "%Y-%m-%dT%H:%M:%SZ"))
DRAND = "https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
DRAND_GENESIS, DRAND_PERIOD = 1692803367, 3
DRAND_ROUND = (TARGET_EPOCH - DRAND_GENESIS) // DRAND_PERIOD + 1
LEDGER = os.path.join(os.path.dirname(__file__), '..', 'ledger')


def commit(label="P-CTC receiver (Cirq, Willow-like noise)"):
    from experiments.e11_live_beacon_level5 import receiver_bit
    seen = P.last_pulse()
    bits = [receiver_bit()[0] for _ in range(17)]
    guess = P.from_bits(bits)
    rec = {"experiment": "CHRONOS-2036", "target_utc": TARGET_UTC,
           "message_rule": "CHRONOS-2036-{int(NIST outputValue,16) % 100000:05d} for pulse at target_utc; "
                           "fallback: int(drand quicknet randomness,16) % 100000 at round below",
           "drand_fallback_round": DRAND_ROUND, "receiver_mechanism": label,
           "received_message": f"CHRONOS-2036-{guess:05d}", "received_bits": bits,
           "latest_pulse_seen": seen["pulseIndex"], "latest_pulse_timestamp": seen["timeStamp"],
           "latest_pulse_value_prefix": seen["outputValue"][:32],
           "committed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rec["sha256"] = P.commit(rec)
    os.makedirs(LEDGER, exist_ok=True)
    path = os.path.join(LEDGER, f"CHRONOS-2036_commit_{rec['committed_utc'].replace(':', '')}.json")
    with open(path, "w") as f:
        json.dump(rec, f, indent=2)
    print(json.dumps(rec, indent=2)); return rec


def true_message():
    try:
        p = P.fetch(f"{P.BEACON}/pulse/time/{TARGET_EPOCH * 1000}")
        assert p["timeStamp"].startswith("2036-11-11T00:00")
        return f"CHRONOS-2036-{int(p['outputValue'], 16) % 100000:05d}", "NIST"
    except Exception:
        with urllib.request.urlopen(f"{DRAND}/public/{DRAND_ROUND}", timeout=20) as r:
            d = json.load(r)
        return f"CHRONOS-2036-{int(d['randomness'], 16) % 100000:05d}", "drand"


def verify():
    if time.time() < TARGET_EPOCH:
        print(f"Too early: the message does not exist until {TARGET_UTC}. That is the point."); return
    msg, src = true_message()
    print(f"True 2036 message ({src}): {msg}")
    for f in sorted(glob.glob(os.path.join(LEDGER, "CHRONOS-2036_commit_*.json"))):
        rec = json.load(open(f))
        ok = P.commit({k: v for k, v in rec.items() if k != "sha256"}) == rec["sha256"]
        print(f"{os.path.basename(f)} hash_ok={ok} received={rec['received_message']} MATCH={rec['received_message'] == msg}")


if __name__ == "__main__":
    {"commit": lambda: commit(*sys.argv[2:3]), "verify": verify}[sys.argv[1] if len(sys.argv) > 1 else "verify"]()
