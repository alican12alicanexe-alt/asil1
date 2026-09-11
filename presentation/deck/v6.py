# -*- coding: utf-8 -*-
"""v5 -> v6: bulgular basligi, kaynaklarin temizligi, ve sona iki ornek slayt.

  - BULGULAR'in dorduncu basligi cumle gibi degil basliktı; digerleriyle ayni
    bicimde bir isim tamlamasi oldu, "kapasite degil" maddesine indi.
  - Kaynaklar: metinde hicbir yerde atif verilmeyen [3]-[6] kalkti. Kalan
    ikisinin numarasi artik slayt 5'teki kartlarin basligina yazili, yani
    listedeki numara bir yeri gosteriyor.
  - Sona iki slayt: simulasyonun ekran goruntuleri. Resimler henuz yok;
    baslik, altyazi ve yer hazir (SHOTS'a dosya yolu verilince gomuluyor).
"""
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC, DST = BASE + "/ASELSAN-Sunum-v5.pptx", BASE + "/ASELSAN-Sunum-v6.pptx"
FIGURES = os.path.join(os.path.dirname(BASE), "figures")

if os.path.isdir(BASE + "/work"):
    shutil.rmtree(BASE + "/work")
os.makedirs(BASE + "/work")
subprocess.run(["unzip", "-q", SRC, "-d", BASE + "/work"], check=True)
sys.path.insert(0, BASE)
import kit                                                    # noqa: E402

# --- 1. kartlar: basliklarina [1] ve [2] geldi, olculeri ayni, kirpma duruyor
shutil.copy(os.path.join(FIGURES, "papers.png"), BASE + "/work/ppt/media/image15.png")

# --- 2. bulgular
kit.body(15, [
    (0, u"EN GÜÇLÜ OLDUĞU YER"),
    (1, u"Duraksız işletme   39 s → 32 s  (%18)   ·   konvoy kuralıyla   "
        u"25 s → 17 s  (%32)"),
    (0, u"ETKİSİNİN KAYBOLDUĞU YER"),
    (1, u"Duraklamalı işletme   78 s → 71 s  (%9)"),
    (1, u"Her sistem kendi aralığında koşarken bozucu etki altında   %0.5"),
    (0, u"KAPSAM DIŞI BIRAKILAN"),
    (1, u"Karma trafik ve ayrılan/birleşen kavşaklar — rota ve tarife optimizasyonu"),
    (0, u"BUGÜNKÜ KISITLAR"),
    (1, u"Kapasite değil: güvenlik ispatı   ·   protokol olgunluğu   ·   "
        u"yatırımın hattı hak etmesi"),
])

# --- 3. kaynaklar: atif verilen ikisi kaliyor
kit.body(16, [
    (0, u"[1]  Quaglietta, E., Wang, M., Goverde, R.M.P. (2020). A multi-state "
        u"train-following model for the analysis of virtual coupling railway "
        u"operations. Journal of Rail Transport Planning & Management, 15, "
        u"100195. doi:10.1016/j.jrtpm.2020.100195"),
    (0, u"[2]  Aoun, J., Quaglietta, E., Goverde, R.M.P., Scheidt, M., "
        u"Blumenfeld, M., Jack, A., Redfern, B. (2021). A hybrid Delphi-AHP "
        u"multi-criteria analysis of Moving Block and Virtual Coupling railway "
        u"signalling. Transportation Research Part C, 129, 103250. "
        u"doi:10.1016/j.trc.2021.103250"),
])

# --- 4. sona iki ornek. 11'den kopyalaniyor: baslik + altyazi + resim duzeni.
SHOTS = [
    (u"SİMÜLASYON — SABİT BLOK",
     u"Aynı çevrim, 3 aspektli sabit blok. Takip mesafesini blok uzunluğu "
     u"belirliyor: öndeki blok işgalliyken arkadaki tren sarıya uyup yavaşlıyor.",
     os.environ.get("SHOT_FIXED", "")),
    (u"SİMÜLASYON — SANAL KUPLAJ",
     u"Aynı çevrim, sanal kuplaj. Kabin sinyalizasyonu, hat kenarında sinyal "
     u"yok; ayrım blokla değil mesafeyle. Tren öndekine kuplajlandığında "
     u"yetkisini ondan alıyor.",
     os.environ.get("SHOT_VC", "")),
]
BOX = (411480, 2100000, 11338560, 3900000)     # sol, ust, en, boy

for i, (head, caption, png) in enumerate(SHOTS):
    pos = len(kit.order())
    kit.duplicate(11, pos)                     # 11 = duraksız işletme slaydı
    new = pos + 1
    kit.title(new, head)
    kit.body(new, [caption])
    kit.drop_shape(new, "Grafik")              # 11'den gelen grafik gidiyor
    while kit.drop_shape(new, "Yuzde"):        # ve onun yuzde etiketleri
        pass
    if png and os.path.exists(png):
        kit.add_pic(new, png, BOX, name="Ekran")
    else:
        print("slayt %d: ekran goruntusu bekleniyor (%s)"
              % (new, "SHOT_FIXED" if i == 0 else "SHOT_VC"))

# --- 5. altbilgideki payda slayt sayisini takip etsin
total = len(kit.order())
master = "ppt/slideMasters/slideMaster1.xml"
s = kit._read(master)
import re                                                     # noqa: E402
kit._write(master, re.sub(r"<a:t>/\d+</a:t>", "<a:t>/%d</a:t>" % total, s, count=1))

kit.pack(DST)
print("%d slayt" % total)
