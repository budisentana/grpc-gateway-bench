// Package tlsutil generates a private test PKI and builds TLS configs for the
// public link (server-auth only) and the internal link (mutual TLS).
package tlsutil

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"fmt"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"time"
)

// Groups maps a key-exchange label to the TLS 1.3 groups offered.
// Offering a single group forces the handshake to use it or fail.
func Groups(kex string) ([]tls.CurveID, error) {
	switch kex {
	case "classical":
		return []tls.CurveID{tls.X25519}, nil
	case "hybrid":
		return []tls.CurveID{tls.X25519MLKEM768}, nil
	}
	return nil, fmt.Errorf("unknown key exchange %q (classical|hybrid)", kex)
}

// GenerateAll writes ca.pem, server.pem/key, client.pem/key into dir.
// Hosts are added to the server certificate's SANs.
func GenerateAll(dir string, hosts []string) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	caKey, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	caTmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "qsbg-bench test CA"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              time.Now().AddDate(2, 0, 0),
		IsCA:                  true,
		KeyUsage:              x509.KeyUsageCertSign,
		BasicConstraintsValid: true,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTmpl, caTmpl, &caKey.PublicKey, caKey)
	if err != nil {
		return err
	}
	caCert, _ := x509.ParseCertificate(caDER)
	if err := writePEM(filepath.Join(dir, "ca.pem"), "CERTIFICATE", caDER); err != nil {
		return err
	}
	leaf := func(name string, serial int64, server bool) error {
		key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		t := &x509.Certificate{
			SerialNumber: big.NewInt(serial),
			Subject:      pkix.Name{CommonName: "qsbg-" + name},
			NotBefore:    time.Now().Add(-time.Hour),
			NotAfter:     time.Now().AddDate(2, 0, 0),
			KeyUsage:     x509.KeyUsageDigitalSignature,
		}
		if server {
			t.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
			for _, h := range hosts {
				if ip := net.ParseIP(h); ip != nil {
					t.IPAddresses = append(t.IPAddresses, ip)
				} else {
					t.DNSNames = append(t.DNSNames, h)
				}
			}
		} else {
			t.ExtKeyUsage = []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
		}
		der, err := x509.CreateCertificate(rand.Reader, t, caCert, &key.PublicKey, caKey)
		if err != nil {
			return err
		}
		kd, _ := x509.MarshalECPrivateKey(key)
		if err := writePEM(filepath.Join(dir, name+".pem"), "CERTIFICATE", der); err != nil {
			return err
		}
		return writePEM(filepath.Join(dir, name+".key"), "EC PRIVATE KEY", kd)
	}
	if err := leaf("server", 2, true); err != nil {
		return err
	}
	return leaf("client", 3, false)
}

func writePEM(path, typ string, der []byte) error {
	return os.WriteFile(path, pem.EncodeToMemory(&pem.Block{Type: typ, Bytes: der}), 0o600)
}

func pool(dir string) (*x509.CertPool, error) {
	b, err := os.ReadFile(filepath.Join(dir, "ca.pem"))
	if err != nil {
		return nil, err
	}
	p := x509.NewCertPool()
	p.AppendCertsFromPEM(b)
	return p, nil
}

// ServerConfig: requireClient=true gives mutual TLS.
func ServerConfig(dir, kex string, requireClient bool, nextProtos []string) (*tls.Config, error) {
	cert, err := tls.LoadX509KeyPair(filepath.Join(dir, "server.pem"), filepath.Join(dir, "server.key"))
	if err != nil {
		return nil, err
	}
	g, err := Groups(kex)
	if err != nil {
		return nil, err
	}
	cfg := &tls.Config{
		Certificates:     []tls.Certificate{cert},
		MinVersion:       tls.VersionTLS13,
		CurvePreferences: g,
		NextProtos:       nextProtos,
	}
	if requireClient {
		p, err := pool(dir)
		if err != nil {
			return nil, err
		}
		cfg.ClientCAs = p
		cfg.ClientAuth = tls.RequireAndVerifyClientCert
	}
	return cfg, nil
}

// ClientConfig: withClientCert=true presents the client certificate (mTLS).
func ClientConfig(dir, kex, serverName string, withClientCert bool, nextProtos []string) (*tls.Config, error) {
	p, err := pool(dir)
	if err != nil {
		return nil, err
	}
	g, err := Groups(kex)
	if err != nil {
		return nil, err
	}
	cfg := &tls.Config{
		RootCAs:          p,
		ServerName:       serverName,
		MinVersion:       tls.VersionTLS13,
		CurvePreferences: g,
		NextProtos:       nextProtos,
	}
	if withClientCert {
		cert, err := tls.LoadX509KeyPair(filepath.Join(dir, "client.pem"), filepath.Join(dir, "client.key"))
		if err != nil {
			return nil, err
		}
		cfg.Certificates = []tls.Certificate{cert}
	}
	return cfg, nil
}
