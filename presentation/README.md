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
| 5 | Literatür | `papers.png` | "Bu çalışma" sütunu → slayt 10, 11 ve 13'ün sayıları; diğer iki sütun makalelerden |
| 6 | Sinyalizasyon | `systems.png` | 148 / 78 / 71 → `_sweep_headway.py` (bkz. slayt 11) |
| 7 | Tren Modeli | — | `python stats.py scenarios/ring` |
| 8 | Hareket Eğrileri | `motion.png` | `python _plot_motion.py` — her nokta `dynamics.achievable_accel`'den integre ediliyor, sabit yok |
| 9 | Kabuller | — | emniyet payları ve dt → `stats.py` + `ring/scenario-*.yaml` |
| 10 | Duraksız İşletme | `res-express.png` | `python presentation/ring/_sweep_express.py <sistem>` |
| 11 | Duraklamalı İşletme | `res-stopping.png` | `python presentation/ring/_sweep_headway.py <sistem>` |
| 12 | Bozucu Etki | `disruption2.png` | `python run.py presentation/ring/scenario-{78,71}-{dwell,both}.yaml --propagation --system <sistem>` |
| 13 | Konvoy Davranışı | `res-convoy.png` | aralıklar → `_sweep_convoy.py --headway [--stopping]`; kuplaj metrikleri → `run.py ... --log` + `convoy_stats.py` |
| 14 | Karşılaştırmalı Sonuçlar | `res-summary.png` | slayt 10 ve 11 ile aynı koşular |
| 15 | Ana Bulgular | — | slayt 10, 11, 12, 13 |
| 16 | Yedi Saniye | — | slayt 11 (7 s / %9) ve slayt 12 (%16 / %0.6) |
| 17 | Kaynaklar | — | — |

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

| | MB @78 | VC @78 | VC @71 | MB @71 |
|---|---|---|---|---|
| kapı arızası, yayılan | 982 s | 829 s | 976 s | 1000 s |
| iki olay birden, toplam | 1162 s | 1020 s | 1156 s | 1169 s |

**Neden iki okuma:** bir sistemi diğerinin tarifesinde koşturmak haksız
karşılaştırmadır, payı olan kazanır. Aynı tarifede (78 s) sanal kuplaj %16
kazanıyor; her sistem kendi sınırında koşturulduğunda fark %0.6'ya iniyor.

`-tsr.yaml` dosyaları hız kısıtlaması deneyidir ve `--headless` ile ölçülür
(`--propagation` değil: kısıtlama **hattın kendisine** uygulandığı için
üstünden geçen her tren doğrudan etkilenmiş sayılır, rapor tüm gecikmeyi
birincil gösterir). **Sunumda kullanılmadı** — iki tarife kısıtlamanın
saatine farklı sayıda tren sokuyor, karşılaştırma tarifeden kirleniyor.
Kayıt için: MB@78 455 s, VC@78 455 s, MB@71 417 s, VC@71 355 s.

### 7. `figures` — grafikler
```sh
python presentation/charts/network.py      # network.png
python presentation/charts/deckgfx.py      # flow.png papers.png systems.png
python presentation/charts/results.py      # res-express/stopping/summary.png
python presentation/charts/convoy2.py      # res-convoy.png
python presentation/charts/disruption2.py  # disruption2.png
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
| `scenario.yaml` + `timetable.yaml` | temel çevrim (5 dk aralık) |
| `scenario-express.yaml` + `timetable-express.yaml` | duraksız |
| `scenario-convoy*.yaml` + `timetable-convoy*.yaml` | konvoy kuralı (`uncoupled_speed_kmh: 70`, `coupling_margin_m: 800`) |
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
