package mldsa

import "crypto/sha3"

// packBits packs 256 values of `bits` bits each, least-significant bit first
// (FIPS 204 SimpleBitPack / BitPack after the value transform).
func packBits(dst []byte, vals *[n]uint32, bits uint) {
	var acc uint64
	var nb uint
	o := 0
	for _, v := range vals {
		acc |= uint64(v) << nb
		nb += bits
		for nb >= 8 {
			dst[o] = byte(acc)
			o++
			acc >>= 8
			nb -= 8
		}
	}
}

func unpackBits(src []byte, bits uint) (vals [n]uint32) {
	var acc uint64
	var nb uint
	o := 0
	mask := uint64(1)<<bits - 1
	for i := 0; i < n; i++ {
		for nb < bits {
			acc |= uint64(src[o]) << nb
			o++
			nb += 8
		}
		vals[i] = uint32(acc & mask)
		acc >>= bits
		nb -= bits
	}
	return
}

// bitPack(w, a, b): packs b - w_i with bitlen(a+b) bits. w given in [0,q).
func bitPack(dst []byte, w *poly, b int64, bits uint) {
	var vals [n]uint32
	for i, c := range w {
		vals[i] = uint32(b - centered(c))
	}
	packBits(dst, &vals, bits)
}

func bitUnpack(src []byte, b int64, bits uint) (w poly) {
	vals := unpackBits(src, bits)
	for i, v := range vals {
		w[i] = toQ(b - int64(v))
	}
	return
}

func shake256(out []byte, in ...[]byte) {
	h := sha3.NewSHAKE256()
	for _, b := range in {
		h.Write(b)
	}
	h.Read(out)
}

// rejNTTPoly samples a polynomial in NTT domain from seed (FIPS 204 Alg. 30).
func rejNTTPoly(seed []byte) (a poly) {
	h := sha3.NewSHAKE128()
	h.Write(seed)
	// 168 bytes = one SHAKE128 block, divisible by 3, so triples never
	// straddle a chunk boundary.
	var buf [168]byte
	j := 0
	for j < n {
		h.Read(buf[:])
		for pos := 0; pos+3 <= len(buf) && j < n; pos += 3 {
			z := uint32(buf[pos]) | uint32(buf[pos+1])<<8 | uint32(buf[pos+2]&0x7f)<<16
			if z < q {
				a[j] = z
				j++
			}
		}
	}
	return
}

// rejBoundedPoly samples a polynomial with coefficients in [-eta, eta] (Alg. 31).
func rejBoundedPoly(seed []byte) (a poly) {
	h := sha3.NewSHAKE256()
	h.Write(seed)
	var b [1]byte
	j := 0
	for j < n {
		h.Read(b[:])
		z0, z1 := b[0]&0x0f, b[0]>>4
		if z0 < 9 {
			a[j] = toQ(int64(eta) - int64(z0))
			j++
		}
		if z1 < 9 && j < n {
			a[j] = toQ(int64(eta) - int64(z1))
			j++
		}
	}
	return
}

func expandA(rho []byte) (A [k][l]poly) {
	seed := make([]byte, 34)
	copy(seed, rho)
	for r := 0; r < k; r++ {
		for s := 0; s < l; s++ {
			seed[32] = byte(s)
			seed[33] = byte(r)
			A[r][s] = rejNTTPoly(seed)
		}
	}
	return
}

func expandS(rhoPrime []byte) (s1 [l]poly, s2 [k]poly) {
	seed := make([]byte, 66)
	copy(seed, rhoPrime)
	for r := 0; r < l; r++ {
		seed[64], seed[65] = byte(r), 0
		s1[r] = rejBoundedPoly(seed)
	}
	for r := 0; r < k; r++ {
		seed[64], seed[65] = byte(r+l), byte((r+l)>>8)
		s2[r] = rejBoundedPoly(seed)
	}
	return
}

func expandMask(rhoPP []byte, kappa int) (y [l]poly) {
	seed := make([]byte, 66)
	copy(seed, rhoPP)
	buf := make([]byte, 32*20)
	for r := 0; r < l; r++ {
		v := kappa + r
		seed[64], seed[65] = byte(v), byte(v>>8)
		shake256(buf, seed)
		y[r] = bitUnpack(buf, gamma1, 20)
	}
	return
}

func sampleInBall(rho []byte) (c poly) {
	h := sha3.NewSHAKE256()
	h.Write(rho)
	var s [8]byte
	h.Read(s[:])
	signs := uint64(0)
	for i := 0; i < 8; i++ {
		signs |= uint64(s[i]) << (8 * i)
	}
	var jb [1]byte
	for i := n - tau; i < n; i++ {
		for {
			h.Read(jb[:])
			if int(jb[0]) <= i {
				break
			}
		}
		j := int(jb[0])
		c[i] = c[j]
		bit := (signs >> uint(i+tau-n)) & 1
		if bit == 1 {
			c[j] = q - 1
		} else {
			c[j] = 1
		}
	}
	return
}

func pkEncode(rho []byte, t1 *[k]poly) []byte {
	pk := make([]byte, PublicKeySize)
	copy(pk, rho)
	for i := 0; i < k; i++ {
		vals := [n]uint32(t1[i])
		packBits(pk[32+320*i:], &vals, 10)
	}
	return pk
}

func pkDecode(pk []byte) (rho []byte, t1 [k]poly) {
	rho = pk[:32]
	for i := 0; i < k; i++ {
		t1[i] = poly(unpackBits(pk[32+320*i:], 10))
	}
	return
}

func skEncode(rho, K, tr []byte, s1 *[l]poly, s2 *[k]poly, t0 *[k]poly) []byte {
	sk := make([]byte, PrivateKeySize)
	copy(sk[0:], rho)
	copy(sk[32:], K)
	copy(sk[64:], tr)
	o := 128
	for i := 0; i < l; i++ {
		bitPack(sk[o:], &s1[i], eta, 4)
		o += 128
	}
	for i := 0; i < k; i++ {
		bitPack(sk[o:], &s2[i], eta, 4)
		o += 128
	}
	for i := 0; i < k; i++ {
		bitPack(sk[o:], &t0[i], 1<<(d-1), 13)
		o += 416
	}
	return sk
}

func skDecode(sk []byte) (rho, K, tr []byte, s1 [l]poly, s2 [k]poly, t0 [k]poly) {
	rho, K, tr = sk[0:32], sk[32:64], sk[64:128]
	o := 128
	for i := 0; i < l; i++ {
		s1[i] = bitUnpack(sk[o:], eta, 4)
		o += 128
	}
	for i := 0; i < k; i++ {
		s2[i] = bitUnpack(sk[o:], eta, 4)
		o += 128
	}
	for i := 0; i < k; i++ {
		t0[i] = bitUnpack(sk[o:], 1<<(d-1), 13)
		o += 416
	}
	return
}

func w1Encode(w1 *[k][n]uint32) []byte {
	out := make([]byte, k*128)
	for i := 0; i < k; i++ {
		packBits(out[128*i:], &w1[i], 4)
	}
	return out
}

func sigEncode(ct []byte, z *[l]poly, h *[k][n]bool) []byte {
	sig := make([]byte, SignatureSize)
	copy(sig, ct)
	o := cTilde
	for i := 0; i < l; i++ {
		bitPack(sig[o:], &z[i], gamma1, 20)
		o += 640
	}
	idx := 0
	for i := 0; i < k; i++ {
		for j := 0; j < n; j++ {
			if h[i][j] {
				sig[o+idx] = byte(j)
				idx++
			}
		}
		sig[o+omega+i] = byte(idx)
	}
	return sig
}

func sigDecode(sig []byte) (ct []byte, z [l]poly, h [k][n]bool, ok bool) {
	if len(sig) != SignatureSize {
		return
	}
	ct = sig[:cTilde]
	o := cTilde
	for i := 0; i < l; i++ {
		z[i] = bitUnpack(sig[o:], gamma1, 20)
		o += 640
	}
	y := sig[o:]
	idx := 0
	for i := 0; i < k; i++ {
		end := int(y[omega+i])
		if end < idx || end > omega {
			return
		}
		first := idx
		for idx < end {
			if idx > first && y[idx-1] >= y[idx] {
				return
			}
			h[i][y[idx]] = true
			idx++
		}
	}
	for i := idx; i < omega; i++ {
		if y[i] != 0 {
			return
		}
	}
	ok = true
	return
}
