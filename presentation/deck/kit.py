# -*- coding: utf-8 -*-
"""pptx duzenleme takimi - work/ altindaki acilmis pakette calisir.

Slayt POZISYONU ile dosya adi ayni olmak zorunda degil, o yuzden her sey
pozisyondan cozuluyor (presentation.xml'in sldIdLst sirasi).
"""
import os
import re
import shutil
from xml.sax.saxutils import escape
from PIL import Image

W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "work")
CT = os.path.join(W, "[Content_Types].xml")


def _read(p):
    return open(os.path.join(W, p), encoding="utf-8").read()


def _write(p, s):
    open(os.path.join(W, p), "w", encoding="utf-8").write(s)


def order():
    """Slayt dosyalari, sunum sirasiyla."""
    rels = _read("ppt/_rels/presentation.xml.rels")
    tgt = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="slides/(slide\d+\.xml)"', rels))
    pres = _read("ppt/presentation.xml")
    return [tgt[r] for r in re.findall(r'<p:sldId id="\d+" r:id="(rId\d+)"/>', pres)]


def path(pos):
    return "ppt/slides/" + order()[pos - 1]


def read(pos):
    return _read(path(pos))


def write(pos, s):
    _write(path(pos), s)


# ------------------------------------------------------------------- metin

def _retext(template, text):
    """Sablonun ilk run'ini yeni metinle birak, kalan run'lari sil.

    Konum tabanli: iki run birbirinin ayni olabildigi icin str.replace ile
    yapmak ilk run'i silip metni tamamen kaybettiriyordu.
    """
    runs = list(re.finditer(r"<a:r>.*?</a:r>", template, re.S))
    if not runs:
        # bos yer tutucu - run'i biz uretiyoruz
        run = ('<a:r><a:rPr lang="tr-TR" dirty="0"/><a:t>%s</a:t></a:r>'
               % escape(text))
        if "</a:p>" in template:
            i = template.rindex("</a:p>")
            return template[:i] + run + template[i:]
        return template
    first = runs[0]
    head = re.sub(r"(<a:t>).*?(</a:t>)",
                  lambda m: m.group(1) + escape(text) + m.group(2),
                  first.group(0), count=1, flags=re.S)
    out = template[:first.start()] + head
    end = first.end()
    for r in runs[1:]:
        out += template[end:r.start()]
        end = r.end()
    return out + template[end:]


def _shapes(s):
    return list(re.finditer(r"<p:sp>.*?</p:sp>", s, re.S))


def _pick(s, name=None):
    """Kutuyu adiyla, ad verilmediyse en cok metni olaniyla sec."""
    shapes = _shapes(s)
    if name:
        for m in shapes:
            nm = re.search(r'name="([^"]*)"', m.group(0))
            if nm and name.lower() in nm.group(1).lower():
                return m
        raise AssertionError("kutu bulunamadi: %s" % name)
    return max(shapes, key=lambda m: len("".join(
        re.findall(r"<a:t>(.*?)</a:t>", m.group(0)))))


def _lvl(p):
    m = re.search(r'<a:pPr[^>]*\blvl="(\d+)"', p)
    return int(m.group(1)) if m else 0


def body(pos, lines, name=None):
    """lines: [(lvl, metin), ...] ya da duz [metin, ...] (hepsi lvl 0)."""
    lines = [(0, x) if isinstance(x, str) else x for x in lines]
    s = read(pos)
    box = _pick(s, name)
    block = box.group(0)
    ps = re.findall(r"<a:p>.*?</a:p>", block, re.S)
    assert ps, "slayt %d: paragraf yok" % pos
    by = {}
    for p in ps:
        by.setdefault(_lvl(p), p)
    made = []
    for lvl, text in lines:
        tpl = by.get(lvl) or by[min(by)]
        made.append(_retext(tpl, text))
    write(pos, s.replace(block, block.replace("".join(ps), "".join(made)), 1))


def title(pos, *lines):
    """Baslik kutusunu yaz. Birden fazla satir verilirse her biri bir paragraf."""
    s = read(pos)
    box = None
    for m in _shapes(s):
        if re.search(r'name="(Title|Baslik|Başlık|Dikdörtgen 10)', m.group(0)):
            box = m
            break
    if box is None:
        box = _shapes(s)[0]
    block = box.group(0)
    ps = re.findall(r"<a:p>.*?</a:p>", block, re.S)
    made = [_retext(ps[i] if i < len(ps) else ps[-1], t)
            for i, t in enumerate(lines)]
    write(pos, s.replace(block, block.replace("".join(ps), "".join(made)), 1))


def place(pos, name, x, y, cx, cy):
    """Bir kutuya acik konum ver (layout'tan miras alanlar icin)."""
    s = read(pos)
    box = _pick(s, name)
    block = box.group(0)
    xfrm = ('<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            % (x, y, cx, cy))
    if "<a:xfrm>" in block:
        fixed = re.sub(r"<a:xfrm>.*?</a:xfrm>", xfrm, block, count=1, flags=re.S)
    elif "<p:spPr/>" in block:
        fixed = block.replace("<p:spPr/>", "<p:spPr>" + xfrm + "</p:spPr>", 1)
    else:
        fixed = block.replace("<p:spPr>", "<p:spPr>" + xfrm, 1)
    write(pos, s.replace(block, fixed, 1))


# ------------------------------------------------------------------ gorsel

def _fit(png, box):
    w, h = Image.open(png).size
    x, y, cx, cy = box
    k = min(cx / float(w), cy / float(h))
    ew, eh = int(w * k), int(h * k)
    return x + (cx - ew) // 2, y + (cy - eh) // 2, ew, eh


def _next_media():
    d = os.path.join(W, "ppt/media")
    used = [int(m.group(1)) for f in os.listdir(d)
            for m in [re.match(r"image(\d+)\.", f)] if m]
    return max(used) + 1


def swap_pic(pos, png, box):
    """Slayttaki mevcut resmi yenisiyle degistir ve kutuya oturt."""
    name = "image%d.png" % _next_media()
    shutil.copy(png, os.path.join(W, "ppt/media", name))
    s = read(pos)
    pic = re.search(r"<p:pic>.*?</p:pic>", s, re.S).group(0)
    rid = re.search(r'<a:blip r:embed="(rId\d+)"', pic).group(1)
    rp = "ppt/slides/_rels/%s.rels" % order()[pos - 1]
    rels = _read(rp)
    _write(rp, re.sub(r'(Id="%s" [^>]*Target=")[^"]+"' % rid,
                      r'\1../media/%s"' % name, rels))
    x, y, cx, cy = _fit(png, box)
    fixed = re.sub(r'<a:off x="-?\d+" y="-?\d+"/><a:ext cx="\d+" cy="\d+"/>',
                   '<a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/>'
                   % (x, y, cx, cy), pic, count=1)
    write(pos, s.replace(pic, fixed, 1))


# --------------------------------------------------------------- konusma notu

NOTE_XML = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
    '<p:notes xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    ' xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/>"
    "<p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>"
    '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image Placeholder 1"/>'
    '<p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/></p:cNvSpPr>'
    '<p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
    '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes Placeholder 2"/><p:cNvSpPr>'
    '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/>'
    "</p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>%s"
    "</p:txBody></p:sp></p:spTree></p:cSld></p:notes>")


def note(pos, text):
    """Slaytin konusma notunu yaz; notesSlide yoksa olustur."""
    slide = order()[pos - 1]
    rp = "ppt/slides/_rels/%s.rels" % slide
    rels = _read(rp)
    m = re.search(r'Target="\.\./notesSlides/(notesSlide\d+\.xml)"', rels)
    paras = "".join('<a:p><a:r><a:rPr lang="tr-TR" dirty="0"/><a:t>%s</a:t>'
                    "</a:r></a:p>" % escape(line)
                    for line in text.split("\n"))
    if m:
        target = m.group(1)
    else:
        d = os.path.join(W, "ppt/notesSlides")
        used = [int(re.match(r"notesSlide(\d+)\.xml", f).group(1))
                for f in os.listdir(d) if re.match(r"notesSlide\d+\.xml$", f)]
        target = "notesSlide%d.xml" % (max(used) + 1)
        _write("ppt/notesSlides/_rels/%s.rels" % target,
               "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>\n"
               '<Relationships xmlns="http://schemas.openxmlformats.org/package'
               '/2006/relationships"><Relationship Id="rId1" Type="http://schemas'
               '.openxmlformats.org/officeDocument/2006/relationships/notesMaster"'
               ' Target="../notesMasters/notesMaster1.xml"/><Relationship '
               'Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument'
               '/2006/relationships/slide" Target="../slides/%s"/>'
               "</Relationships>" % slide)
        rid = "rId%d" % (max(int(x) for x in re.findall(r'Id="rId(\d+)"', rels)) + 1)
        _write(rp, rels.replace(
            "</Relationships>",
            '<Relationship Id="%s" Type="http://schemas.openxmlformats.org'
            '/officeDocument/2006/relationships/notesSlide" '
            'Target="../notesSlides/%s"/></Relationships>' % (rid, target)))
        ct = _read("[Content_Types].xml")
        _write("[Content_Types].xml", ct.replace(
            "</Types>",
            '<Override PartName="/ppt/notesSlides/%s" ContentType="application'
            '/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
            "</Types>" % target))
    _write("ppt/notesSlides/" + target, NOTE_XML % paras)


# ------------------------------------------------------------- slayt kopyala

def duplicate(src_pos, after_pos):
    """``src_pos``'taki slaydi kopyalayip ``after_pos``'tan sonraya koy."""
    src = order()[src_pos - 1]
    used = [int(re.match(r"slide(\d+)\.xml", f).group(1))
            for f in os.listdir(os.path.join(W, "ppt/slides"))
            if re.match(r"slide\d+\.xml$", f)]
    new = "slide%d.xml" % (max(used) + 1)
    shutil.copy(os.path.join(W, "ppt/slides", src),
                os.path.join(W, "ppt/slides", new))
    # rels: notesSlide iliskisini kopyalama, yenisi gerekirse note() kurar
    rels = _read("ppt/slides/_rels/%s.rels" % src)
    rels = re.sub(r'<Relationship [^>]*notesSlides/[^>]*/>', "", rels)
    _write("ppt/slides/_rels/%s.rels" % new, rels)
    ct = _read("[Content_Types].xml")
    _write("[Content_Types].xml", ct.replace(
        "</Types>",
        '<Override PartName="/ppt/slides/%s" ContentType="application'
        '/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        "</Types>" % new))
    prels = _read("ppt/_rels/presentation.xml.rels")
    rid = "rId%d" % (max(int(x) for x in re.findall(r'Id="rId(\d+)"', prels)) + 1)
    _write("ppt/_rels/presentation.xml.rels", prels.replace(
        "</Relationships>",
        '<Relationship Id="%s" Type="http://schemas.openxmlformats.org'
        '/officeDocument/2006/relationships/slide" Target="slides/%s"/>'
        "</Relationships>" % (rid, new)))
    pres = _read("ppt/presentation.xml")
    ids = re.findall(r'<p:sldId id="(\d+)" r:id="rId\d+"/>', pres)
    anchor = re.findall(r'<p:sldId id="\d+" r:id="rId\d+"/>', pres)[after_pos - 1]
    tag = '<p:sldId id="%d" r:id="%s"/>' % (max(int(i) for i in ids) + 1, rid)
    _write("ppt/presentation.xml", pres.replace(anchor, anchor + tag, 1))
    return after_pos + 1


def pack(dest):
    import subprocess
    if os.path.exists(dest):
        os.remove(dest)
    subprocess.run(["zip", "-q", "-r", "-X", dest, "."], cwd=W, check=True)
    print("yazildi:", dest)


def add_pic(pos, png, box, name="Chart"):
    """Slayta yeni bir resim ekle."""
    fn = "image%d.png" % _next_media()
    shutil.copy(png, os.path.join(W, "ppt/media", fn))
    rp = "ppt/slides/_rels/%s.rels" % order()[pos - 1]
    rels = _read(rp)
    rid = "rId%d" % (max(int(x) for x in re.findall(r'Id="rId(\d+)"', rels)) + 1)
    _write(rp, rels.replace(
        "</Relationships>",
        '<Relationship Id="%s" Type="http://schemas.openxmlformats.org'
        '/officeDocument/2006/relationships/image" Target="../media/%s"/>'
        "</Relationships>" % (rid, fn)))
    s = read(pos)
    sid = max(int(x) for x in re.findall(r'<p:cNvPr id="(\d+)"', s)) + 1
    x, y, cx, cy = _fit(png, box)
    pic = ('<p:pic><p:nvPicPr><p:cNvPr id="%d" name="%s"/><p:cNvPicPr>'
           '<a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
           '<p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch>'
           '</p:blipFill><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" '
           'cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
           "</p:spPr></p:pic>" % (sid, name, rid, x, y, cx, cy))
    write(pos, s.replace("</p:spTree>", pic + "</p:spTree>", 1))


def drop_shape(pos, name):
    """Bir sekli slayttan tamamen kaldir (dekoratif kutular, eski resimler)."""
    s = read(pos)
    for pat in (r"<p:sp>.*?</p:sp>", r"<p:pic>.*?</p:pic>"):
        for m in re.finditer(pat, s, re.S):
            nm = re.search(r'name="([^"]*)"', m.group(0))
            if nm and name.lower() in nm.group(1).lower():
                write(pos, s[:m.start()] + s[m.end():])
                return True
    return False


def arrange(keep):
    """Sunumu ``keep`` sirasina getir; listede olmayan slaytlari sil.

    ``keep`` su anki POZISYONLARIN listesi: arrange([1, 3, 2]) ilk uc slaydi
    1-3-2 sirasina koyar ve kalanlari atar.
    """
    prels = _read("ppt/_rels/presentation.xml.rels")
    tgt = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="slides/(slide\d+\.xml)"',
                          prels))
    pres = _read("ppt/presentation.xml")
    tags = re.findall(r'<p:sldId id="\d+" r:id="rId\d+"/>', pres)
    rids = re.findall(r'<p:sldId id="\d+" r:id="(rId\d+)"/>', pres)
    drop = [r for i, r in enumerate(rids, 1) if i not in keep]

    body = "".join(tags[p - 1] for p in keep)
    _write("ppt/presentation.xml",
           re.sub(r"(<p:sldIdLst>).*?(</p:sldIdLst>)",
                  lambda m: m.group(1) + body + m.group(2), pres, flags=re.S))

    ct = _read("[Content_Types].xml")
    for rid in drop:
        slide = tgt[rid]
        # notesSlide'i once at
        rp = "ppt/slides/_rels/%s.rels" % slide
        try:
            nrel = _read(rp)
        except IOError:
            nrel = ""
        for note_name in re.findall(r'Target="\.\./notesSlides/(notesSlide\d+\.xml)"',
                                    nrel):
            for part in ("ppt/notesSlides/%s" % note_name,
                         "ppt/notesSlides/_rels/%s.rels" % note_name):
                if os.path.exists(os.path.join(W, part)):
                    os.remove(os.path.join(W, part))
            ct = ct.replace('<Override PartName="/ppt/notesSlides/%s" ContentType='
                            '"application/vnd.openxmlformats-officedocument'
                            '.presentationml.notesSlide+xml"/>' % note_name, "")
        for part in ("ppt/slides/" + slide, rp):
            if os.path.exists(os.path.join(W, part)):
                os.remove(os.path.join(W, part))
        ct = re.sub(r'<Override PartName="/ppt/slides/%s"[^>]*/>' % slide, "", ct)
        prels = re.sub(r'<Relationship Id="%s"[^>]*/>' % rid, "", prels)
    _write("[Content_Types].xml", ct)
    _write("ppt/_rels/presentation.xml.rels", prels)
