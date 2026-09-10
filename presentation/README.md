# `presentation/` — sunumdaki her sayının kaynağı

Sunumda gösterilen hiçbir sayı elle yazılmadı. Bu klasör, o sayıları üreten
senaryoları, tarifeleri, tarama betiklerini ve grafik kodlarını bir arada
tutar; amacı sonuçların **kendi başına yeniden üretilebilmesidir**.

```
presentation/
  README.md          bu dosya — slayt → komut → sayı haritası
  run_all.sh         her şeyi sırayla koşar
  ring/              kullanılan senaryo, tarife ve altyapı dosyalarının kopyası
  charts/            grafik kodları
  figures/           üretilen PNG'ler
  results/           koşu çıktıları (run_all.sh doldurur)
```

`ring/` altındakiler `scenarios/ring/`'in **kopyasıdır**. Kanonik olan
`scenarios/ring/`; buradakiler sunumun hangi sürümle üretildiğini dondurmak
için var. Betikler yol olarak `dirname(dirname(__file__))`'i depo kökü kabul
ettiği için `presentation/ring/` içinden değişiklik yapmadan çalışırlar.

---

## Hızlı başlangıç

```sh
sh presentation/run_all.sh figures     # sadece grafikler, koşu yok (~30 s)
sh presentation/run_all.sh disruption  # bozucu etki koşuları (~10 dk)
sh presentation/run_all.sh             # hepsi (~1 saat, taramalar yavaş)
```

Adımlar tek tek de koşulur: `stats`, `headway`, `express`, `convoy`,
`convoylog`, `disruption`, `figures`.

---

## Slayt → komut haritası

| # | slayt | grafik | sayıyı üreten komut |
|---|---|---|---|
| 1 | Kapak | — | — |
| 2 | İçerik | — | — |
| 3 | Çalışma | `flow.png` | veri yok, kavramsal şema |
| 4 | Test Ağı | `network.png` | istasyon adları ve km'leri `ring/infrastructure.yaml`'dan **okunuyor**; tur süresi 79:09 → `python stats.py scenarios/ring` |
| 5 | Literatür | `papers.png` | "Bu çalışma" sütunu → slayt 12, 13 ve 15'in sayıları |
| 6 | Sinyalizasyon | `systems.png` | 148 / 78 / 71 → `_sweep_headway.py` |
| 7 | Tren Modeli | — | sayı yok, model tanıtımı |
| 8 | Hareket Denklemleri | — | sayı yok, formülasyon |
| 9 | Kullanılan Parametreler | — | `python stats.py scenarios/ring` |
| 10 | Fren Mesafesi | `res-braking.png` | `python presentation/charts/physics.py` — her terim `dynamics`/`driver` fonksiyonlarından |
| 11 | Hızlanma | `res-traction.png` | aynı betik — `achievable_accel` ile tik tik integrasyon |
| 12 | Eğimli Varyant | `res-gradient.png` | `python run.py presentation/ring/scenario-grade.yaml --check` (blok payı) · `python stats.py presentation/ring/scenario-grade.yaml` (tur, eğim) · profil `python presentation/charts/gradient.py` |
| 13 | Duraksız İşletme | `res-express.png` | `python presentation/ring/_sweep_express.py <sistem>` |
| 14 | Duraklamalı İşletme | `res-stopping.png` | `python presentation/ring/_sweep_headway.py <sistem>` |
| 15 | Bozucu Etki | `res-disruption-a.png` + `res-disruption-b.png` | `python run.py presentation/ring/scenario-{78,71}-{dwell,tsr,both}.yaml --propagation/--headless --system <sistem>` |
| 16 | Konvoy Davranışı | `res-convoy.png` | aralıklar → `_sweep_convoy.py --headway [--stopping]`; kuplaj metrikleri → `run.py ... --log` + `convoy_stats.py` |
| 17 | Karşılaştırmalı Sonuçlar | `res-summary.png` | slayt 13 ve 14 ile aynı koşular |
| 18 | Ana Bulgular | — | slayt 13, 14, 15, 16 |
| 19 | Yedi Saniye | — | slayt 14 (7 s / %9) ve slayt 15 (%13 / %0.5) |
| 20 | Kaynaklar | — | — |
| 21 | Teşekkürler | — | — |

`<sistem>` = `fixed_block_3aspect` | `etcs_moving_block` | `virtual_coupling`

---

## ÖNEMLİ: sayılar grafik kodunda sabit yazılıdır

Grafik betikleri koşu çıktısını **ayrıştırmıyor**; ölçülen değer betiğin
başında sabit olarak duruyor ve hangi komuttan geldiği aynı yerde yazılı.
Yani bir sayıyı değiştirmek için önce koşuyu yapıp sonra sabiti güncellemek
gerekir. Bunun tek istisnası `network.py` (altyapı dosyasını okur),
`_plot_motion.py` (fiziği koşar) ve `convoy_stats.py` (iz dosyasını sayar).

Hangi sayı nerede:

| dosya | sabit | değer |
|---|---|---|
| `charts/results.py` | `EXPRESS` | `[139, 39, 32]` |
| `charts/results.py` | `STOPPING` | `[148, 78, 71]` |
| `charts/convoy2.py` | `HEADWAY` | duraksız `[25, 23, 17]`, duraklamalı `[69, 68, 63]` |
| `charts/convoy2.py` | `COUPLED_PCT` | duraksız `14.5`, duraklamalı `8.6` |
| `charts/convoy2.py` | `EPISODE_S` | duraksız `(31, 135)`, duraklamalı `(19, 30)` |
| `charts/disruption2.py` | `MB78` | `(982, 1162)` |
| `charts/disruption2.py` | `VC78` | `(829, 1020)` |
| `charts/disruption2.py` | `VC71` | `(976, 1156)` |
| `charts/deckgfx.py` | `ROWS` son satırı | `148 s / 78 s / 71 s` |

`charts/physics.py` bu tablonun dışında: fren mesafesinin dört terimini ve
hızlanma eğrisini `dynamics` fonksiyonlarını çağırarak **hesaplıyor**, hiçbir
değeri sabit tutmuyor. Düz hattaki toplamı `driver.stopping_distance()` ile
karşılaştıran bir `assert` var — tutmazsa grafik üretilmiyor.

---

## Adım adım ne koşuyor

### 1. `stats` — model büyüklükleri (slayt 7, 9)
```sh
python stats.py scenarios/ring
```
Kütle 216 t, etkin kütle 233.3 t, güç 2332.8 kW, taban hız 36 km/h, Davis
`R(v) = 1404 + 28.1·v + 3.74·v²`, fren zinciri `44.4 + 22.2 + 246.9 + 25.0 =
338.6 m`, iki emniyet payı (sistem 100/50/yok + sürücü 25). Hiçbiri senaryo
dosyasında yazmıyor; hepsi türetiliyor ve yanında formülüyle basılıyor.

### 2. `headway` — duraklamalı tur (slayt 6, 11, 14)
```sh
python presentation/ring/_sweep_headway.py fixed_block_3aspect
python presentation/ring/_sweep_headway.py etcs_moving_block
python presentation/ring/_sweep_headway.py virtual_coupling
```
Aynı uçuşu 5 dakikadan bir dakikanın altına kadar her aralıkta koşar. Aranan
şey **tüm-yeşil sınır**: hiçbir trenin bir diğerini yavaşlatmadığı ve hiç
kimsenin geç kalmadığı en kısa aralık. Tarife her aralıkta engelsiz tur
sürelerinden yeniden kuruluyor, yani ortaya çıkan gecikme trenlerin
birbirini engellemesinden geliyor, kurulamayan bir tarifeden değil.

→ **148 s / 78 s / 71 s** (24 / 46 / 51 tren-saat)

### 3. `express` — duraksız tur (slayt 10, 14)
```sh
python presentation/ring/_sweep_express.py <sistem>
```
Aynı tarama, peronsuz tur üzerinde.
→ **139 s / 39 s / 32 s** (26 / 92 / 112 tren-saat)

### 4. `convoy` — konvoy kuralının aralığa etkisi (slayt 13)
```sh
python presentation/ring/_sweep_convoy.py --headway
python presentation/ring/_sweep_convoy.py --headway --stopping
```
Üç satır üretir: hat hızı serbest → 70 km/h sınırlı → sınır + öne yaklaşınca
serbest bırakma.
→ duraksız **25 → 23 → 17 s**, duraklamalı **69 → 68 → 63 s**

`--stopping` bayrağını `--headway`'den **önce** yazmak gerekmiyor; betik onu
`sys.argv`'den çıkarıyor.

### 5. `convoylog` — kuplaj metrikleri (slayt 13)
```sh
python run.py presentation/ring/scenario-convoy.yaml --headless \
    --log presentation/results/convoy-express.csv --log-every 5
python run.py presentation/ring/scenario-convoy-stopping.yaml --headless \
    --log presentation/results/convoy-stopping.csv --log-every 5
python presentation/charts/convoy_stats.py \
    presentation/results/convoy-express.csv \
    presentation/results/convoy-stopping.csv
```
`convoy_stats.py` iz dosyasındaki `reason` sütununu sayar. Bir tik **kuplajlı**
sayılıyorsa gerekçe `coupled to X` içeriyor ve `, uncoupled` içermiyor demektir
— yani sanal kuplaj nispi fren mesafesi veriyor **ve** tren kuplaj eşiğinin
içinde (`virtual_coupling.py: _is_coupled`).

→ duraksız **%14.5 · 201 olay · ort. 31 s · en uzun 135 s**
→ duraklamalı **%8.6 · 233 olay · ort. 19 s · en uzun 30 s**

### 6. `disruption` — bozucu etki (slayt 12, 16)
```sh
python run.py presentation/ring/scenario-78-dwell.yaml --propagation --system etcs_moving_block
python run.py presentation/ring/scenario-78-dwell.yaml --propagation --system virtual_coupling
python run.py presentation/ring/scenario-71-dwell.yaml --propagation --system virtual_coupling
# aynısı -both.yaml için
```
Kapı arızası: R06 servisi Gölbaşı 2'de 90 s fazla bekliyor, birincil gecikme
180 s. Okunacak satır `knock-on delay`.

Toplam gecikme (birincil + yayılan), s:

| olay | MB @78 | VC @78 | MB @71 | VC @71 |
|---|---|---|---|---|
| hız kısıtlaması | 455 | 455 | 417 | 355 |
| kapı arızası | 1162 | 1009 | 1169 | 1156 |
| ikisi birden | 1162 | 1020 | 1169 | 1156 |

Kapı arızasının **yayılan** kısmı ayrıca: MB@78 982 s, VC@78 829 s (%16 az),
VC@71 976 s. Grafikteki %13 toplam üzerinden, %16 yayılan üzerinden.

Hız kısıtlaması `-tsr` dosyalarında `--headless` ile ölçülür, `--propagation`
ile değil: kısıtlama **hattın kendisine** uygulandığı için üstünden geçen her
tren doğrudan etkilenmiş sayılır ve rapor tüm gecikmeyi birincil gösterir.

**Neden iki okuma:** bir sistemi diğerinin tarifesinde koşturmak haksız
karşılaştırmadır, payı olan kazanır. Aynı tarifede (78 s) sanal kuplaj kapı
arızasında %13 kazanıyor; her sistem kendi sınırında koşturulduğunda fark
%0.5'e iniyor.

**Hız kısıtlaması aynı tarifede tam olarak berabere: 455 s / 455 s.** Sebebi
kısıtlamanın hattın kendisine uygulanması: her treni birbirinden bağımsız
olarak aynı şekilde yavaşlatıyor, ortada kuyruk yok, nispi frenin
kısaltacağı bir takip mesafesi yok. Sanal kuplaj gecikmeyi değil **kuyruğu**
soğuruyor.

Hız kısıtlaması **kendi sınırı** karşılaştırmasında (78 s / 71 s) yok: iki
tarife kısıtlamanın saatine farklı sayıda tren sokuyor, o satır tarifeden
kirleniyor. Kayıt için MB@71 417 s, VC@71 355 s.

### 7. `figures` — grafikler
```sh
python presentation/charts/network.py      # network.png
python presentation/charts/deckgfx.py      # flow.png papers.png systems.png
python presentation/charts/results.py      # res-express/stopping/summary.png
python presentation/charts/convoy2.py      # res-convoy.png
python presentation/charts/disruption2.py  # res-disruption-a/-b.png
python _plot_motion.py presentation/figures/motion.png
```
Palet ve ortak biçim `charts/style.py`'de: sabit blok `#355FA8`, hareketli
blok `#58B0E8`, sanal kuplaj `#E8871F`. Üç sistem her grafikte aynı üç rengi
alır.

---

## `ring/` içindeki dosyalar

| dosya | ne için |
|---|---|
| `infrastructure.yaml` | ağın kendisi — 11 istasyon, hız profili, bloklar, makaslar |
| `_generate_timetable.py` | tarifeyi engelsiz tur sürelerinden kurar; taramaların hepsi bunu kullanır |
| `_generate_express.py` | duraksız varyant (`ring.LAP`'i yeniden bağlar) |
| `_generate_convoy.py` | konvoy kuralının tarifesi |
| `_sweep_headway.py` | duraklamalı tur, tüm-yeşil sınır |
| `_sweep_express.py` | duraksız tur, tüm-yeşil sınır |
| `_sweep_convoy.py` | konvoy kuralının üç satırı |
| `_sweep_grade.py` | aynı duraklamalı tarama, eğimli çevrim üzerinde — ölçüldü: hareketli blok **78 s**, sanal kuplaj **71 s**, yani düz çevrimin birebir aynısı; eğim aradaki 7 s'yi değiştirmiyor. **Sunumda yok** |
| `scenario.yaml` + `timetable.yaml` | temel çevrim (5 dk aralık) |
| `scenario-express.yaml` + `timetable-express.yaml` | duraksız |
| `scenario-convoy*.yaml` + `timetable-convoy*.yaml` | konvoy kuralı (`uncoupled_speed_kmh: 70`, `coupling_margin_m: 800`) |
| `scenario-grade.yaml` + `infrastructure-grade.yaml` + `timetable-grade.yaml` | eğimli varyant — ruling 15‰, tur boyunca toplamı sıfır |
| `scenario-78-*.yaml` + `timetable-78.yaml` | hareketli bloğun kendi sınırı |
| `scenario-71-*.yaml` + `timetable-71.yaml` | sanal kuplajın kendi sınırı |

`scenario-*-dwell` kapı arızası, `-tsr` hız kısıtlaması, `-both` ikisi
birden.

---

## Sunumda kullanılmayan, ölçülmemiş şeyler

Bunlar için koşu **yok**; slayda koymak istersen önce üretilmeli.

| ne | ne gerekir |
|---|---|
| Sistem başına seyahat süresi / ortalama gecikme | her sistemin kendi aralığında birer koşu (6 koşu) |
| Sabit blok bozucu etki altında | sabit bloğun sınırı 148 s; 78 s'de koşamaz, ayrı bir tarife üretilmeli |
| 2'den büyük konvoy | ölçüldü, oluşmuyor — kuplaj eşiği 800 m ve istasyon sıklığı izin vermiyor |
| Maliyet karşılaştırması | çalışmada yok; slayt 16 bunu açıkça söylüyor |
