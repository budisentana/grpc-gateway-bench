"""Text of the JACOST manuscript. Numbers come from build_paper.py."""

TITLE = "Measuring the Cost of Post-Quantum Authentication in a REST-to-gRPC Gateway"
AUTHORS = [("Author One", "1"), ("Author Two", "2")]
AFFIL = ["^1^Department, Faculty, Institution, City, Country", "^2^Department, Faculty, Institution, City, Country"]
EMAILS = "^1^author1@institution.ac.id, ^2^author2@institution.edu*"
KEYWORDS = "post-quantum cryptography, ML-DSA, API gateway, gRPC, protocol translation, batch signatures"
KATA_KUNCI = "kriptografi pascakuantum, ML-DSA, API gateway, gRPC, translasi protokol, tanda tangan batch"


def front(n, P, runs):
    sub = '<w:pStyle w:val="Subtitle"/>'
    se = '<w:rStyle w:val="SubtleEmphasis"/><w:b w:val="0"/>'
    x = []
    x.append(f'<w:p><w:pPr>{sub}<w:spacing w:before="300" w:after="300"/><w:rPr><w:b w:val="0"/><w:bCs/></w:rPr></w:pPr>'
             + runs(TITLE, '<w:b w:val="0"/><w:bCs/>') + "</w:p>")
    auth = ", ".join(f"{a}^{s}^" for a, s in AUTHORS)
    x.append(f'<w:p><w:pPr>{sub}<w:spacing w:after="0"/></w:pPr>' + runs(auth, se + '<w:sz w:val="20"/>') + "</w:p>")
    for a in AFFIL:
        x.append(f'<w:p><w:pPr>{sub}<w:spacing w:after="0"/></w:pPr>' + runs(a, se) + "</w:p>")
    x.append(f'<w:p><w:pPr>{sub}<w:spacing w:after="0"/></w:pPr>' + runs(EMAILS, se + '<w:iCs w:val="0"/>') + "</w:p>")

    abstract = (
        "Enterprise systems increasingly translate public REST/JSON calls into internal gRPC calls at an API gateway, "
        "which makes the gateway the natural place to add post-quantum authentication. Its cost has not been measured. "
        "This study builds a REST-to-gRPC gateway and compares four internal authentication configurations: classical "
        "mutual TLS, mutual TLS with hybrid X25519MLKEM768 key exchange, an ML-DSA-65 signature per request in gRPC "
        "metadata, and one ML-DSA-65 signature per Merkle batch. Each configuration was measured on one virtual "
        f"machine with the gateway on a dedicated core, at 10 to {n['cmax']} concurrent clients, three payload sizes and "
        f"{n['reps']} repetitions. Hybrid key exchange left throughput unchanged once connections were pooled "
        f"({n['c1pct']:.0f}% of the classical baseline). Per-request signing cut throughput to {n['c2pct']:.0f}% of the "
        f"baseline because each signature took about {n['sign']:.0f} µs of gateway CPU. Batch signing recovered "
        f"{n['c3pct']:.0f}% at {n['cmax']} clients but was no better than per-request signing at low concurrency, when "
        f"batches rarely fill. Each ML-DSA-65 signature adds about {n['meta_c2'] - n['meta_c0']:,.0f} bytes of metadata, "
        f"leaving only about {8192 - n['meta_c2']:,.0f} bytes for other headers under gRPC's default 8 KB limit. "
        "Channel-level post-quantum protection is nearly free; message-level signing needs batching and metadata planning."
    )
    abstrak = (
        "Sistem enterprise semakin sering menerjemahkan panggilan REST/JSON publik menjadi panggilan gRPC internal "
        "pada sebuah API gateway, sehingga gateway menjadi tempat yang wajar untuk menambahkan autentikasi "
        "pascakuantum. Namun, biaya dari langkah tersebut belum pernah diukur. Penelitian ini membangun gateway "
        "REST-ke-gRPC dan membandingkan empat konfigurasi autentikasi internal: mutual TLS klasik, mutual TLS dengan "
        "pertukaran kunci hibrida X25519MLKEM768, satu tanda tangan ML-DSA-65 untuk setiap permintaan di metadata gRPC, "
        "dan satu tanda tangan ML-DSA-65 untuk setiap batch Merkle. Setiap konfigurasi diukur pada satu mesin virtual "
        f"dengan gateway pada satu inti prosesor khusus, dengan 10 hingga {n['cmax']} klien bersamaan, tiga ukuran "
        f"payload, dan {n['reps']} kali pengulangan. Pertukaran kunci hibrida tidak mengubah throughput setelah koneksi "
        f"digunakan ulang ({n['c1pct']:.0f}% dari konfigurasi klasik). Penandatanganan per permintaan menurunkan "
        f"throughput menjadi {n['c2pct']:.0f}% karena setiap tanda tangan memerlukan sekitar {n['sign']:.0f} µs waktu CPU "
        f"gateway. Penandatanganan batch memulihkan throughput hingga {n['c3pct']:.0f}% pada {n['cmax']} klien, tetapi "
        "tidak lebih baik daripada penandatanganan per permintaan pada konkurensi rendah karena batch jarang terisi. "
        f"Setiap tanda tangan ML-DSA-65 menambah sekitar {n['meta_c2'] - n['meta_c0']:,.0f} byte metadata, sehingga "
        f"hanya tersisa sekitar {8192 - n['meta_c2']:,.0f} byte untuk header lain di bawah batas bawaan gRPC "
        "sebesar 8 KB. Perlindungan pascakuantum pada tingkat kanal hampir tanpa biaya, sedangkan penandatanganan "
        "pada tingkat pesan memerlukan batching dan perencanaan ukuran metadata."
    )
    h1 = '<w:pStyle w:val="Heading1"/>'
    for head, text, kwl, kw in [("Abstract", abstract, "Keywords:", KEYWORDS), ("Abstrak", abstrak, "Kata kunci:", KATA_KUNCI)]:
        x.append(f'<w:p><w:pPr>{h1}</w:pPr>' + runs(head) + "</w:p>")
        x.append(P(text, '<w:spacing w:after="120"/>', '<w:sz w:val="18"/><w:szCs w:val="18"/>'))
        x.append('<w:p><w:pPr><w:spacing w:after="120"/></w:pPr>' + runs(kwl, '<w:rStyle w:val="SubtleEmphasis"/>')
                 + runs(" " + kw, '<w:sz w:val="18"/><w:szCs w:val="18"/>') + "</w:p>")
    return "".join(x)


def body(ns):
    P, H1, H2, table, figure, code, equation = (ns[k] for k in ["P", "H1", "H2", "table", "figure", "code", "equation"])
    n, S, G, H, T = ns["numbers"], ns["S"], ns["G"], ns["H"], ns["T"]
    row, f0, f1, f2 = ns["row"], ns["f0"], ns["f1"], ns["f2"]
    GO, OSSL, FIGS, BE = ns["GO"], ns["OSSL"], ns["FIGS"], ns["BE"]
    CL, PLS, RATES, KNEE = ns["CL"], ns["PLS"], ns["RATES"], ns["KNEE"]
    r0, r1, r2, r3 = ns["r0"], ns["r1"], ns["r2"], ns["r3"]
    cmax = n["cmax"]
    x = []

    # ------------------------------------------------------------ 1
    x.append(H1("Introduction"))
    x.append(P(
        "Enterprise information systems increasingly split into two worlds. Internal microservices adopt gRPC, which "
        "carries Protocol Buffers over HTTP/2 and has shown lower latency than REST/JSON in several recent studies "
        "[1]–[4]. External clients, such as browsers, mobile applications and partner systems, still call REST/JSON "
        "APIs. A translation gateway sits between the two, and widely used proxies such as Envoy already provide "
        "gRPC-JSON transcoding [5]. The gateway is therefore the point where every external request is authenticated "
        "and re-encoded before it reaches internal services."))
    x.append(P(
        "At the same time, large quantum computers would break the RSA and elliptic-curve algorithms that "
        "authenticate this traffic, because Shor's algorithm solves factoring and discrete logarithms in polynomial "
        "time [6]. NIST published the lattice-based standards ML-KEM (FIPS 203) and ML-DSA (FIPS 204) in 2024 [7], [8], "
        "and its transition plan deprecates quantum-vulnerable public-key algorithms after 2030 and disallows them "
        "after 2035 [9]. Organisations are advised to inventory where public-key cryptography is used and to plan the "
        "migration of each use [10]."))
    x.append(P(
        "Key exchange on the public web is already moving: Chrome made hybrid X25519 with ML-KEM-768 its default "
        "in version 131 [11]. Authentication is harder. Post-quantum signatures are large, and forging authentication "
        "only threatens traffic after a quantum computer exists, so browser vendors treat it as less urgent than key "
        "exchange [12]. An ML-DSA-65 signature is 3,309 bytes [8], compared with 64 bytes for Ed25519."))
    x.append(P(
        "Most performance studies of post-quantum authentication measure the TLS handshake. Paquin et al. emulated "
        "network conditions to benchmark post-quantum key exchange and signatures in TLS 1.3 [13], Sikeridis et al. "
        "measured post-quantum certificate chains [14], and Sosnowski et al. found that post-quantum TLS 1.3 "
        "handshakes perform comparably to classical ones on modern hardware [15]. Paul et al. proposed mixed "
        "certificate chains for a gradual transition [16], KEMTLS replaces handshake signatures with key encapsulation "
        "[17], and batch signatures amortise one expensive signature over many messages [18]. Beyond TLS, "
        "post-quantum protection has been placed in 5G sidecar proxies [19] and in session-layer protocols [20], and "
        "ML-DSA has been benchmarked on IoT devices [21], [22]. None of these studies measures message-level signing "
        "inside a protocol-translation gateway, where a signature must accompany every request and must fit into gRPC "
        "metadata, which is limited to 8 KB by default [23] and cannot be compressed by HTTP/2 header compression "
        "because each signature is unique [24]. Table 1 summarises this positioning."))
    x.append(table(["Work", "Transl.", "PQ auth.", "Per msg.", "Batch"], [
        ["REST/gRPC studies [1]–[4]", "no", "no", "no", "no"],
        ["gRPC-JSON transcoder [5]", "yes", "no", "no", "no"],
        ["PQ TLS benchmarks [13]–[15]", "no", "handshake", "no", "no"],
        ["Mixed chains, KEMTLS [16], [17]", "no", "handshake", "no", "no"],
        ["Batch signatures [18]", "no", "handshake", "no", "yes"],
        ["PQ sessions, IoT [20]–[22]", "no", "session/device", "no", "no"],
        ["This study", "yes", "channel and message", "yes", "yes"],
    ], [1.75, 0.75, 1.2, 0.75, 0.65], "Positioning against related work", align=["left", "center", "center", "center", "center"]))
    x.append(P(
        "This study addresses that gap with three research questions. The first asks how much latency and CPU the "
        "REST-to-gRPC translation itself adds before any post-quantum cryptography. The second asks what post-quantum "
        "authentication on the internal link costs when it is done at the channel level, with hybrid key exchange in "
        "mutual TLS, compared with the message level, with an ML-DSA-65 signature on every request. The third asks "
        "how much of that cost Merkle-tree batch signing recovers and at what latency penalty. The contributions are a "
        "gateway design that separates translation, public-link security and internal-link authentication so that "
        "each can be measured on its own; a dependency-free, open testbed with a cross-checked ML-DSA-65 "
        "implementation; and measured trade-offs, including how close ML-DSA signatures come to gRPC's default "
        "metadata limit."))

    # ------------------------------------------------------------ 2
    x.append(H1("Research Method"))
    x.append(P(
        "The study follows an experimental design. A gateway and a backend service were implemented, four internal "
        "authentication configurations were defined, and each was measured under controlled load with repeated, "
        "randomised runs. Figure 1 shows the components and where each configuration acts."))
    x.append(figure(f"{FIGS}/fig1_architecture.png", "Gateway pipeline and internal authentication configurations"))

    x.append(H2("2.1. Threat model"))
    x.append(P(
        "The gateway protects two links that face different threats. On the public link between client and gateway, "
        "the main quantum threat is store-now-decrypt-later, in which an attacker records traffic today and decrypts "
        "it once a quantum computer exists. Hybrid X25519MLKEM768 key exchange in TLS 1.3 defends against this and is "
        "already the browser default [11], so it is used for the public link in every configuration. The server "
        "certificate remains classical because the web PKI does not yet issue post-quantum certificates [12]. Client "
        "identity is checked by existing mechanisms such as OAuth 2.0 bearer tokens and is outside the scope of this "
        "study."))
    x.append(P(
        "On the internal link between gateway and services, the threat is a future attacker who forges classical "
        "credentials and impersonates the gateway. A second threat is a compromised intermediate hop, such as a sidecar "
        "or internal load balancer, that alters a request after TLS terminates. Channel-level protection handles the "
        "first threat. Only message-level signatures handle the second, because they survive TLS termination and leave "
        "a verifiable record for each request. Compromise of the gateway itself and side-channel attacks on the "
        "signature implementation are out of scope."))

    x.append(H2("2.2. Gateway design and configurations"))
    x.append(P(
        "For every request the gateway terminates public TLS, parses the JSON body and maps it to the target Protobuf "
        "message, applies the internal authentication of the active configuration, and forwards the call over a "
        "pooled HTTP/2 connection. Only the authentication step and the internal TLS settings change between "
        "configurations, so differences in the results come from them alone. Table 2 lists the four configurations."))
    x.append(table(["ID", "Internal channel", "Message authentication"], [
        ["C0", "mTLS, X25519, ECDSA P-256", "none"],
        ["C1", "mTLS, X25519MLKEM768, ECDSA P-256", "none"],
        ["C2", "as C0", "ML-DSA-65 per request"],
        ["C3", "as C0", "ML-DSA-65 per Merkle batch"],
    ], [0.5, 2.3, 1.7], "Internal authentication configurations", align=["left", "left", "left"]))
    x.append(P(
        "In C2 and C3 the gateway signs a canonical byte string made of the gRPC method path, the serialised Protobuf "
        "body, a millisecond timestamp and a random 128-bit request identifier. The timestamp and identifier let the "
        "backend reject replayed requests. The signature travels in a binary metadata header, which gRPC encodes in "
        "base64 [25], so a 3,309-byte ML-DSA-65 signature occupies 4,412 characters."))
    x.append(P(
        "In C3 the gateway collects requests for at most *T* milliseconds or until *B* requests arrive, builds a "
        "Merkle tree over their hashes and signs the root once [18]. Leaves are SHA-256 hashes of the canonical bytes "
        "with a 0x00 prefix, and inner nodes use a 0x01 prefix. Each request carries the root, its leaf index and its "
        "audit path. The first request of each batch also carries the root signature; the backend verifies it once, "
        "caches the root, and later requests of the batch are checked against the cached root. Unless stated "
        "otherwise, *T* = 5 ms and *B* = 64. Because signing is bounded by one operation per batch, batching also "
        "limits how much CPU an attacker can consume by sending many cheap requests, a concern for C2 where every "
        "accepted request forces a signature. Algorithm 1 summarises the batch signer."))
    x.append(code([
        "Algorithm 1. Batch signer (C3)",
        "Input: queue Q of (leaf, reply), T, B, key sk",
        "loop",
        "  batch <- [take(Q)]          // wait for first",
        "  t0 <- now()",
        "  while |batch| < B and now()-t0 < T do",
        "    batch.append(take(Q, T-(now()-t0)))",
        "  root, paths <- MerkleTree(leaves(batch))",
        "  sig <- ML-DSA.Sign(sk, root, 'qsbg-batch-v1')",
        "  for i, (leaf, reply) in batch do",
        "    proof <- (root, i, |batch|, paths[i])",
        "    if i = 0 then proof.sig <- sig",
        "    reply.send(proof)",
        "end loop",
    ]))

    x.append(H2("2.3. Testbed and implementation"))
    x.append(P(
        "All components run on one virtual machine with an Intel Xeon processor at 2.10 GHz, 2 vCPUs and Linux 6.18. "
        "The gateway is pinned to one core with GOMAXPROCS set to 1, and the backend and load generator share the "
        "second core. Traffic uses the loopback interface with no added delay or loss. This isolates the gateway's "
        "computational cost, which is the subject of the study; network round-trip time would add a similar delay to "
        "every configuration."))
    x.append(P(
        "The gateway, backend and load generator are written in Go 1.24.7 using only the standard library. gRPC is "
        "implemented on Go's HTTP/2 stack [26] following the gRPC over HTTP/2 specification [25]. ML-DSA-65 is a "
        "FIPS 204 implementation written for this study. It was cross-checked against OpenSSL 4.0.2 on "
        f"{ns['cross']} random cases: key generation from the same seed gave byte-identical public keys, signatures "
        "made by each implementation verified in the other, and tampered signatures were rejected. Go's TLS stack does "
        "not support ML-DSA certificates, so C1 measures post-quantum key exchange with classical certificates. The "
        "request message used throughout is:"))
    x.append(code([
        'syntax = "proto3";',
        "package qsbg.eval;",
        "message EvaluationPayload {",
        "  int64  transaction_id   = 1;",
        "  string payload_vector   = 2;",
        "  int64  ingress_epoch_ms = 3;",
        "}",
        "service Echo {",
        "  rpc Submit (EvaluationPayload)",
        "      returns (EvaluationPayload);",
        "}",
    ]))

    x.append(H2("2.4. Workload, metrics and analysis"))
    clients = ", ".join(str(int(c)) for c in CL[:-1]) + f" and {int(CL[-1])}"
    pls = ", ".join(f"{p:,}" for p in PLS[:-1]) + f" and {PLS[-1]:,}"
    rates = ", ".join(f"{int(r):,}" for r in RATES[:-1]) + f" and {int(RATES[-1]):,}"
    x.append(P(
        f"In the closed-loop workload, {clients} concurrent clients each send their next request when the previous one "
        f"returns, with `payload_vector` sizes of {pls} bytes. Every combination of configuration, payload and client "
        f"count was repeated {n['reps']} times in randomised order, with a 5 s warm-up and a 20 s measurement window. "
        f"In the open-loop workload, requests arrive at fixed rates of {rates} requests/s with a 128-byte payload, "
        "3 repetitions each and 15 s windows; latency is measured from each request's scheduled send time so that "
        "queueing appears in the tail. For C3, seven combinations of *T* (1, 5 and 10 ms) and *B* (16, 64 and 256) "
        "were run at 50 clients. Finally, filler headers of 0 to 7,500 bytes, standing in for tracing and "
        "authorisation metadata, were added to C0, C2 and C3 requests to find where the backend's 8,192-byte metadata "
        "limit is crossed."))
    x.append(P(
        "The load generator records end-to-end latency in a log-bucketed histogram with about 1% resolution. The "
        "gateway records the time spent in each stage, its CPU time and memory, and the bytes it sends on each link. "
        "The backend records signature verification time and the HTTP/2 header list size of each request, computed as "
        "in RFC 9113 [26]. For each condition the median across repetitions is reported with a 95% bootstrap "
        "confidence interval. Configurations are compared with the Kruskal–Wallis test and pairwise Mann–Whitney U "
        "tests with Holm correction, using rank-biserial correlation as the effect size. An upper bound on C2 "
        "throughput per gateway core follows from the median signing time *t*sign in microseconds:"))
    x.append(equation("*X*max ≤ 10^6^ / *t*sign", 1))
    x.append(P(
        "To make the study reproducible, every run writes one JSON file containing the load generator's settings and "
        "results together with the gateway's and backend's statistics over the same measurement window. A single "
        "script runs the whole matrix in randomised order and skips runs that already exist, so an interrupted "
        "campaign can be resumed; this was used twice during the measurements reported here, and no run was lost or "
        "repeated. A second script turns the run files into the tables, statistical tests and figures of Section 3. "
        "The software, scripts and all raw run files are published with this article."))

    # ------------------------------------------------------------ 3
    x.append(H1("Results and Discussion"))
    x.append(H2("3.1. Signature cost"))
    ml, ed, ec = GO["mldsa65-gopure"], GO["ed25519"], GO["ecdsa-p256"]
    oml, oed, oec = OSSL["mldsa65 (OpenSSL)"], OSSL["ed25519 (OpenSSL)"], OSSL["ecdsa-p256 (OpenSSL)"]
    x.append(P(
        f"Table 3 lists the cost of one operation on the gateway core. ML-DSA-65 signing took a median of "
        f"{f0(ml['sign']['median_us'])} µs in the Go implementation, about {ml['sign']['median_us'] / ed['sign']['median_us']:.0f} "
        f"times the cost of Ed25519, while verification took {f0(ml['verify']['median_us'])} µs, close to ECDSA. "
        f"OpenSSL's implementation signed in {f0(oml['sign']['median_us'])} µs, so the Go implementation is not slower "
        f"than this reference. By Equation (1), signing alone limits C2 to about {f0(n['sign'] and 1e6 / ml['sign']['median_us'])} "
        "requests/s per gateway core."))
    x.append(table(["Scheme", "Sig. (B)", "Sign (µs)", "Verify (µs)"], [
        ["ECDSA P-256, Go", f0(ec["signature_bytes"]), f1(ec["sign"]["median_us"]), f1(ec["verify"]["median_us"])],
        ["Ed25519, Go", f0(ed["signature_bytes"]), f1(ed["sign"]["median_us"]), f1(ed["verify"]["median_us"])],
        ["ML-DSA-65, Go", f0(ml["signature_bytes"]), f1(ml["sign"]["median_us"]), f1(ml["verify"]["median_us"])],
        ["ECDSA P-256, OpenSSL", f0(oec["signature_bytes"]), f1(oec["sign"]["median_us"]), f1(oec["verify"]["median_us"])],
        ["Ed25519, OpenSSL", f0(oed["signature_bytes"]), f1(oed["sign"]["median_us"]), f1(oed["verify"]["median_us"])],
        ["ML-DSA-65, OpenSSL", f0(oml["signature_bytes"]), f1(oml["sign"]["median_us"]), f1(oml["verify"]["median_us"])],
    ], [2.2, 0.9, 1.0, 1.0], "Signature cost per operation on the gateway core (median)"))

    x.append(H2("3.2. Translation overhead"))
    t7 = [row("C0", c=c, pl=p) for p in PLS for c in [10]]
    x.append(P(
        "Table 4 breaks down the time the gateway spends on each request in C0 at 10 clients. Parsing JSON and mapping "
        f"it to Protobuf took a few microseconds, from {f1(t7[0].stage_parse_us + t7[0].stage_map_us)} µs at "
        f"{PLS[0]} bytes to {f1(t7[-1].stage_parse_us + t7[-1].stage_map_us)} µs at {PLS[-1]:,} bytes. Almost all "
        "of the gateway time was spent forwarding the call and waiting for the backend, which shares a core with the "
        "load generator. The protocol translation itself is therefore not a bottleneck; the cost lies in "
        "cryptography and in the round trip to the backend."))
    x.append(table(["Payload (B)", "Parse (µs)", "Map (µs)", "Forward (µs)", "CPU/req (µs)"], [
        [f0(p), f1(r.stage_parse_us), f1(r.stage_map_us), f0(r.stage_forward_us), f0(r.gw_cpu_us_per_req)] for p, r in zip(PLS, t7)
    ], [1.0, 0.9, 0.9, 1.0, 1.0], "Gateway stage times in C0, 10 clients (median)"))

    x.append(H2("3.3. Throughput and latency"))
    x.append(P(
        f"Figure 2 and Table 5 show throughput and tail latency for a 128-byte payload. C1 reached {f0(r1.rps)} "
        f"requests/s at {cmax} clients, {n['c1pct']:.0f}% of C0's {f0(r0.rps)} requests/s. Hybrid key exchange only "
        "runs when a connection opens, and the gateway reuses pooled HTTP/2 connections, so its cost disappears in "
        f"steady state. C2 reached {f0(r2.rps)} requests/s, {n['c2pct']:.0f}% of C0, with the gateway core saturated "
        f"and {f0(r2.gw_cpu_us_per_req)} µs of CPU per request against {f0(r0.gw_cpu_us_per_req)} µs in C0. Of the "
        f"difference of {f0(r2.gw_cpu_us_per_req - r0.gw_cpu_us_per_req)} µs, the signature itself accounts for "
        f"{f0(n['sign'])} µs (Table 3); the rest comes from encoding, encrypting and sending headers that are more than "
        f"ten times larger. The observed throughput stays below the bound of Equation (1). Its p99 latency rose from {f1(r0.lat_p99_ms)} ms to {f1(r2.lat_p99_ms)} ms as requests queued "
        "for the signing core."))
    rows4 = []
    for c in CL:
        for cfg in ["C0", "C1", "C2", "C3"]:
            r = row(cfg, c=c)
            rows4.append([f"{cfg}, {int(c)}", f0(r.rps), f2(r.lat_p50_ms), f2(r.lat_p99_ms), f0(r.gw_cpu_us_per_req)])
    x.append(table(["Config, clients", "Req/s", "p50 (ms)", "p99 (ms)", "CPU/req (µs)"], rows4,
                   [1.25, 0.9, 0.85, 0.85, 1.0], "Throughput, latency and gateway CPU, 128-byte payload (median)"))
    x.append(figure(f"{FIGS}/fig2_closed.png", "Throughput and p99 latency by configuration, 128-byte payload; whiskers show 95% confidence intervals"))
    r3_10, r2_10 = row("C3", c=10), row("C2", c=10)
    x.append(P(
        f"C3 depended strongly on load. At {cmax} clients it reached {f0(r3.rps)} requests/s, {n['c3pct']:.0f}% of C0 "
        f"and {r3.rps / r2.rps:.1f} times C2, because one signature covered many requests. At 10 clients it reached "
        f"only {f0(r3_10.rps)} requests/s against {f0(r2_10.rps)} for C2. With ten clients a batch can never hold more "
        "than ten requests, so batches closed on the 5 ms timer and every request waited for it."))
    big = PLS[-1]
    x.append(P(
        f"Table 6 shows the effect of payload size. Larger payloads lowered C0 and C1 throughput, from "
        f"{f0(row('C0', c=cmax).rps)} requests/s at {PLS[0]} bytes to {f0(row('C0', c=cmax, pl=big).rps)} at {big:,} "
        "bytes, because more bytes had to be parsed, re-encoded and encrypted. C2 changed least, since signing "
        "dominated its cost regardless of payload, and the ordering of the four configurations was the same at every "
        "size."))
    rows6 = []
    for cfg in ["C0", "C1", "C2", "C3"]:
        rows6.append([cfg] + [f0(row(cfg, c=cmax, pl=p).rps) for p in PLS])
    x.append(table(["Config"] + [f"{p:,} B" for p in PLS], rows6, [1.0] + [1.0] * len(PLS),
                   f"Throughput (req/s) by payload size, {cmax} clients (median)"))
    o = lambda cfg, rt: row(cfg, mode="open", rate=rt)
    rmax = RATES[-1]
    x.append(P(
        "Figure 3 shows the open-loop results, which reveal where each configuration stops keeping up. C0 and C1 "
        f"served every offered load up to the highest rate tested, {int(rmax):,} requests/s, with p99 latency of "
        f"{f1(o('C0', rmax).lat_p99_ms)} and {f1(o('C1', rmax).lat_p99_ms)} ms. C2 still served 1,000 requests/s, but "
        f"its p99 latency had risen to {f0(o('C2', 1000).lat_p99_ms)} ms; at 1,500 requests/s it completed only "
        f"{f0(o('C2', 1500).rps)} requests/s and p99 latency grew to {o('C2', 1500).lat_p99_ms / 1000:.1f} s, because "
        "requests arrived faster than the gateway could sign them. C3 kept up with every offered load, with p99 "
        f"latency between {f1(o('C3', RATES[0]).lat_p99_ms)} and {f1(o('C3', rmax).lat_p99_ms)} ms; its latency floor "
        "is set by the batch window rather than by load."))
    x.append(figure(f"{FIGS}/fig3_open.png", "p99 latency against offered load in the open-loop workload"))

    x.append(H2("3.4. Batch signing trade-off"))
    gb = G.sort_values("rps", ascending=False)
    x.append(P(
        f"Table 7 shows how the batch window and size affect C3 at 50 clients. Short windows performed best: "
        f"*T* = {gb.iloc[0].batch_window_ms:g} ms with *B* = {int(gb.iloc[0].batch_max)} reached "
        f"{gb.iloc[0].rps_pct_of_C0:.0f}% of C0's throughput and added {gb.iloc[0].added_p50_ms_vs_C0:.1f} ms of median "
        f"latency, while *T* = {gb.iloc[-1].batch_window_ms:g} ms reached only {gb.iloc[-1].rps_pct_of_C0:.0f}%. With 50 "
        "clients, at most 50 requests can be waiting, so batches larger than that never fill and the window alone "
        "decides the latency. A practical rule follows: the batch size should not exceed the expected number of "
        "concurrent requests, and the window should be as short as the signing rate allows."))
    x.append(table(["T (ms)", "B", "Avg. batch", "% of C0", "Added p50 (ms)"], [
        [f"{r.batch_window_ms:g}", f0(r.batch_max), f1(r.avg_batch_size), f0(r.rps_pct_of_C0), f2(r.added_p50_ms_vs_C0)]
        for r in G.sort_values(["batch_window_ms", "batch_max"]).itertuples()
    ], [0.8, 0.7, 1.0, 0.9, 1.2], "Batch signing settings in C3, 50 clients, 128-byte payload (median)", align=["left"] + ["right"] * 4))
    x.append(P(
        "Figure 4 plots the same data. Throughput falls and latency rises almost linearly with the window once batches "
        "stop filling before the timer expires, and the batch size matters only while it is smaller than the number of "
        "requests in flight."))
    x.append(figure(f"{FIGS}/fig5_batch.png", "Effect of batch window and size on C3 throughput and added median latency, 50 clients"))

    x.append(H2("3.5. Verification cost at the backend"))
    b0, b2, b3 = (BE.loc[(c, float(cmax))] for c in ["C0", "C2", "C3"])
    x.append(P(
        "Signatures also cost the receiving service. The backend verified each ML-DSA-65 signature in a median of "
        f"{f0(b2.be_verify_p50_us)} µs. In C2 it verifies one signature per request, and its CPU time per request rose "
        f"from {f0(b0.be_cpu_us_per_req)} µs in C0 to {f0(b2.be_cpu_us_per_req)} µs, which includes decoding the large "
        "header and the replay check. In C3 it verifies one signature per batch and otherwise only recomputes a Merkle "
        f"path, so its cost was {f0(b3.be_cpu_us_per_req)} µs per request at {cmax} clients. Table 8 summarises these "
        "figures. Batching therefore lowers the verification burden of every service that receives signed requests, "
        "not only the signing load on the gateway."))
    x.append(table(["Config", "Verify (µs)", "Verifications/req", "Backend CPU/req (µs)"], [
        [c, f0(b.be_verify_p50_us) if b.be_verify_p50_us > 0 else "–", f"{b.signatures_per_req:.3f}", f0(b.be_cpu_us_per_req)]
        for c, b in [(c, BE.loc[(c, float(cmax))]) for c in ["C0", "C1", "C2", "C3"]]
    ], [0.7, 1.0, 1.2, 1.4], f"Verification cost at the backend, 128-byte payload, {cmax} clients (median)"))

    x.append(H2("3.6. Metadata headroom"))
    x.append(P(
        f"Each C2 request reached the backend with {f0(n['meta_c2'])} bytes of HTTP/2 headers, against "
        f"{f0(n['meta_c0'])} bytes in C0. Figure 5 shows what happens when other metadata is added. C2 requests were "
        f"accepted with up to {ns['last_ok_c2']:,} extra bytes and all rejected from {ns['first_fail_c2']:,} bytes, "
        f"leaving about {8192 - n['meta_c2']:,.0f} bytes for every other header under gRPC's default limit. In C3 only "
        "the first request of a batch carries the signature, but when that request is rejected the whole batch fails "
        f"verification, so C3 failed from {ns['first_fail_c3']:,} extra bytes. Distributed tracing and authorisation "
        "tokens can easily use a few kilobytes, so deployments that sign individual messages must raise the "
        "metadata limit or move the signature into the message body. ML-DSA-87, with 4,627-byte signatures, would "
        "leave even less room."))
    hb = {c: float(H[(H["config"] == c) & (H["pad_bytes"] == 0)]["metadata_bytes_max"].iloc[0]) for c in ["C0", "C2", "C3"]}
    hb["C1"] = hb["C0"]
    rows7 = []
    for cfg in ["C0", "C1", "C2", "C3"]:
        r = row(cfg, c=cmax)
        rows7.append([cfg, f0(hb[cfg]), f0(r.internal_bytes_out_per_req), f0(r.public_bytes_in_per_req), f"{r.signatures_per_req:.3f}"])
    x.append(table(["Config", "Max. metadata (B)", "Internal out (B/req)", "Public in (B/req)", "Signatures/req"], rows7,
                   [0.7, 1.1, 1.1, 1.05, 1.0], f"Metadata and bytes per request, 128-byte payload, {cmax} clients"))
    x.append(P(
        "Table 9 shows that the public link carried the same number of bytes per request in every configuration, so "
        "the choice of internal authentication is invisible to clients. On the internal link, C2 sent about "
        f"{row('C2', c=cmax).internal_bytes_out_per_req / max(row('C0', c=cmax).internal_bytes_out_per_req, 1):.0f} times "
        "as many bytes per request as C0, while C3 sent a fraction of that because most requests carry only the root "
        "hash and audit path."))
    x.append(figure(f"{FIGS}/fig4_headroom.png", "Header list size against additional metadata; hollow markers show rejected requests"))

    x.append(H2("3.7. Discussion and limitations"))
    sig = T[(T["metric"] == "rps") & (T["mode"] == "closed")]
    nsig = int((sig["mwu_p_holm"] < 0.05).sum())
    c01 = sig[sig["pair"] == "C0 vs C1"]
    others = sig[sig["pair"].isin(["C0 vs C2", "C0 vs C3", "C1 vs C2", "C1 vs C3"])]
    c23 = sig[sig["pair"] == "C2 vs C3"]
    x.append(P(
        f"With {n['reps']} repetitions per condition, {nsig} of {len(sig)} pairwise throughput comparisons were "
        f"significant after Holm correction. None of the {len(c01)} comparisons between C0 and C1 was significant "
        f"(Holm-adjusted p ≥ {c01['mwu_p_holm'].min():.2f}), while all {len(others)} comparisons of C2 or C3 with C0 or "
        f"C1 were, with rank-biserial correlations of {others['rank_biserial'].abs().min():.2f} in absolute value. C2 "
        f"and C3 differed significantly in {int((c23['mwu_p_holm'] < 0.05).sum())} of {len(c23)} conditions. "
        "The answer to the second research question is therefore clear: channel-level post-quantum protection costs "
        "almost nothing in steady state, while message-level signing costs an order of magnitude in throughput unless "
        "it is batched. Message-level signing is still worth its cost where requests cross several hops after TLS "
        "terminates, or where each request must be auditable on its own."))
    rss0, rss2 = row("C0", c=cmax).gw_rss_mb, row("C2", c=cmax).gw_rss_mb
    x.append(P(
        "The results also support simple capacity planning. With the measured signing time, one gateway core can "
        f"sign at most about {f0(1e6 / n['sign'])} requests/s (Equation 1), so a service that must sign every request "
        "at a peak rate *R* needs roughly *R* divided by that figure in extra cores, on top of the translation work. "
        f"Batching changes this ratio: at {cmax} clients C3 made one signature for about "
        f"{1 / max(row('C3', c=cmax).signatures_per_req, 1e-9):.0f} requests. A faster ML-DSA implementation would raise "
        "the per-core bound in proportion to its speed-up; this was not measured here. Memory was not a constraint: "
        f"the gateway's resident memory stayed between about 15 and {max(rss0, rss2):.0f} MB in every configuration, "
        f"with C2 using the most ({rss2:.0f} MB against {rss0:.0f} MB in C0 at {cmax} clients) because of its larger "
        "headers."))
    x.append(P(
        "Batch signing has a robustness cost that per-request signing does not. Every request in a batch depends on "
        "the one that carries the root signature, so if that request is lost or rejected, the whole batch fails, as "
        "the headroom experiment showed in Section 3.6. Sending the signature with every request in the batch removes "
        "this dependency but gives up most of the bandwidth saving; deciding between the two depends on how reliable "
        "the internal network is. In either form, each request remains bound to its own content by its Merkle path, "
        "so a modified request is still rejected."))
    x.append(P(
        "These results come from one 2-vCPU virtual machine on loopback. The backend and load generator share a core, "
        "so absolute throughput is lower than on separate machines, but all configurations shared the same "
        "conditions. Network delay was not emulated; it would add a similar round-trip time to every configuration "
        "and hide part of the latency differences, but not the CPU cost. The ML-DSA-65 implementation is not "
        "vectorised, and optimised implementations would sign faster and narrow the gap between C2 and C0. C1 used "
        "classical certificates because the TLS stack does not support ML-DSA certificates. Only a single unary "
        "method was tested."))

    # ------------------------------------------------------------ 4
    x.append(H1("Conclusion"))
    x.append(P(
        "This study measured the cost of post-quantum authentication in a gateway that translates REST/JSON requests "
        "into gRPC calls. The translation itself took only microseconds per request. Hybrid post-quantum key exchange "
        f"on pooled internal connections left throughput unchanged, at {n['c1pct']:.0f}% of the classical baseline. "
        f"Signing every request with ML-DSA-65 reduced throughput to {n['c2pct']:.0f}% of the baseline because each "
        f"signature took about {n['sign']:.0f} µs of gateway CPU. Merkle batch signing recovered "
        f"{n['c3pct']:.0f}% at {cmax} concurrent clients, but it helped only when enough requests were in "
        f"flight to fill a batch. Each signature raised the request metadata to {n['meta_c2'] / 1000:.1f} KB, leaving "
        f"about {(8192 - n['meta_c2']) / 1000:.1f} KB for other headers under gRPC's default 8 KB limit."))
    x.append(P(
        "Gateways that need post-quantum protection on internal links should start with hybrid key exchange, which "
        "is nearly free. Message-level signatures should be added only where multi-hop integrity or per-request "
        "auditability is required, together with batching sized to the expected concurrency and a raised metadata "
        "limit. Future work should repeat the measurements on separate machines with emulated network conditions, "
        "evaluate optimised and hardware-accelerated ML-DSA implementations, FN-DSA and SLH-DSA, include ML-DSA "
        "certificates in the internal TLS channel, and test streaming RPCs."))

    # ------------------------------------------------------------ acknowledgement
    x.append(H1("Acknowledgement", numbered=False))
    x.append(P(
        "[Funding source, if any.] The code and raw data are available at "
        "https://github.com/budisentana/grpc-gateway-bench [add archive DOI]."))
    x.append(H1("References", numbered=False))
    return "".join(x)


references = [
    "M. Niswar *et al.*, “Performance evaluation of microservices communication with REST, GraphQL, and gRPC,” *Int. J. Electron. Telecommun.*, 2024, doi: 10.24425/ijet.2024.149562.",
    "P. Iwanowski, J. Jarmoszewicz, and M. Plechawska-Wójcik, “Analysis of the performance and scalability of microservices depending on the communication technology,” *J. Comput. Sci. Inst.*, vol. 33, pp. 323–330, 2024.",
    "M. Z. Ain *et al.*, “Comparative performance analysis of gRPC and REST API under various traffic conditions and data sizes using a quantitative approach,” *J. Appl. Informatics Comput.*, vol. 9, no. 2, pp. 450–457, 2025.",
    "M. Bolanowski *et al.*, “Efficiency of REST and gRPC realizing communication tasks in microservice-based ecosystems,” arXiv:2208.00682, 2022.",
    "Envoy Project, “gRPC-JSON transcoder,” Envoy Proxy documentation. [Online]. Available: https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/grpc_json_transcoder_filter",
    "P. W. Shor, “Polynomial-time algorithms for prime factorization and discrete logarithms on a quantum computer,” *SIAM J. Comput.*, vol. 26, no. 5, pp. 1484–1509, 1997.",
    "National Institute of Standards and Technology, “Module-lattice-based key-encapsulation mechanism standard,” FIPS 203, Aug. 2024, doi: 10.6028/NIST.FIPS.203.",
    "National Institute of Standards and Technology, “Module-lattice-based digital signature standard,” FIPS 204, Aug. 2024, doi: 10.6028/NIST.FIPS.204.",
    "D. Moody *et al.*, “Transition to post-quantum cryptography standards,” NIST IR 8547, National Institute of Standards and Technology, Oct. 2026.",
    "D. Joseph *et al.*, “Transitioning organizations to post-quantum cryptography,” *Nature*, vol. 605, no. 7909, pp. 237–243, 2022, doi: 10.1038/s41586-022-04623-2.",
    "D. Adrian, D. Benjamin, B. Beck, and D. O’Brien, “A new path for Kyber on the web,” Google Online Security Blog, Sep. 2024. [Online]. Available: https://security.googleblog.com/2024/09/a-new-path-for-kyber-on-web.html",
    "D. Adrian, B. Beck, D. Benjamin, and D. O’Brien, “Advancing our amazing bet on asymmetric cryptography,” Chromium Blog, May 2024. [Online]. Available: https://blog.google/chromium/advancing-our-amazing-bet-on-asymmetric/",
    "C. Paquin, D. Stebila, and G. Tamvada, “Benchmarking post-quantum cryptography in TLS,” in *Proc. PQCrypto 2020*, LNCS vol. 12100, Springer, 2020, pp. 72–91.",
    "D. Sikeridis, P. Kampanakis, and M. Devetsikiotis, “Post-quantum authentication in TLS 1.3: A performance study,” in *Proc. NDSS*, 2020, doi: 10.14722/ndss.2020.24203.",
    "M. Sosnowski *et al.*, “The performance of post-quantum TLS 1.3,” in *Companion of the 19th Int. Conf. Emerging Networking Experiments and Technologies (CoNEXT ’23)*, 2023, doi: 10.1145/3624354.3630585.",
    "S. Paul, Y. Kuzovkova, N. Lahr, and R. Niederhagen, “Mixed certificate chains for the transition to post-quantum authentication in TLS 1.3,” in *Proc. ACM Asia Conf. Computer and Communications Security (ASIA CCS ’22)*, 2022. [Online]. Available: https://eprint.iacr.org/2021/1447",
    "P. Schwabe, D. Stebila, and T. Wiggers, “Post-quantum TLS without handshake signatures,” in *Proc. ACM CCS*, 2020, pp. 1461–1480, doi: 10.1145/3372297.3423350.",
    "C. Aguilar-Melchor *et al.*, “Batch signatures, revisited,” in *Topics in Cryptology – CT-RSA 2024*, LNCS vol. 14643, Springer, 2024, pp. 163–186, doi: 10.1007/978-3-031-58868-6_7.",
    "R. A. Faval, R. Moreira, and F. de O. Silva, “Empowering mobile networks security resilience by using post-quantum cryptography,” arXiv:2603.28626, 2026.",
    "A. Olushola and S. P. Meenakshi, “Design and implementation of an authenticated post-quantum session protocol using ML-KEM (Kyber), ML-DSA (Dilithium), and AES-256-GCM,” *Front. Phys.*, vol. 13, art. 1723966, 2026, doi: 10.3389/fphy.2025.1723966.",
    "M. V. Nielsen, M. R. Kjeldsen, T. Turnip, and B. Andersen, “Post-quantum digital signature algorithms on IoT: Evaluating performance on LoRa ESP32 microcontroller,” in *Proc. 22nd Int. Conf. Security and Cryptography (SECRYPT)*, 2025, pp. 592–600, doi: 10.5220/0013508400003979.",
    "C. İnce, “Performance evaluation of ML-KEM and ML-DSA post-quantum algorithms in real-world IoT networks,” *Sakarya Univ. J. Comput. Inf. Sci.*, vol. 9, no. 4, pp. 1004–1011, 2026, doi: 10.35377/saucis.1874093.",
    "gRPC Authors, “GRPC_ARG_MAX_METADATA_SIZE,” gRPC Core channel arguments. [Online]. Available: https://grpc.github.io/grpc/core/group__grpc__arg__keys.html",
    "R. Peon and H. Ruellan, “HPACK: Header compression for HTTP/2,” RFC 7541, IETF, May 2015.",
    "gRPC Authors, “gRPC over HTTP2,” protocol specification. [Online]. Available: https://github.com/grpc/grpc/blob/master/doc/PROTOCOL-HTTP2.md",
    "M. Thomson and C. Benfield, “HTTP/2,” RFC 9113, IETF, Jun. 2022.",
]
