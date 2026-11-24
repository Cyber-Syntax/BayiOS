# BayiOS UI/UX Yenileme Planı

**Durum:** Faz 1–2 tamam; Faz 3 büyük ölçüde tamam, kalanlar §8'de  
**Tarih:** 23.11.2026  
**İlgili belgeler:** [ui.md](./ui.md) tek UI/UX sözleşmesi, [prd.md](./prd.md) işlevsel ürün gereksinimleri, [plan.md](./plan.md) mimari ve milestone sözleşmesi.

## 1. Amaç

BayiOS'un mevcut işlevsel ekranlarını, Python tarafında yeni bir iş özelliği eklemeden, profesyonel ve telefon/laptop için üretken bir arayüze taşımak. Hedef:

- Telefonda hızlı bakma: ürün bul, fiyat/stok oku, teklif için fiyat ver.
- Laptopta yönetme: kampanya, komisyon, içe/dışa aktarma, toplu işlem, A4 çıktı.
- Tek tasarım dili, tek bileşen sözlüğü ve tek UI sözleşmesi.
- Mevcut URL'ler, form alanları, HTMX parçaları ve iş kuralları korunur.

Kapsam dışı: WhatsApp paylaşımı, barkod/kamera, hızlı teslim, kimlik doğrulama/rol, yeni domain davranışı, veritabanı şeması değişikliği. Bunların görselde sahte butonu da yer almaz.

## 2. Alınan kararlar

### D1 — Görsel yön

- Sıcak taş/nötr zemin (#f7f7f4, #fcfcfb, #ffffff) + lacivert/indigo birincil vurgu (#1f2a5a ailesi).
- v2'nin sakin, satışa indirgenmemiş havası korunur; v4'ün mavi aksiyon dili lacivert/indigo'ya çekilir.
- Durum renkleri: başarı zümrüt, uyarı amber, tehlike gül, bilgi mavi. Renk tek başına anlam taşımaz; her durum metinle birlikte gösterilir.
- İlk fazda yalnız açık tema. Koyu tema ayrı bir fazdır; yarım dark mode gönderilmez.

### D2 — Tipografi ve ikonlar

- Inter (latin + latin-ext) ve JetBrains Mono (latin + latin-ext) self-host edilir; CDN yoktur.
- Fontlar web/static/vendor/fonts/ altında, OFL lisanslarıyla ve VERSIONS.txt SHA-256 özetleriyle tutulur.
- İkonlar tek bir inline SVG sprite'tan gelir (base.html içinde symbol tanımları). Tabler benzeri 1.8px çizgi ikon dili; ikon tek başına anlam taşımaz, yanında etiket vardır. İkon fontu kullanılmaz.

### D3 — Navigasyon ve kırılımlar

| Genişlik | Navigasyon | İçerik |
| --- | --- | --- |
| < 1024px | Alt sekme çubuğu (5 öğe + "Daha fazla" sayfası) | Tek sütun, kart görünümü, 16px kenar boşluğu |
| 1024–1279px | Sol menü, yalnız ikon (72px) | Tablo, 24px kenar boşluğu |
| ≥ 1280px | Sol menü, ikon + etiket (248px) | Tablo, 32px kenar boşluğu, iki sütunlu yerleşim |

- Telefon alt sekmeleri: Ana Sayfa, Ürünler, Teklifler, Rezervasyonlar, Daha fazla.
- "Daha fazla" alt sayfası: Kampanyalar, Stok/Sayım, Komisyonlar, Ayarlar.
- Odaklı ekranlarda (teklif formu, sayım oturumu) alt sekme gizlenir; yerine sticky eylem çubuğu gelir.
- Topbar ve arama her ekranda sticky kalır.

### D4 — Liste düzeni

- Laptopta yoğun, taranabilir tablo; telefonda kart.
- Ürünler, teklifler, rezervasyonlar ve kampanyalar bu kurala uyar. Kart görünümü aynı bilgi mimarisini korur; yatay kaydırma gerektirmez.
- Tablolarda işlem kolonu sağa sabitlenir; geniş tablolar data-table-scroll ile her zaman görünür yatay scrollbar alır.

### D5 — Ürün detayı

- Fiyat-öncelikli hero: Oliz fiyatı en büyük metin, normal fiyat üstü çizili, bayi nakit/kart taban fiyatları, stok ve açık rezervasyon rozetleri.
- v2'deki kapalı akordeonlar: ürün özellikleri, teknik özellikler, fiyat geçmişi, stok hareketleri, iç bilgiler (maliyet/scraper).
- "Teklife Ekle" /offers/new?product_id=<id> deep-link'i ile çalışır; küçük, iş kuralı içermeyen bir read-only ön-doldurma eklenir.
- "Rezervasyon Aç" mevcut /reservations/new?product_id= akışını kullanır.

### D6 — Komisyon limitleri

- Kategori bazlı yasal/limit satırları korunur (bankadan bağımsız).
- Ek olarak kanal + banka (+ kart tipi) bazlı max taksit tablosu gösterilir. Örnek: Ödero / Garanti / 9.
- Banka özel limit, aynı kapsamdaki bankasız genel limiti geçersiz kılar; kategori sınırı bankadan bağımsızdır ve yükseltilemez. Bu davranış domain'de zaten vardır; UI yalnızca görünür ve düzenlenebilir hale getirir.

### D7 — Ayarlar

- Mevcut Bankalar ve Kategoriler yönetimi v2'nin kart, toggle, empty-state ve toplu ekleme diliyle yenilenir.
- Backend'i olmayan bayi profili, maliyet görünürlüğü veya bildirim toggle'ları eklenmez.

### D8 — A4 çıktıları

- Faz 1–3'te A4 şablonlarına dokunulmaz; yalnız ekran UI'ı yenilenir.
- Faz 4'te print.css ve A4 şablonları yeni tipografi/renk diliyle uyumlu hale getirilir; içerik ve sayfa kırılımı değişmez.

### D9 — Backend sınırı

- Yeni iş kuralı, yeni domain davranışı veya DB şeması yok.
- Yalnızca görseli besleyen read-only sorgular ve deep-link parametreleri eklenebilir: ana sayfa KPI sayıları, son teklif/rezervasyon listeleri, /offers/new?product_id=.
- Tüm yeni sorgular mevcut repository portlarını kullanır; route içinde iş kuralı yazılmaz.

### D10 — Ürün seçimi

- Mockup'lardaki bağımsız ürün listesi kullanılmaz. Teklif, rezervasyon ve kampanyada ortak desen: arama kutusu → sonuç → "Ekle" → satır.
- Seçilen ürün satırı; miktar, kampanya, hediye ve fiyat alanlarıyla birlikte düzenlenir. Aynı ürün ikinci kez eklenmez.

## 3. Tasarım sistemi özeti

- **Renk:** --bg, --surface, --surface-2, --ink, --muted, --border, --accent, --accent-soft, --success, --warning, --danger, --info.
- **Tipografi:** Inter; başlık 24/20/16px, gövde 14px, yardımcı 12px, mikro 11px. Fiyat/ID için JetBrains Mono ve font-variant-numeric: tabular-nums.
- **Boşluk:** 4px tabanlı ölçek (4, 8, 12, 16, 20, 24, 32, 40).
- **Yarıçap:** kontrol 10px, kart 14–16px, rozet 999px, modal 18px (telefonda üst köşe 20px).
- **Gölge:** kartlarda 0 1px 2px rgba(20,20,19,.04); modal 0 20px 50px rgba(20,20,19,.18).
- **Buton:** 40px laptop, 44px telefon; tek birincil buton; tehlike eylemleri "Diğer işlemler" altında.
- **Form:** görünür etiket, 40–44px kontrol, hata metni alanın altında, odak halkası 2px accent.
- **Tablo:** 13px, kompakt satır, sticky başlık, sağa sabit işlem kolonu, satır hover'ı.
- **Modal:** laptopta ortada, telefonda alttan açılan panel; max-height 90dvh, dikey kaydırma.
- **Durum:** rozet + metin; boş durumda ikon + açıklama + eylem.
- **Hareket:** 150–200ms; prefers-reduced-motion desteklenir. Hover'a bağlı bilgi/eylem yoktur.

## 4. Fazlar

### Faz 0 — Sözleşme ve temel

- [x] docs/ui.md tamamen yeniden yazılır; yalnız UI/UX.
- [x] docs/prd.md içindeki UI/UX ayrıntıları ui.md'ye referanslanır; işlevsel gereksinimler korunur.
- [x] docs/ui-redesign-plan.md bu dosya.
- [x] Fontlar vendorlanır, VERSIONS.txt güncellenir.
- [x] app.css tasarım sistemi ve kabuk bileşenleri yeniden yazılır.
- [x] base.html sprite, topbar, sidebar/rail, alt sekme ve "Daha fazla" katmanıyla yenilenir.

**Kabul:** Tüm mevcut sayfalar yeni kabukta açılır; 320px'den 1440px'e yatay kaydırma yok; alt sekme <1024, rail 1024–1279, tam sidebar ≥1280.

### Faz 1 — Ana Sayfa + Ürünler + Ürün Detayı

- [x] Ana Sayfa: karşılama, 4 KPI, hızlı işlemler, hatırlatmalar, son teklifler/rezervasyonlar, modül kartları.
- [x] Ürünler: sayfa başlığı, arama/filtre çubuğu, masaüstü tablo, mobil kart, toplu işlem çubuğu, modallar.
- [x] Ürün detayı: fiyat-öncelikli hero, birincil eylemler, aktif kampanyalar, kapalı akordeonlar, modallar.
- [x] /offers/new?product_id= ön-doldurma.
- [x] Ana Sayfa KPI'ları için read-only sayımlar; mevcut portlar kullanılır.

**Kabul:** Ürün arama, filtre, sayfalama, satır seçimi, toplu kategori/arşiv/silme, stok güncelleme, detay düzenleme ve iki aşamalı silme aynı işlevle çalışır; mobilde kart, laptopta tablo; tüm fiyatlar tek satırda.

### Faz 2 — Teklifler + Rezervasyonlar

- [x] Teklif listesi: masaüstü tablo, mobil kart, durum filtreleri, arama, sayfalama.
- [x] Teklif formu: iki sütun (müşteri/ödeme solda, sepet/toplamlar sağda), senaryo özeti, taksit paneli, satır ekleme, sticky eylem çubuğu.
- [x] Teklif detayı: özet, kâr/komisyon kartı, durum geçmişi, A4, rezervasyon/teslim eylemleri.
- [x] Rezervasyon listesi: masaüstü tablo, mobil kart, hatırlatma vurgusu.
- [x] Rezervasyon detayı: dikey ürün satırı kartları, teslim/iptal, miktar, hareket geçmişi.
- [x] Yeni rezervasyon: ürün arama + satır ekleme.

**Kabul:** Mevcut teklif/rezervasyon akışları, HTMX otomatik hesaplama ve A4 çıktıları bozulmaz; telefonda yatay kaydırma yok; odaklı ekranlarda alt sekme gizlenir.

### Faz 3 — Komisyonlar + Kampanyalar + Stok + Ayarlar

- [x] Komisyon listesi: dönem kartları/tablosu, aktif dönem vurgusu, içe/dışa aktarma.
- [x] Komisyon detayı: kanal sekmeleri, oran matrisi, kategori limitleri ve banka bazlı limit tablosu.
- [x] Kampanyalar: liste, detay, form, sürüm geçmişi, içe/dışa aktarma.
- [x] Stok/Sayım: açık oturumlar ve geçmiş için iki iç sekme; kategori filtresi; sayım girişi; sticky "Miktarları Kaydet".
- [~] Ayarlar: sekmeler, toplu ekleme önizlemesi ve mobil notlar tamam; birleştirme/silme modalları hâlâ tarayıcı confirm kullanıyor.
- [x] İçe/dışa aktarma önizlemeleri: mobilde "laptopta daha rahat" notu, yatay kaydırmalı tablo.

**Kabul:** Tüm yönetim ekranları laptopta yoğun, telefonda okunabilir; komisyon banka limitleri düzenlenebilir; Excel/JSON akışları çalışır.

### Faz 4 — Cila ve A4

- [x] print.css yeni tipografi/renk diliyle uyumlu; A4 içerikleri değişmedi.
- [~] Erişilebilirlik: aria-current, aria-expanded, kontrast ve dokunma hedefleri tamam; modal odak tuzağı kaldı.
- [ ] Boş/hata/başarı durumları tüm ekranlarda tutarlı.
- [~] 320/390/768/1024/1280/1440px görsel kontrol yapıldı; reduced-motion var; klavye modal odak dönüşü kaldı.
- [x] Tam test ve lint.

## 5. Dosya haritası

- src/bayios/web/static/css/app.css — tasarım sistemi, kabuk, bileşenler, ekran stilleri.
- src/bayios/web/static/css/print.css — A4 (Faz 4).
- src/bayios/web/templates/base.html — sprite, topbar, navigasyon, alt sekme, flash.
- src/bayios/web/templates/home.html — Ana Sayfa.
- src/bayios/web/templates/products/list.html, _table.html, detail.html — Ürünler.
- src/bayios/web/templates/offers/*, reservations/*, commissions/*, campaigns/*, stock/*, settings/* — Faz 2–3.
- src/bayios/web/pages/home.py — read-only KPI context.
- src/bayios/web/pages/offers.py — product_id deep-link.
- src/bayios/web/navigation.py — ikon adları, alt sekme grupları.
- tests/web/* — sözleşme testleri; sınıf adları korunur veya bilinçli güncellenir.

## 6. Test ve kabul

Her faz sonunda:

    uv run ruff check src tests
    uv run pytest -q

Ek kontroller:

- uv run pytest tests/web -q — HTML sözleşmeleri.
- uv run pytest tests/domain tests/application -q — iş kuralları değişmedi.
- Manuel: 390px ve 1440px'de Ana Sayfa, Ürünler, Ürün Detayı; klavye ile modal; yazdırma önizlemesi.
- Regresyon: /products arama/filtre/sayfalama, toplu seçim, stok güncelleme, iki aşamalı silme; /offers/new?product_id= ön-doldurma.

## 7. Riskler ve geri dönüş

- **HTMX parça sözleşmeleri:** _table.html, _picker.html gibi parçaların id/hedef yapısı korunur; sınıf değişiklikleri testlerle doğrulanır.
- **Alpine durumu:** Seçim, modal ve sepet durumu yeniden yazılırken mevcut metot adları korunur.
- **Aşırı yeniden yazım:** İşlevsel route/form alanları değiştirilmez; yalnız markup ve CSS yenilenir.
- **Font lisansı:** OFL dosyaları vendor klasöründe; VERSIONS.txt hash'leri güncel.
- **Geri dönüş:** Her faz ayrı commit; sorun halinde faz geri alınabilir, domain/application katmanı etkilenmez.
## 8. Kalan işler (sonraki tur)

- [ ] Teklif detayında maliyet/kâr bilgisini telefonda kapalı "İç bilgiler" bölümüne almak.
- [ ] Ayarlar birleştirme/silme eylemlerini tarayıcı confirm yerine iki aşamalı modal'a taşımak.
- [ ] Modal odak tuzağı, kapanışta odağı tetikleyiciye döndürme ve son klavye turu.
- [ ] A4 şablonlarında içerik/yerleşim ince ayarı (içerik değişmeden).
