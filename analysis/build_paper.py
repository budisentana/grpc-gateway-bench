"""Build the JACOST manuscript (.docx) from the journal template and the results.

Usage: python3 analysis/build_paper.py TEMPLATE.docx RESULTS_DIR FIG_DIR OUT.docx
"""
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

import pandas as pd

TEMPLATE, RES, FIGS, OUT = sys.argv[1:5]

# ---------------------------------------------------------------- data
data = json.load(open(os.path.join(RES, "summary", "results.json")))
S = pd.DataFrame(data["summary"])
G = pd.DataFrame(data["batch_grid"])
H = pd.DataFrame(data["headroom"])
T = pd.DataFrame(data["tests"])
micro = {m.get("library", "go"): {r["scheme"]: r for r in m["results"]} for m in data["microbench"]}
GO = micro["go"]
OSSL = [v for k, v in micro.items() if k != "go"][0]
cross = open(os.path.join(RES, "crosscheck.txt")).read().strip().split(" cases")[0]


def row(cfg, mode="closed", c=None, pl=128, rate=None):
    d = S[(S["config"] == cfg) & (S["mode"] == mode) & (S["payload"] == pl)]
    d = d[d["concurrency"] == c] if c is not None else d[d["offered_rate"] == rate]
    if d.empty:
        raise KeyError((cfg, mode, c, pl, rate))
    return d.iloc[0]


def f0(x):
    return f"{x:,.0f}"


def f1(x):
    return f"{x:,.1f}"


def f2(x):
    return f"{x:,.2f}"


CL = sorted(S[S["mode"] == "closed"]["concurrency"].dropna().unique())
CMAX = int(max(CL))
PLS = sorted(S[S["mode"] == "closed"]["payload"].unique())
RATES = sorted(S[S["mode"] == "open"]["offered_rate"].dropna().unique())
REPS = int(S[S["mode"] == "closed"]["reps"].min())
r0, r1, r2, r3 = (row(c, c=CMAX) for c in ["C0", "C1", "C2", "C3"])
r0_10, r2_10, r3_10 = (row(c, c=10) for c in ["C0", "C2", "C3"])
ml_go, ml_os = GO["mldsa65-gopure"], OSSL["mldsa65 (OpenSSL)"]
ed_go, ec_go = GO["ed25519"], GO["ecdsa-p256"]
h2 = H[(H["config"] == "C2")].sort_values("pad_bytes")
meta_c2 = float(h2[h2["pad_bytes"] == 0]["metadata_bytes_max"].iloc[0])
meta_c0 = float(H[(H["config"] == "C0") & (H["pad_bytes"] == 0)]["metadata_bytes_max"].iloc[0])
first_fail_c2 = int(h2[h2["completed_ok"] == 0]["pad_bytes"].min())
last_ok_c2 = int(h2[h2["completed_ok"] > 0]["pad_bytes"].max())
h3 = H[(H["config"] == "C3")].sort_values("pad_bytes")
first_fail_c3 = int(h3[h3["completed_ok"] == 0]["pad_bytes"].min())
gbest = G.sort_values("rps", ascending=False).iloc[0]
gworst = G.sort_values("rps").iloc[0]


RUNS = pd.read_csv(os.path.join(RES, "summary", "runs.csv"))
_m = RUNS[(RUNS["mode"] == "closed") & (RUNS["payload"] == 128) & (~RUNS["file"].str.contains("C3grid"))
          & (RUNS["label"] != "headroom")].copy()
_m["be_cpu_us_per_req"] = _m["be_cpu_pct"] / 100 * 1e6 / _m["rps"]
BE = _m.groupby(["config", "concurrency"])[["be_verify_p50_us", "be_cpu_us_per_req", "signatures_per_req"]].median()


def open_knee(cfg):
    """Highest offered rate served with p99 under 50 ms and under 1% errors."""
    d = S[(S["mode"] == "open") & (S["config"] == cfg)].sort_values("offered_rate")
    ok = d[(d["lat_p99_ms"] < 50) & (d["error_rate_pct"] < 1) & (d["rps"] > 0.97 * d["offered_rate"])]
    return int(ok["offered_rate"].max()) if not ok.empty else 0


KNEE = {c: open_knee(c) for c in ["C0", "C1", "C2", "C3"]}
sig_ceiling = 1e6 / ml_go["sign"]["median_us"]

numbers = dict(
    reps=REPS, cmax=CMAX, c0=r0.rps, c1=r1.rps, c2=r2.rps, c3=r3.rps, c2pct=100 * r2.rps / r0.rps,
    c3pct=100 * r3.rps / r0.rps, c1pct=100 * r1.rps / r0.rps, p99_0=r0.lat_p99_ms, p99_2=r2.lat_p99_ms,
    p99_3=r3.lat_p99_ms, c3_10=r3_10.rps, c2_10=r2_10.rps, sign=ml_go["sign"]["median_us"],
    verify=ml_go["verify"]["median_us"], ossl_sign=ml_os["sign"]["median_us"], meta_c2=meta_c2, meta_c0=meta_c0,
    fail=first_fail_c2, knee=KNEE, gbest=dict(gbest), cpu2=r2.gw_cpu_us_per_req, cpu0=r0.gw_cpu_us_per_req,
)
print(json.dumps(numbers, indent=1, default=str))

# ---------------------------------------------------------------- XML helpers
MD = re.compile(r"(\*[^*]+\*|\^[^^]+\^|`[^`]+`)")


def runs(text, base=""):
    out = []
    for part in MD.split(text):
        if not part:
            continue
        rpr = base
        if part.startswith("*") and part.endswith("*"):
            part, rpr = part[1:-1], base + "<w:i/><w:iCs/>"
        elif part.startswith("^") and part.endswith("^"):
            part, rpr = part[1:-1], base + '<w:vertAlign w:val="superscript"/>'
        elif part.startswith("`") and part.endswith("`"):
            part, rpr = part[1:-1], base + '<w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/><w:sz w:val="18"/>'
        out.append(f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
    return "".join(out)


def P(text, ppr='<w:spacing w:after="120"/>', base=""):
    return f"<w:p><w:pPr>{ppr}</w:pPr>{runs(text, base)}</w:p>"


def H1(text, numbered=True):
    num = '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr><w:ind w:left="284" w:hanging="284"/>' if numbered else ""
    return f'<w:p><w:pPr><w:pStyle w:val="Heading1"/>{num}</w:pPr>{runs(text)}</w:p>'


def H2(text):
    return (f'<w:p><w:pPr><w:pStyle w:val="Heading2"/><w:spacing w:before="120" w:after="120"/><w:rPr><w:i w:val="0"/></w:rPr></w:pPr>'
            f'{runs(text, "<w:i w:val=\"0\"/>")}</w:p>')


def caption(kind, title):
    seq = "Tabel_" if kind == "Table" else "Gambar"
    after = '<w:keepNext/><w:spacing w:after="60"/>' if kind == "Table" else '<w:spacing w:after="160"/>'
    return (f'<w:p><w:pPr><w:pStyle w:val="Caption"/>{after}</w:pPr><w:r><w:t xml:space="preserve">{kind} </w:t></w:r>'
            f'<w:fldSimple w:instr=" SEQ {seq} \\* ARABIC "><w:r><w:t>{{N}}</w:t></w:r></w:fldSimple>'
            f'<w:r><w:t xml:space="preserve">. {escape(title)}</w:t></w:r></w:p>')


COLW = 4480  # one column in twips


def table(header, rows, widths, title, align=None):
    n = len(header)
    widths = [int(COLW * w / sum(widths)) for w in widths]
    align = align or (["left"] + ["right"] * (n - 1))

    def cell(text, w, top=None, bottom=None, jc="left", bold=False, keep=True):
        b = ""
        if top:
            b += f'<w:top w:val="single" w:sz="{top}" w:space="0" w:color="000000"/>'
        if bottom:
            b += f'<w:bottom w:val="single" w:sz="{bottom}" w:space="0" w:color="000000"/>'
        borders = f"<w:tcBorders>{b}</w:tcBorders>" if b else ""
        rpr = '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="16"/><w:szCs w:val="16"/>' + ("<w:b/>" if bold else "")
        return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{borders}<w:tcMar><w:left w:w="57" w:type="dxa"/><w:right w:w="57" w:type="dxa"/></w:tcMar></w:tcPr>'
                f'<w:p><w:pPr><w:pStyle w:val="TableCaption"/>{"<w:keepNext/>" if keep else ""}<w:jc w:val="{jc}"/></w:pPr>{runs(str(text), rpr)}</w:p></w:tc>')

    xml = [caption("Table", title),
           f'<w:tbl><w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/>'
           f'<w:tblLook w:val="0000" w:firstRow="0" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="0" w:noVBand="0"/></w:tblPr>'
           f'<w:tblGrid>{"".join(f"<w:gridCol w:w=\"{w}\"/>" for w in widths)}</w:tblGrid>']
    xml.append('<w:tr><w:trPr><w:tblHeader/><w:jc w:val="center"/></w:trPr>' +
               "".join(cell(h, w, top=12, bottom=4, jc=("left" if a == "left" else "center")) for h, w, a in zip(header, widths, align)) + "</w:tr>")
    for i, r in enumerate(rows):
        last = i == len(rows) - 1
        xml.append('<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>' +
                   "".join(cell(v, w, bottom=12 if last else None, jc=a, keep=not last) for v, w, a in zip(r, widths, align)) + "</w:tr>")
    xml.append("</w:tbl>")
    xml.append('<w:p><w:pPr><w:spacing w:after="60"/></w:pPr></w:p>')
    return "".join(xml)


FIGS_USED = []


def figure(path, title, width_in=3.1):
    from PIL import Image
    im = Image.open(path)
    cx = int(width_in * 914400)
    cy = int(cx * im.height / im.width)
    rid = f"rIdFig{len(FIGS_USED) + 1}"
    FIGS_USED.append((rid, path))
    n = len(FIGS_USED)
    drawing = (f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
               f'<wp:docPr id="{100 + n}" name="Figure {n}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>'
               f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
               f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{100 + n}" name="fig{n}.png"/><pic:cNvPicPr/></pic:nvPicPr>'
               f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
               f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
               f'</a:graphicData></a:graphic></wp:inline></w:drawing>')
    return (f'<w:p><w:pPr><w:keepNext/><w:spacing w:before="60" w:after="60"/><w:jc w:val="center"/></w:pPr><w:r>{drawing}</w:r></w:p>'
            + caption("Figure", title))


def code(lines):
    rpr = '<w:rFonts w:ascii="Lucida Console" w:hAnsi="Lucida Console"/><w:sz w:val="16"/><w:szCs w:val="16"/>'
    out = []
    for i, ln in enumerate(lines):
        after = "120" if i == len(lines) - 1 else "0"
        keep = "" if i == len(lines) - 1 else "<w:keepNext/>"
        out.append(f'<w:p><w:pPr>{keep}<w:spacing w:after="{after}"/><w:ind w:left="170"/><w:jc w:val="left"/></w:pPr>'
                   f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(ln)}</w:t></w:r></w:p>')
    return "".join(out)


def equation(text, num):
    return (f'<w:p><w:pPr><w:tabs><w:tab w:val="center" w:pos="2240"/><w:tab w:val="right" w:pos="4480"/></w:tabs><w:spacing w:after="120"/><w:jc w:val="left"/></w:pPr>'
            f'<w:r><w:tab/></w:r>{runs(text)}<w:r><w:tab/><w:t>({num})</w:t></w:r></w:p>')


def ref(text):
    return f'<w:p><w:pPr><w:pStyle w:val="Rujukan"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="4"/></w:numPr><w:ind w:left="284" w:hanging="284"/><w:jc w:val="left"/></w:pPr>{runs(text)}</w:p>'


# ---------------------------------------------------------------- content
from paper_content import front, body, references  # noqa: E402

front_xml = front(numbers, P, runs)
body_xml = body(locals())
refs_xml = "".join(ref(r) for r in references)

# number captions in order
counters = {"Table": 0, "Figure": 0}


def number_caps(xml):
    def rep(m):
        kind = m.group(1)
        counters[kind] += 1
        return m.group(0).replace("{N}", str(counters[kind]))
    return re.sub(r'<w:t xml:space="preserve">(Table|Figure) </w:t></w:r><w:fldSimple[^>]*><w:r><w:t>\{N\}</w:t>', rep, xml)


body_xml = number_caps(body_xml)

# ---------------------------------------------------------------- assemble
tmp = tempfile.mkdtemp()
with zipfile.ZipFile(TEMPLATE) as z:
    z.extractall(tmp)
doc_path = os.path.join(tmp, "word", "document.xml")
x = open(doc_path, encoding="utf-8").read()
paras = list(re.finditer(r"<w:p[ >](?:(?!<w:p[ >]).)*?</w:p>|<w:tbl>.*?</w:tbl>", x, re.S))


def find_idx(pred):
    for i, m in enumerate(paras):
        if pred(m.group(0)):
            return i
    raise ValueError("not found")


i_title = find_idx(lambda s: "Judul" in s and 'w:val="Subtitle"' in s)
i_sect1 = find_idx(lambda s: "<w:sectPr" in s)
i_sect2 = max(i for i, m in enumerate(paras) if "<w:sectPr" in m.group(0))
head = x[: paras[i_title].start()]
sect1 = paras[i_sect1].group(0)
tail = x[paras[i_sect2].start():]
new = head + front_xml + sect1 + body_xml + refs_xml + tail
open(doc_path, "w", encoding="utf-8").write(new)

# images + relationships
rels_path = os.path.join(tmp, "word", "_rels", "document.xml.rels")
rels = open(rels_path).read()
for rid, path in FIGS_USED:
    name = "qsbg_" + os.path.basename(path)
    shutil.copy(path, os.path.join(tmp, "word", "media", name))
    rels = rels.replace("</Relationships>",
                        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/></Relationships>')
open(rels_path, "w").write(rels)
ct_path = os.path.join(tmp, "[Content_Types].xml")
ct = open(ct_path).read()
if 'Extension="png"' not in ct:
    ct = ct.replace("<Types ", "<Types ").replace("</Types>", '<Default Extension="png" ContentType="image/png"/></Types>')
    open(ct_path, "w").write(ct)
# document properties: clear template title/author
core = os.path.join(tmp, "docProps", "core.xml")
if os.path.exists(core):
    c = open(core).read()
    c = re.sub(r"<dc:title>.*?</dc:title>", "<dc:title>Measuring the Cost of Post-Quantum Authentication in a REST-to-gRPC Gateway</dc:title>", c)
    c = re.sub(r"<dc:creator>.*?</dc:creator>", "<dc:creator></dc:creator>", c)
    c = re.sub(r"<cp:lastModifiedBy>.*?</cp:lastModifiedBy>", "<cp:lastModifiedBy></cp:lastModifiedBy>", c)
    open(core, "w").write(c)

if os.path.exists(OUT):
    os.remove(OUT)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(tmp):
        for f in files:
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, tmp))
shutil.rmtree(tmp)
print("wrote", OUT)
