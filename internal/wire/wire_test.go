package wire

import (
	"crypto/rand"
	"testing"
)

func TestPayloadRoundTrip(t *testing.T) {
	p := Payload{TransactionID: 1234567890123, PayloadVector: "hello world", IngressEpochMs: 1762800000000}
	var q Payload
	if err := q.Unmarshal(p.Marshal()); err != nil || q != p {
		t.Fatalf("round trip failed: %v %+v", err, q)
	}
}

func TestMerkleAllSizes(t *testing.T) {
	for n := 1; n <= 70; n++ {
		leaves := make([][32]byte, n)
		for i := range leaves {
			rand.Read(leaves[i][:])
		}
		root, paths := BuildTree(leaves)
		for i := range leaves {
			got := VerifyPath(leaves[i], i, n, paths[i])
			if got != root {
				t.Fatalf("n=%d leaf=%d: root mismatch", n, i)
			}
			bad := leaves[i]
			bad[0] ^= 1
			if VerifyPath(bad, i, n, paths[i]) == root {
				t.Fatalf("n=%d leaf=%d: tampered leaf accepted", n, i)
			}
		}
	}
}
