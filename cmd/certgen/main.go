// certgen creates the private test PKI used by all components.
package main

import (
	"flag"
	"log"
	"strings"

	"qsbg/internal/tlsutil"
)

func main() {
	dir := flag.String("out", "certs", "output directory")
	hosts := flag.String("hosts", "localhost,127.0.0.1", "comma-separated SANs for the server certificate")
	flag.Parse()
	if err := tlsutil.GenerateAll(*dir, strings.Split(*hosts, ",")); err != nil {
		log.Fatal(err)
	}
	log.Printf("wrote test PKI to %s", *dir)
}
