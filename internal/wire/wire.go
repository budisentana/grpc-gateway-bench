// Package wire holds the Protobuf message, gRPC-over-HTTP/2 framing,
// the canonical signed byte string, Merkle batch proofs and metadata sizing.
//
// gRPC is implemented directly on Go's net/http HTTP/2 stack following the
// "gRPC over HTTP2" specification (length-prefixed messages, application/grpc
// content type, grpc-status trailers, base64 "-bin" metadata). This keeps the
// suite free of external modules.
package wire

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// Method is the gRPC path of the single unary method under test.
const Method = "/qsbg.eval.Echo/Submit"

// Payload mirrors message qsbg.eval.EvaluationPayload (see proto/eval.proto).
type Payload struct {
	TransactionID  int64  `json:"transaction_id"`
	PayloadVector  string `json:"payload_vector"`
	IngressEpochMs int64  `json:"ingress_epoch_ms"`
}

// Marshal encodes p in Protobuf wire format (proto3 semantics: zero values omitted).
func (p *Payload) Marshal() []byte {
	b := make([]byte, 0, 24+len(p.PayloadVector))
	if p.TransactionID != 0 {
		b = append(b, 0x08)
		b = binary.AppendUvarint(b, uint64(p.TransactionID))
	}
	if p.PayloadVector != "" {
		b = append(b, 0x12)
		b = binary.AppendUvarint(b, uint64(len(p.PayloadVector)))
		b = append(b, p.PayloadVector...)
	}
	if p.IngressEpochMs != 0 {
		b = append(b, 0x18)
		b = binary.AppendUvarint(b, uint64(p.IngressEpochMs))
	}
	return b
}

// Unmarshal decodes Protobuf bytes into p, skipping unknown fields.
func (p *Payload) Unmarshal(b []byte) error {
	*p = Payload{}
	for len(b) > 0 {
		key, n := binary.Uvarint(b)
		if n <= 0 {
			return errors.New("proto: bad key")
		}
		b = b[n:]
		field, wt := key>>3, key&7
		switch wt {
		case 0:
			v, n := binary.Uvarint(b)
			if n <= 0 {
				return errors.New("proto: bad varint")
			}
			b = b[n:]
			switch field {
			case 1:
				p.TransactionID = int64(v)
			case 3:
				p.IngressEpochMs = int64(v)
			}
		case 2:
			ln, n := binary.Uvarint(b)
			if n <= 0 || uint64(len(b)-n) < ln {
				return errors.New("proto: bad length")
			}
			if field == 2 {
				p.PayloadVector = string(b[n : n+int(ln)])
			}
			b = b[n+int(ln):]
		default:
			return fmt.Errorf("proto: unsupported wire type %d", wt)
		}
	}
	return nil
}

// Frame wraps a message in the 5-byte gRPC length prefix (uncompressed).
func Frame(msg []byte) []byte {
	out := make([]byte, 5+len(msg))
	binary.BigEndian.PutUint32(out[1:5], uint32(len(msg)))
	copy(out[5:], msg)
	return out
}

// ReadFrame reads one length-prefixed gRPC message.
func ReadFrame(r io.Reader, max int) ([]byte, error) {
	var hdr [5]byte
	if _, err := io.ReadFull(r, hdr[:]); err != nil {
		return nil, err
	}
	if hdr[0] != 0 {
		return nil, errors.New("grpc: compressed messages not supported")
	}
	ln := int(binary.BigEndian.Uint32(hdr[1:]))
	if ln > max {
		return nil, fmt.Errorf("grpc: message %d exceeds limit %d", ln, max)
	}
	buf := make([]byte, ln)
	_, err := io.ReadFull(r, buf)
	return buf, err
}

// gRPC status codes used here.
const (
	StatusOK                = 0
	StatusInvalidArgument   = 3
	StatusResourceExhausted = 8
	StatusUnauthenticated   = 16
	StatusInternal          = 13
)

// B64 is the gRPC encoding for "-bin" metadata: standard alphabet, no padding.
var B64 = base64.RawStdEncoding

// Metadata header names.
const (
	HdrSig   = "x-qsbg-sig-bin"
	HdrTS    = "x-qsbg-ts"
	HdrRID   = "x-qsbg-rid-bin"
	HdrRoot  = "x-qsbg-root-bin"
	HdrPath  = "x-qsbg-path-bin"
	HdrIdx   = "x-qsbg-idx"
	HdrN     = "x-qsbg-n"
	HdrMode  = "x-qsbg-mode"
	HdrPad   = "x-qsbg-pad" // filler simulating tracing/auth headers
	CtxMsg   = "qsbg-msg-v1"
	CtxBatch = "qsbg-batch-v1"
)

// Canonical builds the byte string that is signed (C2) or hashed into a leaf (C3):
// method path || 0x00 || protobuf body || ts (8 bytes BE, ms) || request ID (16 bytes).
func Canonical(method string, body []byte, tsMs int64, rid []byte) []byte {
	out := make([]byte, 0, len(method)+1+len(body)+8+len(rid))
	out = append(out, method...)
	out = append(out, 0)
	out = append(out, body...)
	out = binary.BigEndian.AppendUint64(out, uint64(tsMs))
	return append(out, rid...)
}

// HeaderListSize computes the HTTP/2 header list size as defined in
// RFC 9113 §6.5.2 (name + value + 32 octets per field), the quantity gRPC's
// max-metadata limit is applied to.
func HeaderListSize(h http.Header) int {
	total := 0
	for name, vals := range h {
		for _, v := range vals {
			total += len(name) + len(v) + 32
		}
	}
	return total
}

// RequestHeaderListSize adds the HTTP/2 pseudo-headers of a gRPC request.
func RequestHeaderListSize(r *http.Request) int {
	pseudo := len(":method") + len(r.Method) + 32 +
		len(":scheme") + len("https") + 32 +
		len(":path") + len(r.URL.Path) + 32 +
		len(":authority") + len(r.Host) + 32
	h := r.Header.Clone()
	h.Del("Content-Length")
	return pseudo + HeaderListSize(lowerKeys(h))
}

func lowerKeys(h http.Header) http.Header {
	out := http.Header{}
	for k, v := range h {
		out[strings.ToLower(k)] = v
	}
	return out
}

// ---- Merkle batch proofs (C3) ----

// LeafHash = SHA-256(0x00 || canonical); node = SHA-256(0x01 || left || right).
func LeafHash(canonical []byte) [32]byte {
	h := sha256.New()
	h.Write([]byte{0})
	h.Write(canonical)
	var out [32]byte
	h.Sum(out[:0])
	return out
}

func nodeHash(a, b [32]byte) [32]byte {
	h := sha256.New()
	h.Write([]byte{1})
	h.Write(a[:])
	h.Write(b[:])
	var out [32]byte
	h.Sum(out[:0])
	return out
}

// BuildTree returns the root and an audit path for every leaf. An odd node at
// any level is promoted unchanged, so the path length is ceil(log2 n) at most.
func BuildTree(leaves [][32]byte) (root [32]byte, paths [][][32]byte) {
	nLeaves := len(leaves)
	paths = make([][][32]byte, nLeaves)
	pos := make([]int, nLeaves) // index of each leaf's ancestor at current level
	for i := range pos {
		pos[i] = i
	}
	level := leaves
	for len(level) > 1 {
		next := make([][32]byte, 0, (len(level)+1)/2)
		for i := 0; i < len(level); i += 2 {
			if i+1 < len(level) {
				next = append(next, nodeHash(level[i], level[i+1]))
			} else {
				next = append(next, level[i])
			}
		}
		for leaf := range pos {
			p := pos[leaf]
			sib := p ^ 1
			if sib < len(level) {
				paths[leaf] = append(paths[leaf], level[sib])
			}
			pos[leaf] = p / 2
		}
		level = next
	}
	return level[0], paths
}

// VerifyPath recomputes the root from a leaf, its index, the batch size and its path.
func VerifyPath(leaf [32]byte, idx, nLeaves int, path [][32]byte) [32]byte {
	cur := leaf
	p, width := idx, nLeaves
	pi := 0
	for width > 1 {
		sib := p ^ 1
		if sib < width {
			if pi >= len(path) {
				return [32]byte{}
			}
			if p%2 == 0 {
				cur = nodeHash(cur, path[pi])
			} else {
				cur = nodeHash(path[pi], cur)
			}
			pi++
		}
		p /= 2
		width = (width + 1) / 2
	}
	return cur
}

// PackPath / UnpackPath serialise an audit path for metadata.
func PackPath(path [][32]byte) []byte {
	out := make([]byte, 0, 32*len(path))
	for _, h := range path {
		out = append(out, h[:]...)
	}
	return out
}

func UnpackPath(b []byte) ([][32]byte, error) {
	if len(b)%32 != 0 {
		return nil, errors.New("bad path length")
	}
	out := make([][32]byte, len(b)/32)
	for i := range out {
		copy(out[i][:], b[32*i:])
	}
	return out, nil
}
