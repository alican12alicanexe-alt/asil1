# -*- coding: utf-8 -*-
"""Arayuz metinleri iki dilde. Kaynak Ingilizce, Turkce bir sozlukte.

Kod Ingilizce yaziyor, ``t()`` gerekiyorsa Turkcesini veriyor. Bir dizenin
cevirisi yoksa Ingilizcesi gorunuyor - eksik ceviri arayuzu bozmuyor, sadece
o satiri Ingilizce birakiyor.

Dil degisince pencereyi yeniden kurmuyoruz: ``keep()`` her metni kimin
tasidigiyla birlikte not ediyor, ``retranslate()`` hepsini yeniden yaziyor.
Yani dil ortasinda bir tarama sonucu ya da doldurdugun form kaybolmuyor.

    keep(label.setText, "Compare")
    keep(lambda text: combo.setItemText(0, text), "All-green")

Secim ``~/.trainsim-ui.json``'a yaziliyor, her iki arayuz de oradan okuyor.
"""
import json
import os

#: Acilista Ingilizce. Kaydedilmis bir secim varsa load() onu getiriyor.
LANG = "en"

SETTINGS = os.path.join(os.path.expanduser("~"), ".trainsim-ui.json")

#: (uygula, anahtarlar) - dil degisince yeniden calistirilacak her sey.
REGISTRY = []

#: Sinyalizasyon sistemlerinin okunur adlari. Turkcesi asagidaki sozlukte.
SYSTEM_NAMES = {
    "fixed_block_3aspect": "Fixed block (3-aspect)",
    "etcs_l1": "ETCS Level 1",
    "etcs_l2": "ETCS Level 2",
    "etcs_hybrid_l3": "ETCS Hybrid Level 3",
    "etcs_moving_block": "Moving block (ETCS L3)",
    "virtual_coupling": "Virtual coupling",
}

WORDS = {
    # -- sistemler
    "Fixed block (3-aspect)": "Sabit blok (3 aspektli)",
    "ETCS Level 1": "ETCS Seviye 1",
    "ETCS Level 2": "ETCS Seviye 2",
    "ETCS Hybrid Level 3": "ETCS Hibrit Seviye 3",
    "Moving block (ETCS L3)": "Hareketli blok (ETCS L3)",
    "Virtual coupling": "Sanal kuplaj",

    # -- kabuk
    "Microscopic railway simulation": "Mikroskopik demiryolu benzetimi",
    "Compare": "Karşılaştır",
    "Build a line": "Hat kur",
    "SCENARIO": "SENARYO",
    "RUN LENGTH (S)": "KOŞU SÜRESİ (S)",
    "blank uses the scenario's own": "boş bırakırsan senaryonunki",
    "SIGNALLING": "SİNYALİZASYON",
    "As the scenario is fitted": "Senaryonun kendi donanımıyla",
    "COMPARE": "KARŞILAŞTIR",
    "Watch the schematic": "Şematiği izle",
    "GENERATE SCENARIO": "SENARYOYU ÜRET",
    "Sweep the headway": "Headway tara",
    "Generating runs one train over the empty line and writes the timetable "
    "from it. Sweeping runs the same fleet at every interval - it can take "
    "minutes.":
        "Üretmek boş hatta bir tren koşturur ve tarifeyi ondan yazar. Taramak "
        "aynı filoyu her aralıkta koşturur - dakikalar sürebilir.",

    # -- karsilastirma
    "Comparison": "Karşılaştırma",
    "Same line, same timetable, same train. The only thing that changes is "
    "how much room each train is given.":
        "Aynı hat, aynı tarife, aynı tren. Değişen tek şey trene ne kadar yol "
        "verildiği.",
    "Train graph": "Tren grafiği",
    "Time across, distance along the line up. Pick a row from the table.":
        "Yatayda zaman, dikeyde hat boyunca mesafe. Tablodan bir satır seç.",
    "SYSTEM": "SİSTEM",
    "JOURNEY": "SEFER SÜRESİ",
    "VS BASE": "FARKI",
    "MEAN DELAY": "ORT. GECİKME",
    "HELD DOWN": "KISITLI GEÇEN",
    "MIN GAP": "EN DAR ARALIK",
    "AUTHORITY": "ORT. YETKİ",
    "DONE": "BİTEN",
    "BREACHES": "İHLAL",
    "pick a run": "bir koşu seç",
    "km along the line": "hat boyunca km",
    "minute of the run": "koşunun kaçıncı dakikası",
    "same": "aynı",
    "%s running…": "%s koşuyor…",
    "%d runs finished": "%d koşu bitti",
    "Pick a scenario and at least one system.":
        "Bir senaryo ve en az bir sistem seç.",
    "The run length must be a number.": "Koşu süresi bir sayı olmalı.",
    "%s added to the list": "%s listeye eklendi",

    # -- hat kurma
    "Describe the stations, the ground, the fleet and the timetable here; "
    "once written the scenario appears in the comparison list.":
        "İstasyonları, yeri, filoyu ve tarifeyi buradan tarif et; senaryo "
        "yazıldıktan sonra karşılaştırma listesinde belirir.",
    "Line": "Hat",
    "Set the number of stations and the spacing, then press Apply; the names, "
    "kilometres and platform counts in the table can each be changed "
    "afterwards.":
        "İstasyon sayısını ve aralığını gir, Uygula'ya bas; tablodaki adları, "
        "kilometreleri ve peron sayılarını sonra tek tek değiştirebilirsin.",
    "Name": "Adı",
    "Stations": "İstasyon sayısı",
    "Station spacing": "İstasyon arası",
    "Line speed": "Hat hızı",
    "Block length": "Blok uzunluğu",
    "Platform zone": "Peron bölgesi",
    "Platforms by default": "Varsayılan peron",
    "Apply": "Uygula",
    "STATION": "İSTASYON",
    "NAME": "AD",
    "PLATFORMS": "PERON",
    "DEPOT": "DEPO",
    "yes": "evet",
    "no": "hayır",

    "Ground": "Yer",
    "Gradients stretch by stretch, per thousand and in the direction of "
    "travel: positive is a climb. The profile puts the ruling gradient on the "
    "steepest stretch, spreads the rest like a real alignment and levels the "
    "total. Speed limits are given in kilometres - a curve belongs to the "
    "ground, not to the timetable.":
        "Eğim kesim kesim, binde olarak ve gidiş yönünde: artı tırmanış. "
        "Profil en dik kesimi anma eğimine koyar, gerisini gerçek bir güzergâh "
        "gibi yayar ve toplamı sıfırlar. Hız limitleri kilometreyle verilir - "
        "bir kurp tarifeye değil yere aittir.",
    "Terrain": "Arazi",
    "Fill the profile": "Profili doldur",
    "STRETCH": "KESİM",
    "GRADE ‰": "EĞİM ‰",
    "Speed limits": "Hız limitleri",
    "FROM KM": "KM BAŞI",
    "TO KM": "KM SONU",
    "Add row": "Satır ekle",
    "Delete selected": "Seçileni sil",
    "Level (0 ‰)": "Düz (0 ‰)",
    "Plain (4 ‰)": "Ova (4 ‰)",
    "Main line (10 ‰)": "Ana hat (10 ‰)",
    "Mountain (18 ‰)": "Dağlık (18 ‰)",
    "High speed (25 ‰)": "Yüksek hızlı (25 ‰)",
    "Metro / suburban (35 ‰)": "Metro / banliyö (35 ‰)",

    "Fleet": "Filo",
    "One row is one kind of train: length m, top km/h, acceleration and "
    "brakes m/s². The first row is the line's default train; add a second and "
    "the timetable can say which one runs each service.":
        "Bir satır bir tren tipi: uzunluk m, azami km/h, ivme ve frenler m/s². "
        "İlk satır hattın varsayılan treni; ikinci bir satır eklersen tarifede "
        "sefer sefer hangisinin koşacağını seçebilirsin.",
    "LENGTH": "UZUNLUK",
    "TOP": "AZAMİ",
    "ACCEL": "İVME",
    "SERVICE": "SERVİS",
    "EMERGENCY": "ACİL",
    "Suburban": "Banliyö",
    "Express": "Ekspres",

    "Timetable": "Tarife",
    "Automatic by default: the same train, one after another at the interval "
    "you choose. Switch to by hand and you write each service's departure, "
    "train and calls yourself - empty calls means it stops everywhere.":
        "Varsayılan otomatik: aynı tren, seçtiğin aralıkta birbiri ardına. "
        "Elle geçersen her seferin kalkışını, trenini ve duraklarını tek tek "
        "yazarsın - duraklar boşsa hepsinde durur.",
    "Written as": "Yazım",
    "Automatic": "Otomatik",
    "By hand": "Elle",
    "Trains": "Tren sayısı",
    "Interval": "Aralık",
    "Dwell": "Bekleme",
    "First departure": "İlk kalkış",
    "DEPARTURE": "KALKIŞ",
    "CALLS": "DURAKLAR",
    "DWELL S": "BEKLEME S",
    "TRAIN": "TREN",
    "Fill from automatic": "Otomatikten doldur",

    "Signalling and search": "Sinyalizasyon ve arama",
    "Give the interval yourself and the scenario is written at it. Sweep and "
    "the same fleet is run at every interval, the tightest working one is "
    "found to the second, and what binds one second below it is named.":
        "Aralığı elle verirsen senaryo o aralıkla yazılır. Taratırsan aynı "
        "filo her aralıkta koşulur, çalışan en sıkı aralık saniyesine kadar "
        "bulunur ve bir saniye altında neyin bağladığı söylenir.",
    "System": "Sistem",
    "Apply an uncoupled speed limit": "Kuplajsız hız limiti uygula",
    "Uncoupled speed": "Kuplajsız hız",
    "Coupling margin": "Kuplaj marjı",
    "V2V latency": "V2V gecikmesi",
    "Leader brake": "Lider freni",
    "Emergency brake (cautious)": "Acil fren (ihtiyatlı)",
    "Service brake (convoy rule)": "Servis freni (konvoy kuralı)",
    "Search": "Arama",
    "Find the interval by sweeping": "Aralığı tarayarak bul",
    "Top of the search": "Aramanın üstü",
    "Bottom of the search": "Aramanın altı",
    "Steps": "Basamak",
    "Rule": "Ölçüt",
    "Never held by a signal (all-green)": "Hiç sinyalle tutulmadan (all-green)",
    "Held, but still to time": "Tutulsa da tarifeye uyarak",
    "Result": "Sonuç",

    # -- kosarken ve rapor
    "Writing the line, running one train over it…":
        "Hat yazılıyor, boş hatta bir tren koşuyor…",
    "Even one train alone could not finish the line. The run is too short, or "
    "this plan does not work on this railway.":
        "Tek başına koşan tren bile hattı bitiremedi. Koşu süresi kısa, ya da "
        "bu plan bu hatta yürümüyor.",
    "Sweep starting: one run per interval…":
        "Tarama başlıyor: her aralık bir koşu…",
    "clean": "temiz",
    "tight": "sıkışık",
    "%-6s %2d calls   %s alone on the line":
        "%-6s %2d durak   boş hatta %s",
    "  interval    held by signals    mean delay      worst   done":
        "  aralık    sinyalle tutulan   ort. gecikme    en kötü   biten",
    "<-- tight": "<-- sıkışık",
    "Nothing in the range crossed the boundary. Widen the search: upwards if "
    "even the top is tight, downwards if even the bottom is still clean.":
        "Aralığın hiçbir yerinde sınır geçilmedi. Arama sınırlarını genişlet: "
        "ya üstü zaten sıkışıksa yukarı, ya altı hâlâ temizse aşağı.",
    "Tightest working interval: %d s  (%.1f trains an hour)":
        "Çalışan en sıkı aralık: %d s  (saatte %.1f tren)",
    "The scenario was written at this interval.":
        "Senaryo bu aralıkla yazıldı.",
    "What binds one second tighter:": "Bir saniye altında bağlayan:",
    "Where (by the station the train was heading for):":
        "Nerede (trenin gitmekte olduğu istasyona göre):",
    "If one station stands out on its own, adding a platform there is cheaper "
    "than changing the signalling system.":
        "Bir istasyon tek başına öne çıkıyorsa oraya bir peron eklemek "
        "sinyalizasyonu değiştirmekten ucuzdur.",
    "Written: %s": "Yazıldı: %s",
    "ERROR: %s": "HATA: %s",

    # -- itirazlar
    "A line needs at least two stations.":
        "Bir hat en az iki istasyon ister.",
    "Two stations cannot share an id: %s":
        "İki istasyon aynı id'yi taşıyamaz: %s",
    "Stations must be in kilometre order.":
        "İstasyonlar kilometre sırasında olmalı.",
    "The fleet needs at least one kind of train.":
        "Filoda en az bir tren tipi olmalı.",
    "%s calls at a station that does not exist: %s":
        "%s seferi olmayan istasyonda duruyor: %s",
    "A by-hand timetable is selected but the table is empty - \"Fill from "
    "automatic\" is a good start.":
        "Elle tarife seçili ama tabloda sefer yok - \"Otomatikten doldur\" iyi "
        "bir başlangıç.",
    "The bottom of the search must be below the top.":
        "Aramanın altı üstünden küçük olmalı.",
}


def t(text):
    """``text``in secili dildeki hali. Cevirisi yoksa kendisi."""
    if LANG == "en":
        return text
    return WORDS.get(text, text)


def system_name(system):
    """Bir sinyalizasyon sisteminin secili dildeki adi."""
    return t(SYSTEM_NAMES.get(system, system))


def keep(apply, *keys):
    """``apply``i simdi cagir, dil her degistiginde yeniden cagir.

    ``keys`` Ingilizce kaynak dizeler; ``apply`` cevrilmis hallerini aliyor.
    """
    REGISTRY.append((apply, keys))
    apply(*[t(key) for key in keys])


def retranslate():
    """Not edilmis her metni yeniden yaz."""
    for apply, keys in REGISTRY:
        apply(*[t(key) for key in keys])


def set_language(code):
    """Dili degistir ve kaydet. Bir sey degismediyse dokunma."""
    global LANG
    if code == LANG:
        return False
    LANG = code
    save()
    retranslate()
    return True


def load():
    """Kaydedilmis dil secimi. Okunamiyorsa Ingilizce - ev dizini bir ag
    payinda olabilir ve arayuz bu yuzden acilmamali."""
    global LANG
    try:
        with open(SETTINGS, encoding="utf-8") as handle:
            LANG = json.load(handle).get("lang", "en")
    except Exception:
        LANG = "en"
    return LANG


def save():
    try:
        with open(SETTINGS, "w", encoding="utf-8") as handle:
            json.dump({"lang": LANG}, handle)
    except Exception:
        pass                       # yazamiyorsak secim bu oturumluk kalir


def selfcheck():
    global LANG
    was = LANG
    seen = []
    LANG = "en"
    keep(seen.append, "Compare")
    assert seen == ["Compare"], seen
    assert t("Compare") == "Compare"
    assert system_name("virtual_coupling") == "Virtual coupling"
    set_language("tr")
    assert seen[-1] == "Karşılaştır", seen
    assert system_name("virtual_coupling") == "Sanal kuplaj"
    assert t("no translation for this") == "no translation for this", \
        "eksik ceviri arayuzu bozmamali"
    assert not set_language("tr"), "ayni dile gecmek is olmamali"
    set_language("en")
    assert seen[-1] == "Compare", seen
    # Ceviride kaybolan bir %s calisma aninda patlar; en ucuz yakalandigi yer
    # burasi.
    import re
    for english, turkish in WORDS.items():
        assert turkish and turkish != english, english
        marks = re.compile(r"%[-\d.]*[a-z]")
        assert marks.findall(english) == marks.findall(turkish), english
    LANG = was
    print("uilang selfcheck tamam")


if __name__ == "__main__":
    selfcheck()
