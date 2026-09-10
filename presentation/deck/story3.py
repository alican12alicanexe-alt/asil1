# -*- coding: utf-8 -*-
"""v2 -> v3: akademik yeniden kurgu.

Ilke: slaytta grafik, sayi ve en fazla 2-4 kisa madde. Anlatilacak her sey
konusmaci notunda. Slayttaki hicbir sayi elle yazilmadi; hepsi bir kosunun
ciktisi (kaynagi ilgili chart betiginin basliginda).
"""
import os
import shutil
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = BASE + "/ASELSAN-Sunum-v2.pptx"   # bkz. README - depoda yok
if os.path.isdir(BASE + "/work"):
    shutil.rmtree(BASE + "/work")
os.makedirs(BASE + "/work")
subprocess.run(["unzip", "-q", SRC, "-d", BASE + "/work"], check=True)
sys.path.insert(0, BASE)
import kit

CH = os.path.join(os.path.dirname(BASE), "figures")
SC = os.path.join(os.path.dirname(BASE), "figures")
FULL = (411480, 11338560)          # sol kenar, genislik

# 1 kapak, 3 icerik, 2 calisma, 9 test agi, 5 literatur, 8 sinyalizasyon,
# 10 tren modeli, 12 egriler, 13 kabuller, 14 express, 15 duraklamali,
# 16 bozucu, 17 konvoy, 11 karsilastirma, 18 bulgular, 19 yedi saniye,
# 20 kaynaklar, 21 tesekkurler.   Atilanlar: 4 (problem/amac -> 3'e girdi),
# 6 ve 7 (makale slaytlari -> 5'teki kartlara girdi).
kit.arrange([1, 3, 2, 9, 5, 8, 10, 12, 13, 14, 15, 16, 17, 11, 18, 19, 20, 21])

# ==================================================================== 2 İÇERİK
kit.body(2, [
    u"Çalışma", u"Test Ağı", u"Literatür", u"Sinyalizasyon Sistemleri",
    u"Tren Modeli ve Dinamiği", u"Kabuller ve Koşullar",
    u"Deneyler ve Sonuçlar", u"Ana Bulgular",
], name="Metin kutusu 41")

# ================================================================== 3 ÇALIŞMA
kit.title(3, u"ÇALIŞMA")
for junk in ("Rounded Rectangle 10", "Freeform: Shape 36", "Freeform: Shape 36"):
    kit.drop_shape(3, junk)
kit.place(3, "Icerik Metni", FULL[0], 1450000, FULL[1], 1150000)
kit.body(3, [
    u"Soru: Yeni hat yapmadan mevcut altyapıdan daha fazla tren geçirilebilir mi?",
    u"Yöntem: Aynı ağ, aynı filo, aynı tarife — yalnızca sinyalizasyon değişiyor.",
    u"Ölçüt: Hattın gecikmeden sürdürebildiği en kısa tren aralığı.",
], name="Icerik Metni")
kit.add_pic(3, CH + "/flow.png", (FULL[0], 3000000, FULL[1], 2100000), "Akis")
kit.note(3, u"Bu bir literatur derlemesi degil: simulator staj boyunca sifirdan "
            u"yazildi. Icinde tren dinamigi, surucu modeli, uc sinyalizasyon "
            u"sistemi, kilitleme ve tarife var.\n"
            u"Neden onemli: kapasiteyi arttirmanin klasik yolu yeni hat veya yeni "
            u"peron yapmak, ikisi de pahali ve yavas. Sinyalizasyon degistirmek "
            u"ayni altyapidan daha fazla tren gecirmenin en ucuz yolu olarak "
            u"one suruluyor - bu calisma o iddiayi olcuyor.\n"
            u"Sunumda gordugunuz her sayi bir kosunun ciktisi ve komutu depodaki "
            u"COMMANDS.md'de yazili; hicbiri literaturden alinmadi.")

# ================================================================= 4 TEST AĞI
kit.title(4, u"TEST AĞI")
kit.body(4, [
    u"Kapalı çevrim (ring)   ·   çift hat   ·   70 km tur   ·   11 istasyon   "
    u"·   22 duruş",
    u"3.1 km ortalama istasyon aralığı   ·   900 m blok   ·   10 makas bağlantısı",
    u"80 km/h azami hat hızı   ·   30 s peron beklemesi   ·   12 tren",
    u"Kentiçi demiryolu (urban railway) profili — metro değil, banliyö "
    u"karakterinde.   [4][6]",
], name="Text Placeholder")
kit.swap_pic(4, CH + "/network.png", (FULL[0], 2900000, FULL[1], 2900000))
kit.note(4, u"Terminoloji: bu gercek bir metro hatti degil, ve oyleymis gibi "
            u"sunmuyorum. Istasyon araligi 3.1 km ve kapidan kapiya hiz 53 km/h; "
            u"metroda bunlar 0.8-1.2 km ve 30-35 km/h olur. Kapali cevrim yapisi, "
            u"her istasyonda durus ve 71-148 saniyelik takip araliklari ise "
            u"metro-benzeri. Bu yuzden 'kentici demiryolu test agi' diyorum ve "
            u"sunumun tamaminda bu terimi kullaniyorum.\n"
            u"Neden cevrim: gidis-donus hatlarda belli bir araligin altinda kisit "
            u"sinyalizasyon olmaktan cikip terminaldeki sevk sirasi oluyor. Duran "
            u"trenin kalkis suresini hicbir sinyalizasyon sistemi degistirmez, o "
            u"yuzden karsilastirma duzlesiyor. Cevrimde her tren kosuyor ve "
            u"beklemenin tek sebebi onunde birinin olmasi - olculen sey boylece "
            u"sinyalizasyonun kendisi.\n"
            u"Istasyonlar bilerek esit araliksiz: gercek bir tarifenin en sikisik "
            u"yeri vardir. Akyurt 1 - Macunkoy 1 arasindaki 2.5 km burada ilk "
            u"baglayan yer.\n"
            u"Bos turda bir tur 79 dk 09 s; bunun 11 dakikasi peronda duruyor.")

# ================================================================ 5 LİTERATÜR
kit.title(5, u"LİTERATÜR")
kit.body(5, [u"Sanal kuplajın kapasiteye etkisini ölçen iki temel çalışma ve "
             u"bu çalışmanın onlara göre yeri."], name="Text Placeholder")
kit.drop_shape(5, "Not 204")
kit.add_pic(5, CH + "/papers.png", (FULL[0], 2100000, FULL[1], 3650000), "Kartlar")
kit.note(5, u"Stajin ilk gunlerinde kapasite artirimi uzerine cok sayida calisma "
            u"okudum; bu ikisi ayri duruyor.\n"
            u"QUAGLIETTA: sanal kuplaji dort isletim durumu olan bir tren takip "
            u"modeli olarak kuruyor - kuplaja hazirlanma, kuplajli seyir, istemsiz "
            u"ayrilma (dik rampada tren ondekine yetisemiyor), istemli ayrilma "
            u"(ayrilan kavsakta makas guvenle cevrilebilsin diye). Ingiltere'de "
            u"South West Main Line'in 20 km'lik kesitinde iki tren kosturuyorlar. "
            u"Kazanc senaryoya gore %13-%53; en buyugu duraklamali ve farkli "
            u"rotali trenlerde.\n"
            u"AOUN: kapasitenin otesine bakiyor - maliyet, enerji, guvenlik, "
            u"regulasyon onayi, kamuoyu kabulu. On bes sektor uzmaniyla anket. "
            u"Cikan tablo: guvenlik tek basina kararin %45'i, regulasyon %32'si, "
            u"kapasite sadece %5.6'si. Hareketli blok bugun daha olgun oldugu icin "
            u"genel skorda one geciyor.\n"
            u"BENIM FARKIM: onlar iki trenin anlik mesafesini olcuyor, ben on iki "
            u"trenin bir turu hangi aralikla surdurebildigini. Benim sayimin daha "
            u"kucuk cikmasi bu yuzden beklenen - ayni seyi olcmuyoruz.\n"
            u"BURAYA GORSEL (istege bagli): iki makalenin kendi sekilleri. Telifli "
            u"olduklari icin ben eklemedim; kaynak gostererek sen ekleyebilirsin.")

# =========================================================== 6 SİNYALİZASYON
kit.title(6, u"SİNYALİZASYON SİSTEMLERİ")
for junk in ("Picture 4", "Picture 6", "Picture 15", "TextBox 9", "TextBox 11",
             "TextBox 13", "TextBox 16", "TextBox 18"):
    kit.drop_shape(6, junk)
kit.place(6, "Text Placeholder", FULL[0], 1480000, FULL[1], 560000)
kit.body(6, [u"Üçünün farkı tek soruda: ön trenle aramızdaki mesafeyi ne "
             u"belirliyor?   [3][5]"], name="Text Placeholder")
kit.add_pic(6, CH + "/systems.png", (FULL[0], 2200000, FULL[1], 3450000), "Matris")
kit.note(6, u"SABIT BLOK: hat sabit parcalara bolunmus, on tren hangi bloktaysa o "
            u"blok kapali. Tren blogun neresinde olursa olsun bir blok boyu "
            u"kaybediyorsun - burada 900 m.\n"
            u"HAREKETLI BLOK (ETCS L3): blok yok. Yetki, on trenin gercek arkasinin "
            u"100 m gerisinde bitiyor ve tren oraya durabilecegi hizla yaklasiyor. "
            u"Buna MUTLAK fren mesafesi denir: ondeki tren duvara carpmis gibi "
            u"aninda duruyor varsayilir.\n"
            u"SANAL KUPLAJ: ondeki trenin de fren yapacagi varsayilir, yani gereken "
            u"sey iki fren mesafesinin FARKI. NISPI fren mesafesi. Kazancin kaynagi "
            u"bu - ve riski de bu: onde giden trenin freni dogrulanamaz, ve raydan "
            u"cikan bir tren aninda durur. Aoun'un %45 guvenlik agirligi tam olarak "
            u"bu belirsizligi olcuyor.\n"
            u"Kazancin buyuklugu hiza bagli: kabaca v/2 x (1/b - 1/b_acil), bu arac "
            u"icin 0.17v. 80 km/h'te 3.7 saniye, duran trende sifir. Duraklamali bir "
            u"hatta kazancin neden kucuk kaldigini bu tek satir aciklıyor.\n"
            u"ONERI - BURAYA GIF: uc sistemin ayni ani, yan yana. Sabit blokta "
            u"trenin blok sinirinda beklemesi, hareketli blokta arkaya kilitlenmesi, "
            u"sanal kuplajda icine girmesi.")

# ============================================================= 7 TREN MODELİ
kit.title(7, u"TREN MODELİ VE DİNAMİĞİ")
kit.body(7, [
    u"Araç:   120 m   ·   216 t   ·   90 km/h   ·   2333 kW  (10.8 kW/t)",
    u"Performans:   kalkış 1.0   ·   servis freni 1.0   ·   acil fren 1.5 m/s²",
    u"Dinamik:   çeki eğrisi (taban hız 36 km/h)   ·   Davis direnci   ·   "
    u"eğim   ·   jerk sınırı 0.5 m/s³",
    u"Türetilen:   kütle, güç, Davis katsayıları, taban hız — hiçbiri senaryo "
    u"dosyasında yazmıyor",
], name="Text Placeholder")
kit.note(7, u"HAREKET DENKLEMI:   m_eff · a = F(v) − R(v) − m·g·sin(θ)\n"
            u"  m_eff = m · 1.08 — donen kutleler de hizlandirilmak zorunda: "
            u"tekerlek, disli, rotor. 216 t tren 233 t gibi davraniyor.\n"
            u"  F(v) : ceki kuvveti. Taban hiza kadar sabit (233 kN), ustunde P/v "
            u"ile dusuyor.\n"
            u"  R(v) : Davis direnci = A + B·v + C·v²  [N, v m/s]. Bu arac icin "
            u"R(v) = 1404 + 28.1·v + 3.74·v².  A yatak ve yuvarlanma direnci, B "
            u"flans ve ray temasi - ikisi kutleyle olcekleniyor; C aerodinamik ve "
            u"kutleyle degil UZUNLUKLA olcekleniyor.\n"
            u"  m·g·sin(θ) : egim bileseni. Sonradan eklenen bir duzeltme degil, "
            u"denklemin kendi terimi. Trenin %30'u bir egimde %70'i baskaysa kuvvet "
            u"trenin ALTINDAKI egimin uzunlukla agirliklandirilmis ortalamasindan "
            u"hesaplaniyor - tek bir nokta degil, trenin tamami.\n"
            u"  Fren: talep edilen oran aderans siniriyla (mu·g) kesiliyor, egim "
            u"dogrudan orana ekleniyor.\n"
            u"SON MADDE: senaryo dosyasi bir aracin uzunlugunu ve dort performans "
            u"degerini yaziyor, hepsi bu. Kutle, guc, Davis katsayilari, ceki "
            u"egrisinin kirildigi hiz, en dik inisteki fren mesafesi - hepsi "
            u"turetiliyor ve stats.py bunlari formuluyle birlikte yazdiriyor.")

# =============================================================== 8 EĞRİLER
kit.title(8, u"HAREKET EĞRİLERİ")
kit.body(8, [
    u"Hareket yetkisi bir fren mesafesi değildir:  44 + 22 + 247 + 25 = 339 m.",
    u"Her nokta simülatörün kendi fonksiyonundan — jerk sınırı dahil.",
], name="Text Placeholder")
kit.swap_pic(8, SC + "/motion.png", (473569, 2550000, 11214381, 3450000))
kit.note(8, u"SOL PANEL sik yapilan bir hatayi duzeltiyor. Cizilen sey bir fren "
            u"mesafesi degil, surucunun ayirdigi toplam yol:\n"
            u"  tepki suresi 2 s -> 44 m (tren hala tam hizda)\n"
            u"  fren kabarmasi   -> 22 m (havanin hareket etmesi gerekiyor)\n"
            u"  fren egrisi      -> 247 m\n"
            u"  emniyet payi     -> 25 m\n"
            u"  TOPLAM           -> 339 m.  Fren mesafesi bunun %73'u.\n"
            u"Dogrulama: surucunun planladigi sabit oranli egri 338.6 m diyor, "
            u"jerk sinirli gercek hareketi integre ettigimde 337.9 m cikiyor. "
            u"0.7 metre. Kabarma payi tam olarak jerkin maliyetini karsilamak icin "
            u"var ve dogru boyutta.\n"
            u"ORTA PANEL: 3.1 km'lik bir istasyon araligi. 164 saniye, ortalama "
            u"68 km/h. Kirilma noktasi taban hiz.\n"
            u"SAG PANEL: ayni seyahatin ivmesi. Seyirde sifir - surucu hizi "
            u"tutuyor, tam guc istemiyor. Buyutec fren devreye girisini "
            u"gosteriyor: 0'dan -1.0 m/s²'ye jerk siniri yuzunden 2 saniyede "
            u"iniyor, bir adimda degil. Grafikte hicbir yerde ani ivme sicramasi "
            u"yok, cunku modelde de yok.")

# =============================================================== 9 KABULLER
kit.title(9, u"KABULLER VE SİMÜLASYON KOŞULLARI")
kit.body(9, [
    (0, u"ARAÇ VE HAREKET"),
    (1, u"120 m · 216 t   ·   90 km/h   ·   1.0 / 1.0 / 1.5 m/s²   ·   "
        u"jerk 0.5 m/s³"),
    (0, u"AYRIM VE EMNİYET"),
    (1, u"Sistem payı: hareketli blok 100 m · sanal kuplaj 50 m · sabit blok yok"),
    (1, u"Sürücü payı: 25 m, sistemden bağımsız — ikisi toplanır"),
    (1, u"Sürücü: izin verilen her metreyi kullanır; tepki 2.0 s (kabinde 0 s)"),
    (0, u"HABERLEŞME VE ALTYAPI"),
    (1, u"V2V gecikmesi 0.5 s   ·   kesintisiz kapsama   ·   40 km/h makas, "
        u"50 km/h dönüş kavisi"),
    (0, u"KOŞULLAR"),
    (1, u"dt = 1.0 s (tümü dt = 0.5 s ile doğrulandı)   ·   12 servis   ·   "
        u"30 s bekleme"),
], name="Text Placeholder")
kit.note(9, u"IKI AYRI EMNIYET PAYI VAR VE TOPLANIYORLAR. Sistemin payi tehlike "
            u"noktasinin NEREDE oldugunu belirliyor - hareketli blokta ondeki "
            u"trenin arkasindan 100 m once, sanal kuplajda 50 m, sabit blokta hic "
            u"(orada tehlike noktasi zaten bosalmis bir blok siniri). Surucunun "
            u"payi ise verilen tehlike noktasindan ne kadar once durdugu: 25 m ve "
            u"sinyalizasyondan bagimsiz. Yani hareketli blokta bir tren ondekinin "
            u"arkasindan 125 m uzakta tutuluyor.\n"
            u"SURUCU DAVRANISI: model surucusu 'agresif' anlamda ideal - hicbir "
            u"metreyi bosa harcamiyor, hiz sinirini da asmiyor. Bu bilerek boyle: "
            u"amac sinyalizasyonu olcmek, surucu farkini degil. Gercek bir surucu "
            u"daha temkinli surer ve butun sistemler ayni oranda kotulesir, yani "
            u"karsilastirma bozulmaz.\n"
            u"HABERLESME: V2V icin 0.5 s gecikme ve kesintisiz kapsama varsayildi. "
            u"Kapsama kaybi modellenmedi - bu bir sinirlama; gercekte sanal kuplaj "
            u"baglantisiz kaldiginda hareketli bloga dusuyor ve model bu geri "
            u"dususe sahip ama senaryolarda tetiklenmiyor.\n"
            u"dt = 0.5 s dogrulamasi onemli: iki sinir da ikiser saniye artiyor, "
            u"aradaki FARK degismiyor. Yani sonuc bir zaman adimi artefakti degil.")

# ================================================================ 10 EXPRESS
kit.title(10, u"DURAKSIZ (EXPRESS) İŞLETME")
kit.body(10, [u"Peron kısıtı devrede değil — bağlayıcı olan tek şey trenler "
              u"arası mesafe."], name="Text Placeholder")
kit.drop_shape(10, "Not 202")
kit.swap_pic(10, CH + "/res-express.png", (FULL[0], 2350000, FULL[1], 3200000))
kit.note(10, u"Bu sanal kuplaj icin en elverisli vaka: hicbir tren durmuyor, "
             u"herkes hat hizinda. Nispi fren mesafesinin kazanci hizla buyudugu "
             u"icin fark burada aciliyor - 39 saniyeden 32 saniyeye, %18.\n"
             u"Sabit blogun 139 saniyede kalmasinin sebebi sinyalizasyon felsefesi "
             u"degil, blok uzunlugunun kendisi: 900 metrelik bir blok, tren nerede "
             u"olursa olsun kaybedilen mesafedir.\n"
             u"ONERI - BURAYA GIF/VIDEO: duraksiz kosunun canli semasi. Uc sistemi "
             u"yan yana gostermek en carpici olani; grafigin yerine degil, "
             u"grafikten once gosterilebilir.")

# ============================================================ 11 DURAKLAMALI
kit.title(11, u"DURAKLAMALI (ALL-STOP) İŞLETME")
kit.body(11, [u"22 duruşlu tur — bağlayıcı kısıt artık sinyalizasyon değil, "
              u"peron işgali."], name="Text Placeholder")
kit.drop_shape(11, "Not 203")
kit.swap_pic(11, CH + "/res-stopping.png", (FULL[0], 2350000, FULL[1], 3200000))
kit.note(11, u"Ayni ag, ayni filo, tek fark her istasyonda durulmasi. Sanal "
             u"kuplajin ustunlugu %18'den %9'a iniyor.\n"
             u"Neden: turun buyuk kismi hat hizinin altinda geciyor ve nispi frenin "
             u"kazanci hizla satin aliniyor - duran trende kazanc sifir. Daha "
             u"onemlisi, bu araligin altinda baglayan sey peron: bir peron bir takip "
             u"mesafesi degildir ve hicbir sinyalizasyon sistemi onu kisaltamaz.\n"
             u"Bu, calismanin en onemli tek bulgusu olabilir: sanal kuplajin "
             u"kazanci isletme bicimine bagli, teknolojinin kendisine degil. "
             u"Aoun da duraklamali isletmede kazancin %2'ye indigini buluyor - "
             u"ayni yon.\n"
             u"ONERI - BURAYA GIF/VIDEO: duraklamali kosunun semasi; peron "
             u"isgalinin baglayici oldugu an gorulsun.")

# ========================================================== 12 BOZUCU ETKİ
kit.title(12, u"BOZUCU ETKİ ALTINDA DAVRANIŞ")
kit.body(12, [
    u"Üç bozucu etki, iki okuma: aynı tarifede ve her sistem kendi "
    u"sürdürülebilir aralığında.",
    u"Kazanç sistemin kendisinden değil, elinde kalan paydan geliyor.",
], name="Text Placeholder")
# Iki ayri grafik yan yana: solda ayni tarife, sagda kendi siniri.
kit.swap_pic(12, CH + "/res-disruption-a.png",
             (FULL[0], 2330000, 6150000, 3350000))
kit.add_pic(12, CH + "/res-disruption-b.png",
            (6650000, 2330000, 5100000, 3350000), "Bozucu-b")
kit.note(12, u"METODOLOJI: bir sistemi digerinin tarifesinde kosturmak haksiz "
             u"karsilastirmadir - payi olan kazanir. O yuzden iki okuma var.\n"
             u"SOL: ikisi de 78 saniyede, yani isletmecinin bugun hareketli "
             u"blokla kostugu tarife. Uc olayin ucunde de ayni trenler, ayni "
             u"tarife; tek degisen sinyalizasyon.\n"
             u"HIZ KISITLAMASI: 455 saniyeye karsi 455 saniye. Tam olarak "
             u"ayni. Sebebi su: kisitlama HATTIN kendisine uygulaniyor ve her "
             u"treni birbirinden bagimsiz olarak ayni sekilde yavaslatiyor. "
             u"Ortada kuyruk yok, yani nispi frenin kisaltacagi bir takip "
             u"mesafesi de yok. Sanal kuplaj burada hicbir sey veremez.\n"
             u"KAPI ARIZASI: 1162'ye karsi 1009 saniye, %13 az. Burada kuyruk "
             u"VAR - bir tren peronda takiliyor, arkasindakiler ona yetisiyor. "
             u"Kuyruk tam olarak nispi frenin kisalttigi seydir.\n"
             u"BULGU: sanal kuplaj gecikmeyi degil KUYRUGU soguruyor. Hattin "
             u"kendisi yavassa yapabilecegi bir sey yok.\n"
             u"Yayilan gecikme ayrica: kapi arizasinda MB 982 s, VC 829 s - "
             u"%16 az. Slayttaki %13 toplam uzerinden, %16 yayilan uzerinden; "
             u"ikisi de dogru, farkli buyuklukler.\n"
             u"SAG: kontrol deneyi. Her sistem kendi tum-yesil sinirinda - "
             u"hareketli blok 78, sanal kuplaj 71. Ikisinde de pay yok ve fark "
             u"1162'ye karsi 1156: alti saniye, %0.5. Yani ayri bir toparlanma "
             u"davranisi YOK. Teknoloji yedi saniye veriyor, baska bir sey "
             u"degil; onu ya trene harcarsin ya dayanikliliga.\n"
             u"Hiz kisitlamasi sag grafikte yok cunku iki tarife kisitlamanin "
             u"saatine farkli sayida tren sokuyor; o satir tarifeden kirleniyor. "
             u"Kayit icin: MB@71 417 s, VC@71 355 s.")

# ================================================================= 13 KONVOY
kit.title(13, u"KONVOY DAVRANIŞI")
kit.body(13, [
    (0, u"Kural: 70 km/h ile sınırlı; yalnızca öndekine yaklaşırken hat hızına "
        u"serbest bırakılıyor."),
    (0, u"Kural aralığı kısaltıyor, ama trenler kalıcı konvoy kurmuyor: "
        u"kuplajlar kısa ve ikişerli."),
], name="Text Placeholder")
kit.swap_pic(13, CH + "/res-convoy.png", (FULL[0], 2700000, FULL[1], 2980000))
kit.note(13, u"Sagdaki iki panel iz dosyasindan sayildi. Bir tik kuplajli "
             u"sayiliyor: yetki gerekcesi 'coupled to X' iceriyor ve 'uncoupled' "
             u"icermiyor - yani sanal kuplaj nispi fren mesafesi veriyor VE tren "
             u"kuplaj esiginin icinde.\n"
             u"DURAKSIZ: kosma suresinin %14.5'i kuplajli, ortalama kuplaj 31 s, "
             u"en uzunu 135 s. Trenler ikiser ikiser esleşiyor - X02 X01'e, X04 "
             u"X03'e. Yani kural gercekten cift kuruyor.\n"
             u"DURAKLAMALI: %8.6, ortalama 19 s, en uzunu 30 s. Kuplaj kuruluyor "
             u"ama her istasyonda bozuluyor; kalici konvoy yok.\n"
             u"En buyuk konvoy iki tren. Uc ve daha buyuk konvoy bu kurulumda "
             u"olusmuyor - kuplaj esigi (800 m) ve istasyon sikligi buna izin "
             u"vermiyor.\n"
             u"DURUST KAYIT: sinirin kendi maliyeti duraksiz turda 213 saniye; "
             u"serbest birakma bunun 150 saniyesini geri aliyor, tamamini degil. "
             u"Ayrica tesvikli satir 70 km/h'e gore planlanip 90 kosabildigi icin "
             u"toparlanma payi tasiyor - kuralin payi ile planin payi bu kurulumda "
             u"ayrilamiyor.\n"
             u"ONERI - BURAYA GIF: iki trenin kuplaj kurup istasyonda ayrilmasi.")

# ====================================================== 14 KARŞILAŞTIRMA
kit.title(14, u"KARŞILAŞTIRMALI SONUÇLAR")
kit.body(14, [
    (0, u"Aynı ağ, aynı filo, aynı tarife — tek değişken sinyalizasyon."),
], name="Text Placeholder")
kit.add_pic(14, CH + "/res-summary.png", (FULL[0], 2200000, FULL[1], 3450000),
            "Ozet")
kit.note(14, u"Bu slayt butun deneyleri tek karede topluyor.\n"
             u"Buyuk sicrama sabit bloktan hareketli bloga: duraklamali turda 148 "
             u"saniyeden 78'e, kapasite neredeyse ikiye katlaniyor (%47). Hareketli "
             u"bloktan sanal kuplaja gecis ise 78'den 71'e, %9.\n"
             u"Isletmeci icin yatirim sirasini belirleyen sey bu: buyuk kazanc "
             u"zaten hareketli blokta aliniyor, sanal kuplaj onun ustune koyuyor.\n"
             u"Duraksiz isletmede tablo degisiyor: orada sanal kuplajin katkisi "
             u"%18, yani iki kati. Kazanc isletme bicimine bagli.")

# =========================================================== 15 ANA BULGULAR
kit.title(15, u"ANA BULGULAR")
kit.body(15, [
    (0, u"SANAL KUPLAJ NEREDE KAZANDIRIYOR"),
    (1, u"Duraksız işletme   39 s → 32 s   (%18)   ·   konvoy kuralıyla "
        u"25 s → 17 s   (%32)"),
    (1, u"Aynı tarifede bozucu etki altında   %16 daha az yayılan gecikme"),
    (0, u"NEREDE KAZANDIRMIYOR"),
    (1, u"Duraklamalı işletme   78 s → 71 s   (%9) — kısıt peron, ve peron bir "
        u"takip mesafesi değil"),
    (1, u"Kendi sürdürülebilir aralığında bozucu etki altında   %0.6"),
    (0, u"BAĞLAMI KAÇIRMAMAK İÇİN"),
    (1, u"Asıl sıçrama sabit blok → hareketli blok:   148 s → 78 s   (%47)"),
], name="Text Placeholder")
kit.note(15, u"Bu slaydin isi dengeli olmak. Sanal kuplaj her kosulda daha iyi "
             u"degil; ISLETME BICIMINE bagli olarak daha iyi.\n"
             u"Duraksiz, yuksek hizli, az duraklı bir hatta kazanc gercek ve "
             u"buyuk. Her istasyonda duran bir hatta kazanc kuculuyor cunku "
             u"baglayan sey artik sinyalizasyon degil.\n"
             u"Ve buyuk resimde: asil kazanci sabit bloktan hareketli bloga gecis "
             u"veriyor. Sanal kuplaj bunun ustune bir kat daha koyuyor - onemli "
             u"ama ikincil bir adim.\n"
             u"SINIRLAMALAR (sorulursa): (1) egim sinyalizasyon katmaninin yetki "
             u"hesabinda dikkate alinmiyor, sadece trenin fren mesafesinde. "
             u"(2) Konvoy satiri planlama payi tasiyor. (3) Tek arac tipi, tek "
             u"ag geometrisi. (4) V2V kapsama kaybi modellenmedi.")

# ============================================================ 16 YEDİ SANİYE
kit.title(16, u"YEDİ SANİYE: TRENE Mİ, DAYANIKLILIĞA MI?")
kit.body(16, [
    (0, u"Ölçüm tek bir şey söylüyor: teknoloji 7 saniye veriyor. Nereye "
        u"harcanacağı bir işletme kararı."),
    (0, u"TRENE HARCARSAN"),
    (1, u"%9 daha fazla tren — ama yeni tarife, yeni diyagram, yeni roster"),
    (0, u"DAYANIKLILIĞA HARCARSAN"),
    (1, u"Aynı trenler, %16 daha az yayılan gecikme — yalnızca araç donanımı"),
    (0, u"UYGULANABİLİRLİK"),
    (1, u"Gerektirdikleri: V2V haberleşme, tren–tren koordinasyonu, araç üstü "
        u"sistemler, ETCS L3 altyapısı"),
    (1, u"Bu çalışmada maliyet analizi yapılmadı; olası kazanç saha donanımına "
        u"bağımlılığın azalmasıdır"),
], name="Text Placeholder")
kit.note(16, u"KAPANIS: sanal kuplaj kapasitede hareketli bloktan iyi, ama karari "
             u"kapasite vermiyor. Aoun'un olctugu agirliklara gore karar %45 "
             u"guvenlik, %32 regulasyon onayi, sadece %5.6 kapasite. Hareketli "
             u"blok bugun daha olgun oldugu icin genel skorda one geciyor.\n"
             u"DIKKAT - burada ne SOYLEMIYORUM: sanal kuplajin daha ucuz oldugunu "
             u"soylemiyorum, cunku bu calismada maliyet analizi yapmadim. "
             u"Soyleyebilecegim sey su: sanal kuplaj ayirmayi trenin uzerine "
             u"tasiyor, dolayisiyla saha donanimina bagimliligi azaltma potansiyeli "
             u"var. Bunun paraya ne kadar cevrildigi ayri bir calisma konusu.\n"
             u"Teknoloji olgunlastikca ve araç ustu sistemlerin maliyeti dustukce "
             u"tablo sanal kuplaj lehine doner; olctugum kapasite farki bu "
             u"beklentinin sayisal tarafini destekliyor. Ama bugun icin durust "
             u"cevap: duraksiz isletmede evet, duraklamali isletmede marjinal.")

# --------- sayfa sayaci: sablonun "/22"si ve elle yazilmis iki numara
master = "ppt/slideMasters/slideMaster1.xml"
kit._write(master, kit._read(master).replace("<a:t>/22</a:t>",
                                             "<a:t>/%d</a:t>" % len(kit.order())))
kit.body(2, [u"2/%d" % len(kit.order())], name="Rectangle 18")
kit.body(3, [u"3/%d" % len(kit.order())], name="Rectangle 8")

kit.pack(BASE + "/ASELSAN-Sunum-v3.pptx")
