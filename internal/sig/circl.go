//go:build circl

// Optional optimised ML-DSA-65 backend from Cloudflare CIRCL.
// Build with:  go get github.com/cloudflare/circl@latest && go build -tags circl ./...
//
// NOTE: this file was written against the CIRCL v1.6 mldsa65 API but could
// not be compiled in the authoring environment (no module download). If the
// build fails, check the function signatures in
// https://pkg.go.dev/github.com/cloudflare/circl/sign/mldsa/mldsa65
package sig

import (
	"crypto/rand"

	"github.com/cloudflare/circl/sign/mldsa/mldsa65"
)

func init() {
	Schemes["mldsa65-circl"] = circlScheme{}
	verifierParsers["mldsa65-circl"] = func(b []byte) (Verifier, error) {
		var pk mldsa65.PublicKey
		if err := pk.UnmarshalBinary(b); err != nil {
			return nil, err
		}
		return circlVerifier{&pk}, nil
	}
	DefaultMLDSA = "mldsa65-circl"
}

type circlScheme struct{}

func (circlScheme) Name() string { return "mldsa65-circl" }
func (circlScheme) GenerateKey() (Signer, Verifier, error) {
	pk, sk, err := mldsa65.GenerateKey(rand.Reader)
	if err != nil {
		return nil, nil, err
	}
	return circlSigner{sk, pk}, circlVerifier{pk}, nil
}

type circlSigner struct {
	sk *mldsa65.PrivateKey
	pk *mldsa65.PublicKey
}

func (s circlSigner) Name() string { return "mldsa65-circl" }
func (s circlSigner) Sign(msg, ctx []byte) ([]byte, error) {
	out := make([]byte, mldsa65.SignatureSize)
	err := mldsa65.SignTo(s.sk, msg, ctx, true, out)
	return out, err
}
func (s circlSigner) PublicKey() []byte { b, _ := s.pk.MarshalBinary(); return b }

type circlVerifier struct{ pk *mldsa65.PublicKey }

func (v circlVerifier) Verify(msg, sig, ctx []byte) bool { return mldsa65.Verify(v.pk, msg, ctx, sig) }
