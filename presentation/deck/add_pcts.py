# -*- coding: utf-8 -*-
"""v4 -> v5: yuzdeleri slayta metin olarak koy. Grafiklere dokunmuyor.

11 ve 12'de etiketler barlarin hizasina oturuyor: bar merkezleri PNG'den
olculuyor, slayttaki kirpma (srcRect) ve resim kutusu uzerinden slayt
koordinatina cevriliyor.
"""
import re, zipfile
from PIL import Image

SRC = "/home/user/asil1/presentation/deck/ASELSAN-Sunum-v4.pptx"
DST = "/home/user/asil1/presentation/deck/ASELSAN-Sunum-v5.pptx"

SKY, ORANGE, MUTED = "58B0E8", "E8871F", "5B6478"
BARS = ((0x35, 0x5F, 0xA8), (0x58, 0xB0, 0xE8), (0xE8, 0x87, 0x1F))

z = zipfile.ZipFile(SRC)
out = {n: z.read(n) for n in z.namelist()}


def textbox(nid, x, y, cx, cy, runs, align="l", anchor="ctr"):
    """runs: (metin, punto, kalin, renk, italik) satirlari."""
    paras = ""
    for text, sz, bold, colour, italic in runs:
        paras += (
            '<a:p><a:pPr algn="%s"/><a:r><a:rPr lang="tr-TR" sz="%d" b="%d" i="%d"'
            ' dirty="0"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
            '<a:latin typeface="Segoe UI"/><a:cs typeface="Segoe UI"/></a:rPr>'
            '<a:t>%s</a:t></a:r></a:p>'
            % (align, sz, int(bold), int(italic), colour, text))
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="Yuzde %d"/>'
            '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr>'
            '<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            '<p:txBody><a:bodyPr wrap="square" rtlCol="0" anchor="%s">'
            '<a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>'
            % (nid, nid, x, y, cx, cy, anchor, paras))


def add(slide, shapes):
    key = "ppt/slides/slide%d.xml" % slide
    x = out[key].decode("utf-8")
    nid = max(int(v) for v in re.findall(r'<p:cNvPr id="(\d+)"', x)) + 1
    body = ""
    for i, (bx, by, bcx, bcy, runs) in enumerate(shapes):
        body += textbox(nid + i, bx, by, bcx, bcy, runs)
    out[key] = x.replace("</p:spTree>", body + "</p:spTree>").encode("utf-8")


def bar_rows(slide, png):
    """PNG'deki uc barin merkezini slayt koordinatina tasi."""
    im = Image.open(png).convert("RGB")
    W, H = im.size
    px = im.load()
    x = out["ppt/slides/slide%d.xml" % slide].decode("utf-8")
    pic = re.search(r"<p:pic>.*?</p:pic>", x, re.S).group(0)
    off = re.search(r'<a:off x="(\d+)" y="(\d+)"/><a:ext cx="(\d+)" cy="(\d+)"',
                    pic).groups()
    y0, cy = int(off[1]), int(off[3])
    crop = re.search(r"<a:srcRect([^>]*)/>", pic)
    attrs = dict(re.findall(r'(\w+)="(-?\d+)"', crop.group(1))) if crop else {}
    top = int(attrs.get("t", 0)) / 100000.0
    bot = int(attrs.get("b", 0)) / 100000.0
    span = 1.0 - top - bot
    out_y = []
    for colour in BARS:
        rows = [r for r in range(H)
                if sum(1 for c in range(0, W // 2, 4) if px[c, r] == colour) > 20]
        frac = ((rows[0] + rows[-1]) / 2.0 / H - top) / span
        out_y.append(int(round(y0 + frac * cy)))
    return out_y


FIG = "/home/user/asil1/presentation/figures/%s.png"
H = 420000

for slide, fig, x, cx, pcts, last in (
        (11, "res-express", 8550000, 3200000, (u"−72 %", u"−77 %"), u"hareketli bloğa göre −18 %"),
        (12, "res-stopping", 8720000, 3030000, (u"−47 %", u"−52 %"), u"hareketli bloğa göre −9 %")):
    navy, sky, orange = bar_rows(slide, FIG % fig)
    add(slide, [
        (x, navy - H - 220000, cx, H,
         [(u"sabit bloğa göre", 1200, False, MUTED, True)]),
        (x, sky - H // 2, cx, H, [(pcts[0], 2000, True, SKY, False)]),
        (x, orange - H // 2, cx, H, [(pcts[1], 2000, True, ORANGE, False)]),
        (x, orange + H // 2, cx, H, [(last, 1200, False, ORANGE, False)]),
    ])

# 14 - kuralin adim adim kazandirdigi, olculen degerlerden
add(14, [(8460000, 3250000, 3290000, 1300000, [
    (u"kuralın kazancı", 1200, False, MUTED, True),
    (u"duraksız  −32 %", 2000, True, ORANGE, False),
    (u"duraklamalı  −9 %", 2000, True, SKY, False)])])

with zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as w:
    for n in z.namelist():
        w.writestr(z.getinfo(n), out[n])
print("wrote", DST)
