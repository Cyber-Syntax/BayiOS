# Teklif / Rezervasyon UX ve Manuel Toplam Planı

Durum: **Uygulandı (2026-11-22)** · Kapsam: teklif formu, teklif/rezervasyon listeleri, CSV/Excel/JSON dışa aktarma.

## 1. Teklifte nakit/kart toplamı manuel değiştirilebilir

**Amaç:** Çok ürünlü tekliflerde satır fiyatlarıyla tek tek uğraşmadan paket nakit/kart toplamı girilebilsin.

**Önerilen davranış**

- `offers.cash_total_override` ve `offers.card_total_override` nullable `MONEY` alanları eklenecek (migration `0020`).
- Formda iki opsiyonel alan: **Nakit Toplam (manuel)** ve **Kart Toplam (manuel)**. Boş = otomatik hesap.
- Girilen değer 2 haneye yuvarlanır ve negatif olamaz. Seçili ödeme türünün toplamı (`selected_total`) override'dan gelir.
- Manuel toplam, mevcut satır satış toplamlarına göre orantılı olarak satır `unit_price_cash` / `unit_price_card` değerlerine **dağıtılır**; böylece satır toplamları manuel toplamı verir.
- Kuruş yuvarlama artığı kalırsa (özellikle adet > 1) kâr özetinde **"Manuel toplam farkı"** olarak gösterilir; toplam gelir/kâr/marj nihai toplama göre hesaplanır.
- Kart komisyonu ve taksit limiti kontrolü, manuel kart toplamı üzerinden yapılır.
- Maliyetin altında toplam girilirse kayıt engellenmez; kırmızı uyarı gösterilir.
- Düzenlemede alanlar mevcut override değerleriyle dolar; boşaltılırsa otomatik hesaba döner.

**Dokunulacak yerler**

- `src/bayios/adapters/db/models/offers.py`: yeni alanlar ve check constraint.
- `alembic/versions/0020_offer_manual_totals.py`.
- `src/bayios/application/offers/__init__.py`: `OfferInput`, `_totals`, create/update, `preview_offer_comparison`, `build_offer_profit_summary`.
- `src/bayios/web/pages/offers.py`: form parse/render, compare endpoint.
- `src/bayios/web/templates/offers/form.html`, `_basket_totals.html`, `_comparison.html`, `detail.html`.
- `src/bayios/application/offers/io.py`: export/import alanları.
- Testler: create/update override, boş/tek/iki toplam, negatif/yanlış değer, komisyon ve kâr düzeltmesi.

**Karar:** Fark satırlara orantılı dağıtılır; böylece kullanıcı 61 kart / 59 nakit gibi paket toplam girdiğinde satır satış fiyatları da otomatik bölünür. Yalnızca kuruş yuvarlama artığı manuel fark olarak kalabilir.

## 2. Teklif ve rezervasyon listelerinde tek "Ürünler" sütunu

**Amaç:** Genel listede her kaydın ürünlerini tek bakışta görmek.

**Web listesi**

- Teklifler listesine **Ürünler** sütunu: `Ürün A ×2 · Ürün B ×1` (kampanya varsa kısa etiket).
- Rezervasyonlar listesine **Ürünler** sütunu: `A 600 B (teslim edildi) · A 710 I · 570471 MB (iptal)`.
- Durum metinleri: teslim edildi / iptal / kısmi (X teslim, Y iptal) / açık.
- Uzun listelerde hücre satır kırar; tam metin `title` ile de görünür.

**CSV/Excel**

- Teklifler ana sayfasına **son sütun** olarak `Ürünler` eklenir.
- Rezervasyonlar ana sayfasına **son sütun** olarak `Ürünler` eklenir.
- Satır düzeyi sayfalar (`Teklif Satırları`, `Rezervasyon Satırları`) mevcut ayrıntıyı korur.

**JSON (uygulandı)**

- `/offers/export/json` ve `/reservations/export/json` eklendi.
- Şema `schema_version: "1.0"`; her kayıtta `items[]`:
  - teklif: `product_id`, `product_name`, `quantity`, `campaign_name`
  - rezervasyon: `product_id`, `product_name`, `quantity`, `delivered_quantity`, `cancelled_quantity`, `open_quantity`, `status`
- CSV/Excel için düz `Ürünler` metni, JSON için yapısal `items` birlikte tutulur.

**Dokunulacak yerler**

- `application/offers`: liste için `OfferListItem`/items özeti; repository'de toplu item sorgusu.
- `application/reservations`: `ReservationListItem.products`/`products_summary`.
- `web/templates/offers/_results.html`, `reservations/_results.html`.
- `application/offers/io.py`, `application/reservations/io.py`; gerekirse yeni `json_io` modülleri.
- Testler: ürün özeti, durum etiketleri, CSV/Excel son sütunu, JSON items.

## 3. Teklif oluştur/vazgeç butonları sticky alt bar

- Formun altındaki buton grubu `.sticky-action-bar no-print` ile ekranın altına sabitlenir.
- Bar içinde **Vazgeç** ve **Teklif Oluştur / Kaydet**; sağda seçili toplam özeti.
- İçerik altında `.sticky-action-spacer` ile butonların kapatmaması sağlanır.
- Mobilde butonlar tek satırda, yatay taşma yok.
- Form submit sırasında buton disabled + "Kaydediliyor…" durumu.

## 4. Taksit seçenekleri açılır/kapanır

- "Taksit Seçenekleri" kartı `<details>` ile sarılır.
- Özet: **Taksit Seçenekleri** + yüklendiğinde seçenek sayısı.
- Varsayılan kapalı; kullanıcı açtığında tablo görünür.
- Karşılaştırma isteği panel kapalıyken de arka planda yüklenir; açınca hazır olur.
- Hata/boş durum mesajları panel içinde kalır.

## 5. Ürün eklenince taksit seçenekleri otomatik yenilenir

**Mevcut sorun:** `addProduct()` Alpine modelini güncelledikten hemen sonra `offer-changed` gönderiyor; HTMX formu gönderirken yeni ürünün hidden inputları henüz DOM'a yansımamış oluyor. Bu yüzden seçenekler ancak başka bir input değişince güncelleniyor.

**Çözüm**

- `addProduct()` ve `remove()` içinde `this.$nextTick(() => this.notifyChange())` kullanılacak; isteğe bağlı kısa debounce.
- `hx-trigger` korunur: `offer-changed from:body`, `change/input from:#offer-form`.
- Ürün ekleme, çıkarma, miktar, kampanya ve manuel toplam değişimlerinde tek bir tutarlı yenileme.
- Gerekirse `offer-comparison` isteğine `hx-sync` ile eşzamanlı istekleri birleştirme eklenir.

## 6. Senaryo özeti sepetin hemen üzerinde

- Senaryo özeti ayrı bir `#offer-scenario-summary` kartına taşınır; **Sepet** kartının hemen üstünde durur.
- `_comparison.html` ana hedef olarak yalnızca taksit tablosunu döndürür; senaryo özeti ve sepet toplamları `hx-swap-oob` ile güncellenir.
- Yeni form sırası:
  1. Müşteri + ödeme/indirim
  2. **Senaryo Özeti**
  3. **Sepet** (satırlar + toplamlar)
  4. Taksit Seçenekleri (kapalı panel)
  5. Ürün Ekle
  6. Sticky alt bar
- Özet ilk yüklemede "Senaryolar hesaplanıyor…" gösterir; comparison yanıtı gelince dolar.

## Uygulama sırası

1. Migration `0020` + model/domain override alanları.
2. Teklif create/update/compare/kâr özeti override desteği.
3. Form: manuel toplam alanları, sticky bar, `<details>`, senaryo özeti taşıma.
4. Alpine `$nextTick` düzeltmesi.
5. Liste/export "Ürünler" sütunu; JSON export (opsiyonel faz).
6. Testler + `ruff check` + tam `pytest`.

## Kabul kriterleri

- Tek ürün veya 10 ürünlü teklifte manuel nakit/kart toplamı girilebilir; kaydedilir ve tekrar açıldığında korunur.
- Manuel toplam satır fiyatlarına dağıtılır; kâr/marj ve komisyon hesabına yansır.
- Ürün eklenince taksit seçenekleri ekstra input değişikliği gerekmeden güncellenir.
- Senaryo özeti sepetin hemen üstünde; taksit seçenekleri açılır/kapanır.
- Teklif/rezervasyon listelerinde ve CSV/Excel'de `Ürünler` sütunu vardır; rezervasyonda teslim/iptal durumu görünür.
- Teklif oluştur/vazgeç butonları sticky alt bardadır.


## Uygulama notu

- Manuel nakit/kart toplamı `0020_offer_manual_totals` migration'ı ile eklendi.
- Teklif ve rezervasyon JSON içe/dışa aktarma uygulandı; CSV/Excel desteği korunuyor.
- `Ürünler` sütunu CSV/Excel'de **export-only** ve import'ta opsiyonel/okunmaz; ürün satırları hâlâ `Teklif Satırları` / `Rezervasyon Satırları` sayfalarından okunur.
- JSON teklif export/import tam current-state taşır; rezervasyon JSON import'u mevcut durumu (teslim/iptal adetleri ve satır durumu) stok hareketi oluşturmadan aktarır.
