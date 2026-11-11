"""Reference timings for an optimised C implementation (OpenSSL, via
pyca/cryptography), to compare with the Go implementations in cmd/microbench.
Python call overhead (~1 us) is included in every figure.

Usage: python3 analysis/microbench_openssl.py [N] > results/microbench_openssl.json
"""
import json
import os
import statistics
import sys
import time

from cryptography.hazmat.backends.openssl.backend import backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, mldsa

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
msg = os.urandom(200)
ctx = b"qsbg-msg-v1"


def timeit(fn, n):
    out = []
    for _ in range(n):
        t = time.perf_counter_ns()
        fn()
        out.append((time.perf_counter_ns() - t) / 1000)
    out.sort()
    return {"n": n, "median_us": out[n // 2], "p95_us": out[n * 95 // 100], "mean_us": statistics.fmean(out)}


schemes = {
    "ecdsa-p256 (OpenSSL)": (lambda: ec.generate_private_key(ec.SECP256R1()),
                             lambda k: k.sign(msg, ec.ECDSA(hashes.SHA256())),
                             lambda k, s: k.public_key().verify(s, msg, ec.ECDSA(hashes.SHA256()))),
    "ed25519 (OpenSSL)": (ed25519.Ed25519PrivateKey.generate,
                          lambda k: k.sign(msg),
                          lambda k, s: k.public_key().verify(s, msg)),
    "mldsa65 (OpenSSL)": (mldsa.MLDSA65PrivateKey.generate,
                          lambda k: k.sign(msg, ctx),
                          lambda k, s: k.public_key().verify(s, msg, ctx)),
}
results = []
for name, (gen, sign, verify) in schemes.items():
    kg = timeit(gen, max(N // 10, 50))
    key = gen()
    sig = sign(key)
    results.append({
        "scheme": name, "signature_bytes": len(sig),
        "keygen": kg, "sign": timeit(lambda: sign(key), N), "verify": timeit(lambda: verify(key, sig), N),
    })
    print(f"{name:22s} sign median {results[-1]['sign']['median_us']:8.1f} us  verify median {results[-1]['verify']['median_us']:8.1f} us", file=sys.stderr)
json.dump({"library": backend.openssl_version_text(), "msg_len": len(msg), "results": results}, sys.stdout, indent=2)
print()
