# `deck/` — sunum dosyası ve onu kuran betikler

| dosya | ne |
|---|---|
| `ASELSAN-Sunum-v5.pptx` | teslim edilen sunum, 17 slayt — 11, 12 ve 14'te yüzdeler slayt metni olarak |
| `ASELSAN-Sunum-v4.pptx` | v3'ün elle düzenlenmiş hâli; sayfa numarası alan (`slidenum`), içerik listesi slayt başlıklarıyla aynı — v5'in girdisi |
| `ASELSAN-Sunum-v3.pptx` | `story3.py`'nin çıktısı, 21 slayt — v4'ün girdisi |
| `ASELSAN-Sunum-v2.pptx` | `story3.py`'nin girdisi — ara sürüm |
| `kit.py` | `.pptx` düzenleme takımı — başlık/gövde yazma, resim ekleme ve değiştirme, konuşmacı notu, slayt kopyalama ve yeniden sıralama |
| `story3.py` | v3'ün içeriğini kuran betik: slayt sırası, her slaydın maddeleri, grafikleri ve notu |
| `add_pcts.py` | v4 → v5: yüzdeleri metin kutusu olarak ekler; barların hizasını grafiğin PNG'sinden ve slayttaki kırpmadan hesaplar |
| `dump.py` | bir `.pptx`'in bütün slayt metnini ve notlarını terminale döker — kontrol için |

## Sunumu yeniden kurmak

```sh
python presentation/deck/story3.py
```

`story3.py`, elle hazırlanmış ASELSAN şablonundan türeyen ara sürümü
(`ASELSAN-Sunum-v2.pptx`) girdi alır, `presentation/figures/` altındaki
grafikleri yerleştirir ve `ASELSAN-Sunum-v3.pptx`'i yazar. Slayt sırası,
her slaydın maddeleri ve konuşmacı notları betiğin içinde.

Sunumun içeriğini **sıfırdan** üretmek istersen doğru yol `SUNUM-PROMPT.md`:
bütün veriyi ve slayt slayt spesifikasyonu taşır, şablonla birlikte verilir.

Grafikler ise ayrıca yeniden üretilebilir:

```sh
sh presentation/run_all.sh figures
```

`story3.py` grafikleri `presentation/figures/` altından okur, yani grafiği
değiştirip betiği yeniden koşmak yeterlidir (v2 elindeyse).

## `kit.py` neyi çözüyor

Bir `.pptx` düzenlerken üç yer insanı yanıltıyor; `kit.py` üçünü de tek yerde
hallediyor:

- **Slayt pozisyonu ≠ dosya adı.** `slide11.xml` sunumun 11. slaydı olmak
  zorunda değil. `kit.order()` sırayı `presentation.xml`'in `sldIdLst`'inden
  çözer; her fonksiyon pozisyonla çalışır.
- **Bir paragrafın run'ları birbirinin aynı olabilir.** Metni `str.replace`
  ile değiştirmek yanlış run'ı silip paragrafı boşaltıyor. `_retext` konum
  tabanlı çalışır.
- **Resim ilişkisi.** Bir slaytta birden fazla resim ilişkisi olabilir;
  `swap_pic` değiştirilecek `rId`'yi `rels` dosyasının ilk eşleşmesinden
  değil, `<p:pic>`'in kendi `<a:blip r:embed>`'inden okur.
