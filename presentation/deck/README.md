# `deck/` — sunum dosyası ve onu kuran betikler

| dosya | ne |
|---|---|
| `ASELSAN-Sunum-v3.pptx` | teslim edilen sunum, 18 slayt |
| `kit.py` | `.pptx` düzenleme takımı — başlık/gövde yazma, resim ekleme ve değiştirme, konuşmacı notu, slayt kopyalama ve yeniden sıralama |
| `story3.py` | v3'ün içeriğini kuran betik: slayt sırası, her slaydın maddeleri, grafikleri ve notu |
| `dump.py` | bir `.pptx`'in bütün slayt metnini ve notlarını terminale döker — kontrol için |

## Bu klasör tek komutla sunumu yeniden kurmaz

`story3.py`, elle hazırlanmış ASELSAN şablonundan türeyen bir **ara sürümü**
(`ASELSAN-Sunum-v2.pptx`) girdi alır. O ara sürüm depoda tutulmuyor — iki
adet 5 MB'lık ikili dosya, üstelik yalnızca bu zincirin ortasında bir kez
kullanılıyor. Yani `story3.py` burada **sunumun nasıl düzenlendiğinin kaydı**
olarak duruyor, çalıştırılabilir bir yapı betiği olarak değil.

Sunumun içeriğini sıfırdan üretmek istersen doğru yol `SUNUM-PROMPT.md`:
bütün veriyi ve slayt slayt spesifikasyonu taşır, şablonla birlikte verilir.

Grafikler ise tamamen yeniden üretilebilir:

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
