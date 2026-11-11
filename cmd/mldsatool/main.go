// mldsatool exposes the pure-Go ML-DSA-65 for cross-checking against other
// implementations (see analysis/crosscheck_mldsa.py).
//
//	mldsatool keygen <seed-hex>                         -> pk-hex
//	mldsatool sign   <seed-hex> <msg-hex> <ctx-hex> [det] -> sig-hex
//	mldsatool verify <pk-hex> <msg-hex> <sig-hex> <ctx-hex> -> true|false
package main

import (
	"encoding/hex"
	"fmt"
	"os"

	"qsbg/internal/mldsa"
)

func mustHex(s string) []byte {
	b, err := hex.DecodeString(s)
	if err != nil {
		fmt.Fprintln(os.Stderr, "bad hex:", err)
		os.Exit(2)
	}
	return b
}

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "usage: mldsatool keygen|sign|verify ...")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "keygen":
		sk, err := mldsa.NewKeyFromSeed(mustHex(os.Args[2]))
		if err != nil {
			panic(err)
		}
		fmt.Println(hex.EncodeToString(sk.Public().Bytes()))
	case "sign":
		sk, err := mldsa.NewKeyFromSeed(mustHex(os.Args[2]))
		if err != nil {
			panic(err)
		}
		msg, ctx := mustHex(os.Args[3]), mustHex(os.Args[4])
		var sig []byte
		if len(os.Args) > 5 && os.Args[5] == "det" {
			sig, err = mldsa.SignDeterministic(sk, msg, ctx)
		} else {
			sig, err = mldsa.Sign(sk, msg, ctx)
		}
		if err != nil {
			panic(err)
		}
		fmt.Println(hex.EncodeToString(sig))
	case "verify":
		pk, err := mldsa.NewPublicKey(mustHex(os.Args[2]))
		if err != nil {
			panic(err)
		}
		fmt.Println(mldsa.Verify(pk, mustHex(os.Args[3]), mustHex(os.Args[4]), mustHex(os.Args[5])))
	default:
		fmt.Fprintln(os.Stderr, "unknown command")
		os.Exit(2)
	}
}
