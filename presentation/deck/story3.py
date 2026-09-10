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

# Fizik blogu: denklemler -> parametreler -> fren mesafesi -> hizlanma.
# Dordu de lvl0/lvl1 yapisi istiyor; o yapiya sahip tek sablon 9. slayt,
# o yuzden ucunu kopyalayip sonra hepsini sirasina yerlestiriyoruz.
for _ in range(3):
    kit.duplicate(9, len(kit.order()))
kit.arrange([1, 2, 3, 4, 5, 6, 7, 19, 9, 20, 21, 10, 11, 12, 13, 14, 15,
             16, 17, 18])          # eski 8 (hareket egrileri) dusuyor

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
kit.title(7, u"TREN MODELİ")
kit.body(7, [
    u"Tek boyutlu hareket: konum tek bir skaler, hız ve ivme ondan türer.",
    u"Dört kuvvet: çeki, yuvarlanma direnci, eğim, fren.",
    u"Jerk sınırı — ne çeki ne fren anında oluşur.",
    u"Sürücü izin verilen her metreyi kullanır, hız sınırını aşmaz.",
], name="Text Placeholder")
kit.note(7, u"Bu slayt modelin NE OLDUGUNU soyluyor; denklemleri bir sonraki, "
            u"sayilari ondan sonraki slayt veriyor.\n"
            u"TEK BOYUT: tren bir noktada degil, bir uzunluga sahip. Konumu tek "
            u"skaler ama uzunlugu her yerde hesaba giriyor - trenin altindaki hiz "
            u"siniri burnundan kuyruguna en dusuk olan, altindaki egim ise "
            u"uzunlukla agirliklandirilmis ortalama. Trenin %30'u bir egimde "
            u"%70'i baskaysa kuvvet buna gore hesaplaniyor.\n"
            u"JERK: ivmenin degisim hizi, ve yolcu konforu standartlarinin "
            u"olctugu buyukluk. Modelde fren brake build-up suresinden turetiliyor: "
            u"2 saniyede tam frene ulasan bir fren, saniyede 0.5 m/s2 "
            u"degisebilen bir frendir.\n"
            u"SURUCU ideal ama 'agresif' anlamda: hicbir metreyi bosa harcamiyor. "
            u"Amac sinyalizasyonu olcmek, surucu farkini degil.")

# ============================================================ 8 DENKLEMLER
kit.title(8, u"HAREKET DENKLEMLERİ")
kit.body(8, [
    (0, u"HAREKET DENKLEMİ"),
    (1, u"m_eff · a  =  F(v)  −  R(v)  −  m · g · sin(θ)"),
    (1, u"m_eff = m · 1.08   —   dönen kütlelerin eylemsizliği"),
    (1, u"F(v) = F₀   (v ≤ v_taban)          F(v) = P / v   (v > v_taban)"),
    (0, u"DİRENÇ — DAVIS"),
    (1, u"R(v)  =  A  +  B·v  +  C·v²          [N,  v m/s]"),
    (1, u"A, B kütleyle ölçeklenir   ·   C trenin uzunluğuyla"),
    (0, u"FREN"),
    (1, u"b(θ)  =  min(b_talep , μ·g)  +  g · sin(θ) · m / m_eff"),
    (1, u"d_fren  =  v₀² / 2b(θ)"),
    (0, u"HAREKET YETKİSİ"),
    (1, u"D  =  v₀·t_tepki  +  ½·v₀·t_buildup  +  v₀² / 2b(θ)  +  d_pay"),
], name="Text Placeholder")
kit.note(8, u"Dort denklem, dordu de simulatorun gercekten kullandigi hali.\n"
            u"HAREKET: egim sonradan eklenen bir duzeltme degil, denklemin kendi "
            u"terimi. Trenin %30'u bir egimde %70'i baskaysa kuvvet trenin "
            u"ALTINDAKI egimin uzunlukla agirliklandirilmis ortalamasindan "
            u"hesaplaniyor - tek nokta degil, trenin tamami.\n"
            u"m_eff: donen kutleler de hizlandirilmak zorunda - tekerlek, disli, "
            u"rotor. 216 t tren 233 t gibi davraniyor.\n"
            u"DAVIS: A yatak ve yuvarlanma direnci, hizdan neredeyse bagimsiz. "
            u"B flans ve ray temasi, hizla dogrusal. Ikisi de kutleyle "
            u"olcekleniyor. C aerodinamik ve kutleyle DEGIL, trenin uzunluguyla "
            u"olcekleniyor - uzun tren daha cok surtunme yuzeyi demek.\n"
            u"FREN: talep edilen oran once aderans siniriyla (mu*g) kesiliyor, "
            u"sonra egim orana ekleniyor. Egim terimi m/m_eff ile bolunuyor "
            u"cunku yercekimi statik kutleye etki ediyor ama donen parcalarin "
            u"eylemsizligi de ona direniyor. Binde 15 inis icin: 9.80665 x "
            u"0.015 / 1.08 = 0.136 m/s2, yani 1.0 fren 0.864'e dusuyor.\n"
            u"YETKI: son satir bu sunumun en cok yanlis anlasilan yeri. Bir blogu "
            u"boyutlandiran sey fren mesafesi degil, bu dort terimin toplami. "
            u"Sonraki slaytta sayilariyla var.")

# =========================================================== 9 PARAMETRELER
kit.title(9, u"KULLANILAN PARAMETRELER")
kit.body(9, [
    (0, u"ARAÇ"),
    (1, u"120 m   ·   216 t   ·   m_eff 233 t   ·   v_max 90 km/h"),
    (1, u"F₀ 233 kN   ·   P 2333 kW   ·   v_taban 36 km/h  (%40 · v_max)"),
    (1, u"Davis:   A 1404 N   ·   B 28.1 N·s/m   ·   C 3.74 N·s²/m²"),
    (0, u"FREN VE SÜRÜCÜ"),
    (1, u"servis 1.0   ·   acil 1.5 m/s²   ·   jerk 0.5 m/s³   ·   brake build-up 2.0 s"),
    (1, u"tepki 2.0 s (kabin sinyalizasyonunda 0 s)   ·   sürücü payı 25 m"),
    (0, u"SİNYALİZASYON"),
    (1, u"tehlike noktası payı:  hareketli blok 100 m · sanal kuplaj 50 m · "
        u"sabit blok yok"),
    (1, u"V2V gecikmesi 0.5 s   ·   kuplaj eşiği 800 m   ·   blok 900 m"),
    (0, u"İŞLETME"),
    (1, u"dt = 1.0 s (tümü dt = 0.5 s ile doğrulandı)   ·   12 servis   ·   "
        u"22 duruş/tur   ·   30 s bekleme"),
], name="Text Placeholder")
kit.note(9, u"Senaryo dosyasi bunlarin cogunu YAZMIYOR. Bir arac icin yazilan sey "
            u"uzunluk ve dort performans degeri: azami hiz, kalkis, servis freni, "
            u"acil fren. Kutle, etkin kutle, kalkis kuvveti, guc, taban hiz ve "
            u"Davis katsayilari bunlardan turetiliyor; stats.py hepsini yaninda "
            u"formuluyle birlikte yazdiriyor. Boylece elle girilmis tek bir sayi "
            u"yok.\n"
            u"IKI AYRI EMNIYET PAYI VAR VE TOPLANIYORLAR. Sistemin payi tehlike "
            u"noktasinin NEREDE oldugunu belirliyor; surucunun payi ise verilen "
            u"tehlike noktasindan ne kadar once durdugu - 25 m ve sinyalizasyondan "
            u"bagimsiz. Hareketli blokta bir tren ondekinin arkasindan "
            u"100 + 25 = 125 m uzakta tutuluyor.\n"
            u"SURUCU: model surucusu 'agresif' anlamda ideal - izin verilen hicbir "
            u"metreyi bosa harcamiyor, hiz sinirini da asmiyor. Bilerek boyle: "
            u"amac sinyalizasyonu olcmek, surucu farkini degil. Gercek bir surucu "
            u"daha temkinli surer ve butun sistemler ayni oranda kotulesir, yani "
            u"karsilastirma bozulmaz.\n"
            u"V2V icin 0.5 s gecikme ve kesintisiz kapsama varsayildi; kapsama "
            u"kaybi modellenmedi - bu bir sinirlama.")

# ========================================================= 10 FREN MESAFESİ
kit.title(10, u"FREN MESAFESİ")
kit.body(10, [
    (0, u"80 km/h'ten duruşa, düz hat, servis freni:   "
        u"44 + 22 + 247 + 25  =  339 m"),
    (0, u"Fren eğrisi toplamın yalnızca %73'ü. Bir bloğu boyutlandıran sayı "
        u"toplam olan."),
], name="Text Placeholder")
kit.add_pic(10, CH + "/res-braking.png", (FULL[0], 2400000, FULL[1], 3300000),
            "Fren")
kit.note(10, u"Adim adim, hepsi slayt 9'daki parametrelerden:\n"
             u"  v0 = 80 km/h = 22.22 m/s\n"
             u"  tepki    v0 x t_tepki      = 22.22 x 2.0        =  44.4 m\n"
             u"  brake build-up  v0 x t_brake build-up/2  = 22.22 x 1.0        =  22.2 m\n"
             u"  fren     v0^2 / 2b         = 493.8 / 2.0        = 246.9 m\n"
             u"  pay      surucunun payi                          =  25.0 m\n"
             u"  TOPLAM                                           = 338.6 m\n"
             u"Kabarma neden yarim: ERTMS'in yaptigi gibi, brake build-up suresinin "
             u"yarisi boyunca tren frensiz sayiliyor. Bu bir yaklasim ve dogru "
             u"boyutta oldugunu olctum: sabit oranli plan 338.6 m diyor, jerk "
             u"sinirli gercek hareketi tik tik integre ettigimde 337.9 m cikiyor. "
             u"0.7 metre.\n"
             u"EGIM: binde 15 iniste b = 1.0 - 9.80665 x 0.015 / 1.08 = 0.864, "
             u"fren egrisi 247'den 286 metreye cikiyor, toplam 378 m. Egim "
             u"teriminin 1.08'e bolunmesi, yercekiminin statik kutleye etki "
             u"etmesi ama donen parcalarin eylemsizliginin de ona direnmesinden.\n"
             u"ACIL FREN 1.5 m/s2 ile fren egrisi 165 m, toplam 256 m. Ama "
             u"surucunun cizdigi egri SERVIS freniyle cizilir; acil fren son "
             u"caredir, planlanan bir sey degil.\n"
             u"Fren egrisi Davis direncini kasten saymaz: bir fren egrisi tren "
             u"hafif, temiz ve arkadan ruzgar alirken de tutmali. Hata emniyetli "
             u"yonde.")

# ============================================================== 11 HIZLANMA
kit.title(11, u"HIZLANMA")
kit.body(11, [
    (0, u"Taban hıza kadar sabit kuvvet (233 kN), üstünde sabit güç "
        u"(2333 kW / v)."),
    (0, u"Duruştan 80 km/h'e:   31 s,   392 m.   Direnç 80 km/h'te 3.9 kN — "
        u"çekinin %4'ü."),
], name="Text Placeholder")
kit.add_pic(11, CH + "/res-traction.png", (FULL[0], 2400000, FULL[1], 3300000),
            "Hizlanma")
kit.note(11, u"SOL: ceki egrisi iki parcali. Taban hiza kadar kuvvet sabit - "
             u"F0 = kalkis ivmesi x etkin kutle = 1.0 x 233.3 t = 233.3 kN. "
             u"Taban hiz azami hizin %40'i, yani 36 km/h. Ustunde guc sabit "
             u"kaliyor ve kuvvet P/v ile dusuyor: P = F0 x v_taban = 233.3 kN x "
             u"10 m/s = 2333 kW, tonuna 10.8 kW - bu tur bir arac icin normal "
             u"bandin (10-20) alt ucu.\n"
             u"Direnc ne kadar kucuk oldugu carpici: 80 km/h'te 3.9 kN, cekinin "
             u"%4'u. Yani bir treni hizlandirmanin maliyeti neredeyse tamamen "
             u"eylemsizlik, surtunme degil. Bu, duraklamali bir hatta neden bu "
             u"kadar cok zaman kaybedildigini de acikliyor.\n"
             u"SAG: gercek hareket, jerk sinirli. Ilk saniyelerde ivme 0'dan "
             u"1.0'a jerk siniriyla cikiyor (0.5 m/s3, yani 2 saniye), sonra "
             u"36 km/h'e kadar sabit, ustunde dusuyor. 80 km/h'e 31 saniyede ve "
             u"392 metrede variliyor - 3.1 km'lik bir istasyon araliginin sekizde "
             u"biri.\n"
             u"Karsilastirma icin fren: 80'den duruşa 247 metre. Yani bu arac "
             u"hizlanirken durdugundan bir buçuk kat fazla yol aliyor.")

# ================================================================ 12 EXPRESS
kit.title(12, u"DURAKSIZ (EXPRESS) İŞLETME")
kit.body(12, [u"Peron kısıtı devrede değil — bağlayıcı olan tek şey trenler "
              u"arası mesafe."], name="Text Placeholder")
kit.drop_shape(12, "Not 202")
kit.swap_pic(12, CH + "/res-express.png", (FULL[0], 2350000, FULL[1], 3200000))
kit.note(12, u"Bu sanal kuplaj icin en elverisli vaka: hicbir tren durmuyor, "
             u"herkes hat hizinda. Nispi fren mesafesinin kazanci hizla buyudugu "
             u"icin fark burada aciliyor - 39 saniyeden 32 saniyeye, %18.\n"
             u"Sabit blogun 139 saniyede kalmasinin sebebi sinyalizasyon felsefesi "
             u"degil, blok uzunlugunun kendisi: 900 metrelik bir blok, tren nerede "
             u"olursa olsun kaybedilen mesafedir.\n"
             u"ONERI - BURAYA GIF/VIDEO: duraksiz kosunun canli semasi. Uc sistemi "
             u"yan yana gostermek en carpici olani; grafigin yerine degil, "
             u"grafikten once gosterilebilir.")

# ============================================================ 13 DURAKLAMALI
kit.title(13, u"DURAKLAMALI (ALL-STOP) İŞLETME")
kit.body(13, [u"22 duruşlu tur — bağlayıcı kısıt artık sinyalizasyon değil, "
              u"peron işgali."], name="Text Placeholder")
kit.drop_shape(13, "Not 203")
kit.swap_pic(13, CH + "/res-stopping.png", (FULL[0], 2350000, FULL[1], 3200000))
kit.note(13, u"Ayni ag, ayni filo, tek fark her istasyonda durulmasi. Sanal "
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

# ========================================================== 14 BOZUCU ETKİ
kit.title(14, u"BOZUCU ETKİ ALTINDA DAVRANIŞ")
kit.body(14, [
    u"Üç bozucu etki, iki okuma: aynı tarifede ve her sistem kendi "
    u"sürdürülebilir aralığında.",
    u"Kazanç sistemin kendisinden değil, elinde kalan paydan geliyor.",
], name="Text Placeholder")
# Iki ayri grafik yan yana: solda ayni tarife, sagda kendi siniri.
kit.swap_pic(14, CH + "/res-disruption-a.png",
             (FULL[0], 2330000, 6150000, 3350000))
kit.add_pic(14, CH + "/res-disruption-b.png",
            (6650000, 2330000, 5100000, 3350000), "Bozucu-b")
kit.note(14, u"METODOLOJI: bir sistemi digerinin tarifesinde kosturmak haksiz "
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

# ================================================================= 15 KONVOY
kit.title(15, u"KONVOY DAVRANIŞI")
kit.body(15, [
    (0, u"Kural: 70 km/h ile sınırlı; yalnızca öndekine yaklaşırken hat hızına "
        u"serbest bırakılıyor."),
    (0, u"Kural aralığı kısaltıyor, ama trenler kalıcı konvoy kurmuyor: "
        u"kuplajlar kısa ve ikişerli."),
], name="Text Placeholder")
kit.swap_pic(15, CH + "/res-convoy.png", (FULL[0], 2700000, FULL[1], 2980000))
kit.note(15, u"Sagdaki iki panel iz dosyasindan sayildi. Bir tik kuplajli "
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

# ====================================================== 16 KARŞILAŞTIRMA
kit.title(16, u"KARŞILAŞTIRMALI SONUÇLAR")
kit.body(16, [
    (0, u"Aynı ağ, aynı filo, aynı tarife — tek değişken sinyalizasyon."),
], name="Text Placeholder")
kit.add_pic(16, CH + "/res-summary.png", (FULL[0], 2200000, FULL[1], 3450000),
            "Ozet")
kit.note(16, u"Bu slayt butun deneyleri tek karede topluyor.\n"
             u"Buyuk sicrama sabit bloktan hareketli bloga: duraklamali turda 148 "
             u"saniyeden 78'e, kapasite neredeyse ikiye katlaniyor (%47). Hareketli "
             u"bloktan sanal kuplaja gecis ise 78'den 71'e, %9.\n"
             u"Isletmeci icin yatirim sirasini belirleyen sey bu: buyuk kazanc "
             u"zaten hareketli blokta aliniyor, sanal kuplaj onun ustune koyuyor.\n"
             u"Duraksiz isletmede tablo degisiyor: orada sanal kuplajin katkisi "
             u"%18, yani iki kati. Kazanc isletme bicimine bagli.")

# =========================================================== 17 ANA BULGULAR
kit.title(17, u"ANA BULGULAR")
kit.body(17, [
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
kit.note(17, u"Bu slaydin isi dengeli olmak. Sanal kuplaj her kosulda daha iyi "
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

# ============================================================ 18 YEDİ SANİYE
kit.title(18, u"YEDİ SANİYE: TRENE Mİ, DAYANIKLILIĞA MI?")
kit.body(18, [
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
kit.note(18, u"KAPANIS: sanal kuplaj kapasitede hareketli bloktan iyi, ama karari "
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
