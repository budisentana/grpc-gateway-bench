"""Cross-check the pure-Go ML-DSA-65 against OpenSSL (via pyca/cryptography).

Checks, for N random seeds and messages:
  1. Key generation from the same 32-byte seed gives identical public keys.
  2. Signatures made in Go verify in OpenSSL (with the same context string).
  3. Signatures made in OpenSSL verify in Go.
  4. Tampered signatures are rejected by Go.

Usage: python3 analysis/crosscheck_mldsa.py ./bin/mldsatool [N]
"""
import os
import subprocess
import sys

from cryptography.hazmat.primitives.asymmetric import mldsa


def run(tool, *args):
    return subprocess.run([tool, *args], check=True, capture_output=True, text=True).stdout.strip()


def main():
    tool = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    failures = 0
    for i in range(n):
        seed = os.urandom(32)
        msg = os.urandom(1 + i * 37 % 500)
        ctx = os.urandom(i % 40)

        ossl_sk = mldsa.MLDSA65PrivateKey.from_seed_bytes(seed)
        ossl_pk = ossl_sk.public_key().public_bytes_raw()
        go_pk = bytes.fromhex(run(tool, "keygen", seed.hex()))
        ok_keygen = go_pk == ossl_pk

        go_sig = bytes.fromhex(run(tool, "sign", seed.hex(), msg.hex(), ctx.hex()))
        try:
            ossl_sk.public_key().verify(go_sig, msg, ctx)
            ok_go_sig = True
        except Exception:
            ok_go_sig = False

        ossl_sig = ossl_sk.sign(msg, ctx)
        ok_ossl_sig = run(tool, "verify", go_pk.hex(), msg.hex(), ossl_sig.hex(), ctx.hex()) == "true"

        bad = bytearray(ossl_sig)
        bad[100] ^= 0x01
        ok_reject = run(tool, "verify", go_pk.hex(), msg.hex(), bytes(bad).hex(), ctx.hex()) == "false"

        ok = ok_keygen and ok_go_sig and ok_ossl_sig and ok_reject and len(go_sig) == 3309
        failures += not ok
        print(f"case {i:2d}: keygen={ok_keygen} go->openssl={ok_go_sig} "
              f"openssl->go={ok_ossl_sig} tamper_rejected={ok_reject} sig_len={len(go_sig)}")
    print(f"\n{n - failures}/{n} cases passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
