package mldsa

import (
	"crypto/rand"
	"crypto/subtle"
	"errors"
)

// PrivateKey holds the encoded secret key plus pre-computed NTT forms, so
// that signing does not repeat ExpandA and NTT(s1), NTT(s2), NTT(t0).
type PrivateKey struct {
	enc []byte
	K   []byte
	tr  []byte
	A   [k][l]poly
	s1h [l]poly
	s2h [k]poly
	t0h [k]poly
	pub *PublicKey
}

// PublicKey holds the encoded public key plus pre-computed values for Verify.
type PublicKey struct {
	enc []byte
	tr  []byte
	A   [k][l]poly
	t1h [k]poly // NTT(t1 * 2^d)
}

func (sk *PrivateKey) Bytes() []byte      { return append([]byte(nil), sk.enc...) }
func (sk *PrivateKey) Public() *PublicKey { return sk.pub }
func (pk *PublicKey) Bytes() []byte       { return append([]byte(nil), pk.enc...) }

// GenerateKey creates a key pair from fresh randomness.
func GenerateKey() (*PrivateKey, error) {
	var seed [SeedSize]byte
	if _, err := rand.Read(seed[:]); err != nil {
		return nil, err
	}
	return NewKeyFromSeed(seed[:])
}

// NewKeyFromSeed implements ML-DSA.KeyGen_internal (FIPS 204 Alg. 6).
func NewKeyFromSeed(xi []byte) (*PrivateKey, error) {
	if len(xi) != SeedSize {
		return nil, errors.New("mldsa: seed must be 32 bytes")
	}
	buf := make([]byte, 128)
	shake256(buf, xi, []byte{k, l})
	rho, rhoPrime, K := buf[:32], buf[32:96], buf[96:128]

	A := expandA(rho)
	s1, s2 := expandS(rhoPrime)
	var s1h [l]poly
	for i := range s1 {
		s1h[i] = s1[i]
		ntt(&s1h[i])
	}
	var t1, t0 [k]poly
	for i := 0; i < k; i++ {
		var acc poly
		for j := 0; j < l; j++ {
			p := pointwise(&A[i][j], &s1h[j])
			acc = addPoly(&acc, &p)
		}
		invNTT(&acc)
		t := addPoly(&acc, &s2[i])
		for c := 0; c < n; c++ {
			r1, r0 := power2Round(t[c])
			t1[i][c] = r1
			t0[i][c] = toQ(r0)
		}
	}
	pkEnc := pkEncode(rho, &t1)
	tr := make([]byte, 64)
	shake256(tr, pkEnc)
	skEnc := skEncode(rho, K, tr, &s1, &s2, &t0)
	return parsePrivate(skEnc, pkEnc)
}

func parsePrivate(skEnc, pkEnc []byte) (*PrivateKey, error) {
	rho, K, tr, s1, s2, t0 := skDecode(skEnc)
	sk := &PrivateKey{enc: skEnc, K: append([]byte(nil), K...), tr: append([]byte(nil), tr...)}
	sk.A = expandA(rho)
	for i := 0; i < l; i++ {
		sk.s1h[i] = s1[i]
		ntt(&sk.s1h[i])
	}
	for i := 0; i < k; i++ {
		sk.s2h[i] = s2[i]
		ntt(&sk.s2h[i])
		sk.t0h[i] = t0[i]
		ntt(&sk.t0h[i])
	}
	pk, err := NewPublicKey(pkEnc)
	if err != nil {
		return nil, err
	}
	sk.pub = pk
	return sk, nil
}

// NewPublicKey parses an encoded public key.
func NewPublicKey(enc []byte) (*PublicKey, error) {
	if len(enc) != PublicKeySize {
		return nil, errors.New("mldsa: bad public key length")
	}
	pk := &PublicKey{enc: append([]byte(nil), enc...)}
	rho, t1 := pkDecode(pk.enc)
	pk.A = expandA(rho)
	pk.tr = make([]byte, 64)
	shake256(pk.tr, pk.enc)
	for i := 0; i < k; i++ {
		for c := 0; c < n; c++ {
			pk.t1h[i][c] = mulq(t1[i][c], 1<<d)
		}
		ntt(&pk.t1h[i])
	}
	return pk, nil
}

func formatMessage(msg, ctx []byte) ([]byte, error) {
	if len(ctx) > 255 {
		return nil, errors.New("mldsa: context too long")
	}
	m := make([]byte, 0, 2+len(ctx)+len(msg))
	m = append(m, 0, byte(len(ctx)))
	m = append(m, ctx...)
	return append(m, msg...), nil
}

// Sign implements ML-DSA.Sign (hedged, FIPS 204 Alg. 2) with context ctx.
func Sign(sk *PrivateKey, msg, ctx []byte) ([]byte, error) {
	var rnd [32]byte
	if _, err := rand.Read(rnd[:]); err != nil {
		return nil, err
	}
	mp, err := formatMessage(msg, ctx)
	if err != nil {
		return nil, err
	}
	return signInternal(sk, mp, rnd[:]), nil
}

// SignDeterministic uses rnd = 0^32 (FIPS 204 deterministic variant).
func SignDeterministic(sk *PrivateKey, msg, ctx []byte) ([]byte, error) {
	mp, err := formatMessage(msg, ctx)
	if err != nil {
		return nil, err
	}
	return signInternal(sk, mp, make([]byte, 32)), nil
}

func signInternal(sk *PrivateKey, mp, rnd []byte) []byte {
	mu := make([]byte, 64)
	shake256(mu, sk.tr, mp)
	rhoPP := make([]byte, 64)
	shake256(rhoPP, sk.K, rnd, mu)

	for kappa := 0; ; kappa += l {
		y := expandMask(rhoPP, kappa)
		var yh [l]poly
		for i := range y {
			yh[i] = y[i]
			ntt(&yh[i])
		}
		var w [k]poly
		var w1 [k][n]uint32
		for i := 0; i < k; i++ {
			var acc poly
			for j := 0; j < l; j++ {
				p := pointwise(&sk.A[i][j], &yh[j])
				acc = addPoly(&acc, &p)
			}
			invNTT(&acc)
			w[i] = acc
			for c := 0; c < n; c++ {
				w1[i][c] = uint32(highBits(acc[c]))
			}
		}
		ct := make([]byte, cTilde)
		shake256(ct, mu, w1Encode(&w1))
		c := sampleInBall(ct)
		ch := c
		ntt(&ch)

		var z [l]poly
		reject := false
		for i := 0; i < l && !reject; i++ {
			cs1 := pointwise(&ch, &sk.s1h[i])
			invNTT(&cs1)
			z[i] = addPoly(&y[i], &cs1)
			if infNorm(&z[i]) >= gamma1-beta {
				reject = true
			}
		}
		if reject {
			continue
		}
		var h [k][n]bool
		ones := 0
		for i := 0; i < k && !reject; i++ {
			cs2 := pointwise(&ch, &sk.s2h[i])
			invNTT(&cs2)
			wMinus := subPoly(&w[i], &cs2)
			for c := 0; c < n; c++ {
				r0 := lowBits(wMinus[c])
				if r0 < 0 {
					r0 = -r0
				}
				if r0 >= gamma2-beta {
					reject = true
					break
				}
			}
			if reject {
				break
			}
			ct0 := pointwise(&ch, &sk.t0h[i])
			invNTT(&ct0)
			if infNorm(&ct0) >= gamma2 {
				reject = true
				break
			}
			r := addPoly(&wMinus, &ct0)
			for c := 0; c < n; c++ {
				neg := subq(0, ct0[c])
				if makeHint(neg, r[c]) {
					h[i][c] = true
					ones++
				}
			}
		}
		if reject || ones > omega {
			continue
		}
		return sigEncode(ct, &z, &h)
	}
}

// Verify implements ML-DSA.Verify (FIPS 204 Alg. 3) with context ctx.
func Verify(pk *PublicKey, msg, sig, ctx []byte) bool {
	mp, err := formatMessage(msg, ctx)
	if err != nil {
		return false
	}
	ct, z, h, ok := sigDecode(sig)
	if !ok {
		return false
	}
	for i := 0; i < l; i++ {
		if infNorm(&z[i]) >= gamma1-beta {
			return false
		}
	}
	mu := make([]byte, 64)
	shake256(mu, pk.tr, mp)
	c := sampleInBall(ct)
	ch := c
	ntt(&ch)
	var zh [l]poly
	for i := range z {
		zh[i] = z[i]
		ntt(&zh[i])
	}
	var w1 [k][n]uint32
	for i := 0; i < k; i++ {
		var acc poly
		for j := 0; j < l; j++ {
			p := pointwise(&pk.A[i][j], &zh[j])
			acc = addPoly(&acc, &p)
		}
		ct1 := pointwise(&ch, &pk.t1h[i])
		acc = subPoly(&acc, &ct1)
		invNTT(&acc)
		for c := 0; c < n; c++ {
			w1[i][c] = uint32(useHint(h[i][c], acc[c]))
		}
	}
	ct2 := make([]byte, cTilde)
	shake256(ct2, mu, w1Encode(&w1))
	return subtle.ConstantTimeCompare(ct, ct2) == 1
}
