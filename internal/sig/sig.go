// Package sig wraps the signature schemes used by the gateway and the
// micro-benchmark behind one small interface.
package sig

import (
	"crypto/ecdsa"
	"crypto/ed25519"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"fmt"

	"qsbg/internal/mldsa"
)

// Signer signs messages under a fixed key.
type Signer interface {
	Name() string
	Sign(msg, ctx []byte) ([]byte, error)
	PublicKey() []byte
}

// Verifier checks signatures for one public key.
type Verifier interface {
	Verify(msg, sig, ctx []byte) bool
}

// Scheme bundles key generation for the micro-benchmark.
type Scheme interface {
	Name() string
	GenerateKey() (Signer, Verifier, error)
}

// Schemes lists the schemes compiled into this binary.
var Schemes = map[string]Scheme{
	"ecdsa-p256":     ecdsaScheme{},
	"ed25519":        ed25519Scheme{},
	"mldsa65-gopure": goMLDSA{},
}

// Default ML-DSA backend used by the gateway; overridden by the circl build.
var DefaultMLDSA = "mldsa65-gopure"

// LoadMLDSA returns the configured ML-DSA-65 scheme.
func LoadMLDSA(name string) (Scheme, error) {
	if name == "" {
		name = DefaultMLDSA
	}
	s, ok := Schemes[name]
	if !ok {
		return nil, fmt.Errorf("unknown signature backend %q", name)
	}
	return s, nil
}

// ---- pure Go ML-DSA-65 ----

type goMLDSA struct{}

func (goMLDSA) Name() string { return "mldsa65-gopure" }
func (goMLDSA) GenerateKey() (Signer, Verifier, error) {
	sk, err := mldsa.GenerateKey()
	if err != nil {
		return nil, nil, err
	}
	return goMLDSASigner{sk}, goMLDSAVerifier{sk.Public()}, nil
}

type goMLDSASigner struct{ sk *mldsa.PrivateKey }

func (s goMLDSASigner) Name() string                         { return "mldsa65-gopure" }
func (s goMLDSASigner) Sign(msg, ctx []byte) ([]byte, error) { return mldsa.Sign(s.sk, msg, ctx) }
func (s goMLDSASigner) PublicKey() []byte                    { return s.sk.Public().Bytes() }

type goMLDSAVerifier struct{ pk *mldsa.PublicKey }

func (v goMLDSAVerifier) Verify(msg, sig, ctx []byte) bool { return mldsa.Verify(v.pk, msg, sig, ctx) }

// NewMLDSAVerifier parses a public key for the named backend.
func NewMLDSAVerifier(backend string, pk []byte) (Verifier, error) {
	if backend == "" {
		backend = DefaultMLDSA
	}
	if f, ok := verifierParsers[backend]; ok {
		return f(pk)
	}
	return nil, fmt.Errorf("no verifier for backend %q", backend)
}

var verifierParsers = map[string]func([]byte) (Verifier, error){
	"mldsa65-gopure": func(pk []byte) (Verifier, error) {
		p, err := mldsa.NewPublicKey(pk)
		if err != nil {
			return nil, err
		}
		return goMLDSAVerifier{p}, nil
	},
}

// ---- classical baselines (micro-benchmark only) ----

type ecdsaScheme struct{}

func (ecdsaScheme) Name() string { return "ecdsa-p256" }
func (ecdsaScheme) GenerateKey() (Signer, Verifier, error) {
	k, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return nil, nil, err
	}
	return ecdsaSigner{k}, ecdsaVerifier{&k.PublicKey}, nil
}

type ecdsaSigner struct{ k *ecdsa.PrivateKey }

func (s ecdsaSigner) Name() string { return "ecdsa-p256" }
func (s ecdsaSigner) Sign(msg, _ []byte) ([]byte, error) {
	h := sha256.Sum256(msg)
	return ecdsa.SignASN1(rand.Reader, s.k, h[:])
}
func (s ecdsaSigner) PublicKey() []byte {
	b, _ := s.k.PublicKey.ECDH()
	return b.Bytes()
}

type ecdsaVerifier struct{ pk *ecdsa.PublicKey }

func (v ecdsaVerifier) Verify(msg, sig, _ []byte) bool {
	h := sha256.Sum256(msg)
	return ecdsa.VerifyASN1(v.pk, h[:], sig)
}

type ed25519Scheme struct{}

func (ed25519Scheme) Name() string { return "ed25519" }
func (ed25519Scheme) GenerateKey() (Signer, Verifier, error) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, nil, err
	}
	return ed25519Signer{priv}, ed25519Verifier{pub}, nil
}

type ed25519Signer struct{ k ed25519.PrivateKey }

func (s ed25519Signer) Name() string                       { return "ed25519" }
func (s ed25519Signer) Sign(msg, _ []byte) ([]byte, error) { return ed25519.Sign(s.k, msg), nil }
func (s ed25519Signer) PublicKey() []byte                  { return s.k.Public().(ed25519.PublicKey) }

type ed25519Verifier struct{ pk ed25519.PublicKey }

func (v ed25519Verifier) Verify(msg, sig, _ []byte) bool { return ed25519.Verify(v.pk, msg, sig) }
