// Package mldsa is a straightforward, dependency-free implementation of
// ML-DSA-65 as specified in NIST FIPS 204 (August 2024).
//
// It favours readability and correctness over speed: arithmetic uses plain
// 64-bit modular reduction rather than Montgomery form, and nothing is
// vectorised. It is NOT constant-time and must not be used to protect real
// secrets. Its purpose is to make the benchmark suite build with only the Go
// standard library. Correctness is checked against OpenSSL (see
// analysis/crosscheck_mldsa.py). For speed comparisons, the suite also
// supports Cloudflare CIRCL via the `circl` build tag.
package mldsa

const (
	q    = 8380417
	n    = 256
	d    = 13
	zeta = 1753
	nInv = 8347681 // 256^-1 mod q
)

// ML-DSA-65 parameters (FIPS 204, Table 1).
const (
	k      = 6
	l      = 5
	eta    = 4
	tau    = 49
	beta   = tau * eta // 196
	gamma1 = 1 << 19
	gamma2 = (q - 1) / 32 // 261888
	omega  = 55
	lambda = 192
	cTilde = lambda / 4 // 48 bytes
)

// Encoded sizes in bytes.
const (
	PublicKeySize  = 32 + 32*k*10                       // 1952
	PrivateKeySize = 32 + 32 + 64 + 32*(k+l)*4 + 32*d*k // 4032
	SignatureSize  = cTilde + l*32*20 + omega + k       // 3309
	SeedSize       = 32
)

type poly [n]uint32 // coefficients in [0, q)

var zetas [n]uint32

func init() {
	// zetas[i] = zeta^brv8(i) mod q
	for i := 0; i < n; i++ {
		zetas[i] = powMod(zeta, uint64(brv8(uint8(i))))
	}
}

func brv8(x uint8) uint8 {
	var r uint8
	for i := 0; i < 8; i++ {
		r = (r << 1) | (x & 1)
		x >>= 1
	}
	return r
}

func powMod(b, e uint64) uint32 {
	r := uint64(1)
	b %= q
	for e > 0 {
		if e&1 == 1 {
			r = r * b % q
		}
		b = b * b % q
		e >>= 1
	}
	return uint32(r)
}

func addq(a, b uint32) uint32 { return uint32((uint64(a) + uint64(b)) % q) }
func subq(a, b uint32) uint32 { return uint32((uint64(a) + q - uint64(b)) % q) }
func mulq(a, b uint32) uint32 { return uint32(uint64(a) * uint64(b) % q) }

// toQ maps a signed integer into [0, q).
func toQ(x int64) uint32 {
	x %= q
	if x < 0 {
		x += q
	}
	return uint32(x)
}

// centered returns the representative of a in (-(q-1)/2, (q-1)/2].
func centered(a uint32) int64 {
	if a > (q-1)/2 {
		return int64(a) - q
	}
	return int64(a)
}

func ntt(w *poly) {
	m := 0
	for length := 128; length >= 1; length >>= 1 {
		for start := 0; start < n; start += 2 * length {
			m++
			z := zetas[m]
			for j := start; j < start+length; j++ {
				t := mulq(z, w[j+length])
				w[j+length] = subq(w[j], t)
				w[j] = addq(w[j], t)
			}
		}
	}
}

func invNTT(w *poly) {
	m := n
	for length := 1; length < n; length <<= 1 {
		for start := 0; start < n; start += 2 * length {
			m--
			z := q - zetas[m] // -zetas[m] mod q
			for j := start; j < start+length; j++ {
				t := w[j]
				w[j] = addq(t, w[j+length])
				w[j+length] = mulq(z, subq(t, w[j+length]))
			}
		}
	}
	for j := range w {
		w[j] = mulq(nInv, w[j])
	}
}

func pointwise(a, b *poly) (c poly) {
	for i := range c {
		c[i] = mulq(a[i], b[i])
	}
	return
}

func addPoly(a, b *poly) (c poly) {
	for i := range c {
		c[i] = addq(a[i], b[i])
	}
	return
}

func subPoly(a, b *poly) (c poly) {
	for i := range c {
		c[i] = subq(a[i], b[i])
	}
	return
}

func infNorm(a *poly) int64 {
	var m int64
	for _, c := range a {
		v := centered(c)
		if v < 0 {
			v = -v
		}
		if v > m {
			m = v
		}
	}
	return m
}

// modPM returns r mod± alpha, in (-alpha/2, alpha/2] for even alpha.
func modPM(r int64, alpha int64) int64 {
	r0 := r % alpha
	if r0 < 0 {
		r0 += alpha
	}
	if r0 > alpha/2 {
		r0 -= alpha
	}
	return r0
}

func power2Round(r uint32) (r1 uint32, r0 int64) {
	rp := int64(r)
	r0 = modPM(rp, 1<<d)
	return uint32((rp - r0) >> d), r0
}

func decompose(r uint32) (r1 int64, r0 int64) {
	rp := int64(r)
	r0 = modPM(rp, 2*gamma2)
	if rp-r0 == q-1 {
		return 0, r0 - 1
	}
	return (rp - r0) / (2 * gamma2), r0
}

func highBits(r uint32) int64 { r1, _ := decompose(r); return r1 }
func lowBits(r uint32) int64  { _, r0 := decompose(r); return r0 }

func makeHint(z, r uint32) bool {
	return highBits(r) != highBits(addq(r, z))
}

func useHint(h bool, r uint32) int64 {
	const m = (q - 1) / (2 * gamma2) // 16
	r1, r0 := decompose(r)
	if h {
		if r0 > 0 {
			return (r1 + 1) % m
		}
		return (r1 - 1 + m) % m
	}
	return r1
}
