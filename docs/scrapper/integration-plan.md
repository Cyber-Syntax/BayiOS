# Bayios — Scraper Entegrasyon Planı

Durum: Uygulandı (2026-11-22) · Kaynak brief: [scrapper.md](scrapper.md) · GitHub release JSON butonu sonraki session
Hedef: Scraper çıktısındaki ürün ID'si, fiyatları ve JSON detaylarını Bayios'a aktarmak; Excel/CSV ve `catalog.json` aynı ürün modeline düşsün.

## 1. Kapsam ve sınır

- Bayios içinde scraping yapılmaz; yalnızca scraper'ın ürettiği dosyalar içe aktarılır.
- Faz 1: Excel/CSV (9, 10, 11 ve 12 sütunlu dosyalar).
- Faz 2: `catalog.json` (schema_version `1.0`).
- Medya/görsel/video indirilmez; yalnızca metin detayları saklanır.
- Mevcut ürünler silinmez, arşivlenmez; katalogda olmayan ürünler delist edilmez.
- Ürün kimliği: iç UUID korunur; scraper ID'si ayrı `external_id` alanında tutulur.

## 2. Veri modeli ve migration (`0018_scraper_product_details`)

`products` tablosuna eklenecek alanlar:

| Alan | Tip | Kural |
|---|---|---|
| `external_id` | text, nullable, unique | Scraper ID'si; baştaki sıfırlar korunur; boş string `NULL`'a çevrilir |
| `details` | JSONB, nullable | `{"features": [...], "specifications": [...]}` |
| `source_url` | text, nullable | Yalnızca catalog.json'dan gelir; ürün detayında link |
| `kind` | text, not null, default `product` | `product`, `warranty`, `explicit` |
| `scraped_at` | timestamptz, nullable | Scraper'ın üretim zamanı; `last_seen_at`'ten ayrı |

Yeni tablo `product_external_id_history`:

| Alan | Tip | Kural |
|---|---|---|
| `id` | uuid | PK |
| `product_id` | uuid FK | `products.id`, CASCADE |
| `external_id` | text, unique | Eski scraper ID'si |
| `created_at` | timestamptz | Alias'ın yazıldığı an |

Diğer değişiklikler:

- `products.name_normalized` üzerindeki UNIQUE kısıt kaldırılır; yerine normal index gelir.
- `products.external_id` için unique index/constraint; boş string kabul edilmez.
- `product_import_batches.file_type` check'i `csv`, `xlsx`, `json` olacak şekilde genişletilir.
- `product_price_history.source` check'ine `scraper_import` eklenir.
- Mevcut ürünler: `external_id=NULL`, `details=NULL`, `kind='product'`; eski ID geçmişi boş başlar.
- Migration downgrade yalnızca veri çakışması yoksa çalışır; duplicate isim varsa unique kısıt geri eklenemez (forward-only notu).

Model/repository etkileri:

- `Product` modeline yeni alanlar; `name_normalized` unique yerine index.
- Repository'ye `get_by_external_id`, `get_by_external_ids`, `get_by_external_id_including_history`, `find_by_normalized_names` (ad -> ürün listesi) eklenir.
- `get_by_normalized_name` legacy tek kayıt döndürmeye devam eder; yeni importlar ve diğer adla eşleşen importlar `find_by_normalized_names` ile çoklu eşleşmeyi açıkça raporlar.
- Arama (`search`) ürün adı veya `external_id` ile eşleşir.

## 3. Kimlik ve eşleştirme kuralları

Ürün ID'si zamanla değişebilir: aynı ürün yeni seriyle üretildiğinde scraper yeni ID getirir. Bu nedenle güncel ID ile eski ID'leri ayırıyoruz.

- `products.external_id`: ürünün **güncel** scraper ID'si.
- `product_external_id_history`: eski ID'ler; `product_id` + `external_id` (unique). Eski teklif/rezervasyon dosyaları bu alias'larla doğru ürüne bağlanır.

Eşleştirme önceliği:

1. `external_id` güncel ID ile eşleşiyorsa o ürün.
2. Değilse `product_external_id_history` alias'ı ile eşleşiyorsa o ürün.
3. ID boşsa normalize ürün adıyla legacy eşleştirme.
4. ID dolu ama ne güncel ne alias olarak bulunamazsa satır hatası; ada göre ikinci deneme yapılmaz (yanlış ürüne bağlanmayı önler).
5. ID boş + ad tek eşleşme -> o ürün; ad çoklu eşleşme -> belirsizlik hatası.
6. Ürün kataloğu importunda (kimlik kaynağı) yeni ID, mevcut ürünle ad üzerinden tek eşleşiyorsa ürünün `external_id` değeri **doğrudan güncellenir**; eski güncel ID alias tablosuna yazılır.
7. Yeni ID başka bir ürüne aitse birleştirme yapılmaz; çakışma hatası verilir (yanlış ürünün ID'sini ezmemek için).
8. Katalog satırında ID boşsa mevcut `external_id` korunur; ada göre eşleşme yoksa ID'siz yeni ürün açılır (garanti satırları).
9. Teklif/rezervasyon/kampanya importları ID'yi yalnızca **çözer**; ürünün güncel `external_id` değerini değiştirmez. Güncel ID katalog importundan gelir.
10. Aynı ID dosyada birden fazla kez gelirse ilk kayıt işlenir; sonrakiler `skip` + çakışma uyarısı olur.
11. Aynı ad farklı ID gerçekten farklı ürünse manuel ayrım gerekir; katalog importu tek ad eşleşmesini ID güncellemesi sayar. Ad çoklu eşleşiyorsa ID ile karar verilir.

Eski rezervasyon/teklif satırları ürün UUID'sine bağlıdır; ürünün `external_id` değeri güncellenince ekranda/çıktıda **yeni ID** görünür. Ayrı ID snapshot'ı tutulmaz; servis kaydı güncel ID'yi kullanır.

## 3.1. Tüm ürün referanslı importlarda ID kolonu
## 3.1. Tüm ürün referanslı importlarda ID kolonu

Ürün ID'si yalnızca ürün kataloğunda değil; ürünü satır bazında referans eden tüm Excel/CSV importlarında opsiyonel `Ürün ID` kolonu olarak eklenir:

- Teklif Satırları (`offer_items`): teklif başlığı altındaki ürün satırları.
- Rezervasyon Satırları (`reservation_items`): rezervasyon başlığı altındaki ürün satırları.
- Kampanya Ürünleri: kampanya-ürün ilişki satırları.
- Ürün kataloğu: `Ürün ID` zaten ana kolon.

Kurallar:

- Önce `external_id` ile eşleştirilir; ID varsa ad hiç kullanılmaz.
- ID boşsa normalize ürün adıyla legacy eşleştirme yapılır.
- ID dolu ama ürün bulunamazsa satır hatası verilir; ada göre ikinci deneme **yapılmaz** (yanlış ürüne bağlanmayı önlemek için). Bu kural teklif/rezervasyon/kampanya importları için geçerlidir; ürün kataloğu importunda ID yoksa ada göre bağlama/oluşturma kuralı 3. bölümdedir.
- ID boş ve aynı ad birden fazla ürüne denk geliyorsa belirsizlik hatası verilir; kullanıcıdan ID girmesi istenir.
- Eski ID'siz dosyalar çalışmaya devam eder; ID kolonu yoksa tamamen ada göre legacy akış kullanılır.
- Dışa aktarılan teklif, rezervasyon ve kampanya ürün sayfalarına `Ürün ID` kolonu eklenir; içe aktarma bu kolonu opsiyonel kabul eder.
- Bu sayede teklifte ürün ID'si doğrudan ürünün Oliz fiyatı, maliyeti ve kampanyasıyla eşleşir; Türkçe karakterli/special karakterli adlar eşleştirmeyi etkilemez.
- Hata mesajları satır no + ürün ID + ürün adı ile raporlanır.

## 4. Excel/CSV kuralları

Başlıklar pozisyona göre değil, ada göre eşlenir. Desteklenen dosyalar:

- 9 sütun: ID ve JSON yok; adla eşleş, detayları ve ID'yi değiştirme.
- 10 sütun: ID var, JSON yok; ID ile eşleş, detayları değiştirme.
- 11 sütun: ID + JSON; tam format.
- 12 sütun: ID + JSON + `scraped_at`; opsiyonel.

Genel kurallar:

- Fazla sütunlar yok sayılır; eksik opsiyonel sütunlar boş kabul edilir.
- İlk satırda tanınan başlık yoksa pozisyon tahmini yapılmaz; dosya hatası verilir.
- `Ürün Adı` zorunludur. `Ürün ID` boş olabilir (garanti).
- `kind` sütunu opsiyoneldir; yoksa `Kategori` normalize adı `ek garanti` ise `warranty`, aksi halde `product` kabul edilir.
- `source_url` ve `scraped_at` sütunları opsiyoneldir; yoksa mevcut değer korunur.
- `Fiziksel Stok`, `Alış Fiyatı`, `Kredi Kartı Taban`, `Nakit Taban`, `Aktif Kampanya` scraper'da boştur; mevcut değerleri ezmez.

Fiyat:

- `Perakende Fiyat` boş/0 ise mevcut fiyat korunur; yeni üründe `NULL`.
- `Oliz İndirimli Fiyat` boş/0 ise mevcut Oliz fiyatı **silinir** (kampanya bitti kabulü; önceki ürün import kuralıyla aynı).
- Tüm fiyatlar `Decimal`, iki ondalık; 0 gerçek fiyat olarak yazılmaz.

JSON detay hücresi (11. sütun):

- Boş hücre: mevcut detaylar korunur.
- Geçerli `{"features":[],"specifications":[]}`: detaylar temizlenir (boş listeler kaydedilir).
- Dolu geçerli JSON: `features` ve `specifications` replace edilir.
- Bozuk JSON: satır `details_error` ile işaretlenir; ürün adı/fiyat/kategori güncellenmeye devam eder, mevcut detaylar korunur. Bu satır commit'i durdurmaz.
- JSON nesnesinde eksik `features`/`specifications` anahtarı boş liste sayılır.
- `features`: `title`, `text`, `note`; `specifications`: `group`, `name`, `value`. Değerler string'e çevrilir; HTML yoktur, satır sonları korunur.

## 5. catalog.json kuralları

- Dosya `schema_version: "1.0"` taşımalı; desteklenmeyen sürüm dosya hatası verir.
- `products` listesi aynı `ProductImportRow` modeline dönüştürülür; böylece preview/commit Excel/CSV ile aynı akışı kullanır.
- `id` -> `external_id`; boş string `NULL`.
- `product_name`, `category`, `price`, `discounted_price`, `source_url`, `kind`, `scraped_at` alanları okunur.
- `currency` yalnızca `TRY` kabul edilir; farklı değer satır uyarısı/hatası olur.
- `price` `null`/0 ise mevcut fiyat korunur; `discounted_price` `null` ise mevcut Oliz silinir. (Onaylandı: mevcut örnekte 56 ürünün tamamı `discounted_price: null`; import bu ürünlerde Oliz varsa siler.)
- `features`/`specifications` her zaman replace edilir; boş listeler detayları temizler (catalog tam snapshot'tır).
- Aynı ID birden fazla kez gelirse ilk kayıt işlenir; sonrakiler `skip` + uyarı.
- Katalogda olmayan mevcut ürünler silinmez/arşivlenmez.
- Dosya düzeyi JSON/schema hatası tüm importu durdurur; satır düzeyi hata yalnızca o satırı etkiler.

## 6. Import akışı ve UI

- `/imports/products` ekranı `.csv`, `.xlsx` ve `.json` kabul eder; dosya tipi uzantı ve içerikten otomatik algılanır.
- Yükleme metni ve şablon indirme bağlantısı yeni formatı anlatır.
- Preview tablosuna eklenir:
  - Ürün ID (boşsa “—”),
  - Tür (product/warranty/explicit),
  - Detay özeti (“11 özellik / 42 teknik” veya “Bozuk JSON”),
  - Kaynak URL ikonu/linki (varsa).
- Kararlar: Yeni Ürün Aç, Güncelle, Atla; `clear_discount` yalnızca Oliz kolonu olmayan dosyalar için manuel opsiyon olarak kalır.
- ID'siz ada göre eşleşen satırda “ID bağlanacak” uyarısı gösterilir.
- Commit tek transaction; batch `file_type=json` dahil; idempotency `source_checksum`/token ile korunur.
- Ürün detay ekranına eklenir:
  - “Ürün ID” ve “Tür” bilgisi,
  - kaynak URL linki ve `scraped_at`,
  - “Öne Çıkan Özellikler” (features) ve gruplanmış “Teknik Özellikler” (specifications),
  - detay yoksa “Detay bilgisi yok”.
- Ürün listesinde adın altında küçük `ID: ...` gösterilir; arama ad veya ID ile çalışır.
- Teklif/rezervasyon ürün seçicileri aynı adı taşıyan ürünlerde ID/kategori ile ayrıştırma gösterir. Teklif, rezervasyon ve kampanya Excel importlarında `Ürün ID` kolonu vardır; ID güncel veya alias ise çözülür, ID yoksa adla legacy eşleşir, aynı ad birden fazlaysa ID istenir.
- Teklif ve rezervasyon detay/A4 çıktısında ürünün **güncel** `external_id` değeri gösterilir; eski rezervasyonlar ürün UUID'si üzerinden yeni ID'yi otomatik alır.

## 7. Testler

- 9/10/11/12 sütunlu CSV ve XLSX okunur; başlıksız dosya hata verir.
- 11. sütun JSON'u doğru parse edilir; bozuk JSON satırında ürün alanları güncellenir, detay korunur ve hata raporlanır.
- Boş JSON hücresi detayı korur; boş listeler detayı temizler.
- ID ile upsert: aynı ID günceller, yeni ID ekler.
- ID'siz ada göre eşleşme ID'yi bağlar; yeni ID uydurmaz.
- Aynı ürün yeni ID ile gelirse `external_id` güncellenir, eski ID alias olarak saklanır; eski teklif/rezervasyon dosyası alias ile doğru ürüne bağlanır.
- ID'siz garanti satırı ada göre eşleşir; eşleşmezse yeni ürün açılır.
- Aynı ID dosyada tekrar ederse ilk kayıt işlenir, sonraki atlanır.
- Teklif/rezervasyon/kampanya importlarında ID ile eşleşme, ID yoksa adla legacy eşleşme ve ID bulunamazsa hata.
- Aynı ad birden fazla üründe ID yoksa belirsizlik hatası; ID varsa doğru ürün seçilir.
- `catalog.json` ile aynı verinin Excel/CSV importu aynı sonucu verir.
- `price`/`discounted_price` null ve 0 davranışı; Oliz'in silinmesi.
- `kind`, `source_url`, `scraped_at` doğru saklanır/gösterilir.
- Migration: unique name kalkar, `external_id` unique çalışır, `file_type=json` kabul edilir.
- Web: .json yükleme -> preview -> commit; ürün detayında özellikler/teknik özellikler görünür.
- Tam `pytest` ve `ruff check` temiz.

## 8. Uygulama sırası

1. Model + `0018` migration + `product_external_id_history` + repository metotları.
2. `ProductDetails` domain modeli/validator ve JSON parse.
3. `ProductImportRow` genişletme; Excel/CSV 9/10/11/12 parse.
4. Kimlik indeksi, ID güncelleme + alias yazımı, upsert/eşleştirme kuralları; commit.
5. `catalog.json` parser'ı ve aynı preview/commit akışına bağlama.
6. Web import ekranı (.json, preview kolonları, kararlar).
7. Teklif/rezervasyon/kampanya importlarına `Ürün ID` kolonu ve ID-öncelikli eşleştirme; export şablonları.
8. Ürün detay/liste UI ve arama; diğer importlarda çoklu ad eşleşmesini çakışma hatasına çevirme.
9. Dokümanlar (`plan.md`, `prd.md`, `DATA_IMPORT.md`, `ui.md`, `GLOSSARY.md`, `AGENTS.md`) ve testler.

## 9. Varsayımlar / sonraki faz

- `external_id` alan adı kullanılacak; ayrı `product_code` yok.
- Aynı ürünün yeni ID'si katalog importunda doğrudan `external_id` güncellemesi yapar; eski ID alias olarak saklanır. Gerçekten farklı ürünler aynı adı taşıyorsa manuel ayrım/ID gerekir.
- Teklif/rezervasyon/kampanya importları ürün ID'sini yalnızca çözer; güncel ID'yi değiştirmez.
- Teklif/rezervasyon/kampanya Excel importlarında `Ürün ID` kolonu bu fazda eklenir; ID yoksa adla legacy eşleşme yapılır, ID dolu ama bulunamazsa hata verilir, duplicate adlarda ID istenir.
- Detaylar için ayrı tarihçe tutulmaz; `scraped_at` ve `updated_at` yeterlidir.
- `catalog.json` dışında `source_url`, `kind`, `scraped_at` sağlanmazsa mevcut değerler korunur.
- `catalog.json` `discounted_price: null` mevcut Oliz fiyatını siler (onaylandı); bu, scraper Oliz yakalamadığında veri kaybı riski taşır.
- Medya/görsel/video ve delist kapsam dışıdır.

## 10. Sonraki session — GitHub release JSON butonu

- Ayrı bir iş: scraper reposunun latest GitHub release asset'inden `catalog.json` indirilip aynı preview/commit akışına verilecek.
- Bayios içinde scraping yapılmaz; yalnızca yayınlanmış JSON asset'i indirilir.
- Ağ erişimi, asset adı, sürüm doğrulama ve hata mesajları bu işte ele alınacak; mevcut `catalog.json` importu değişmeden kullanılacak.

## 10. Sonraki session — GitHub release JSON butonu

- Ayrı bir iş: scraper reposunun latest GitHub release asset'inden `catalog.json` indirilip aynı preview/commit akışına verilecek.
- Bayios içinde scraping yapılmaz; yalnızca yayınlanmış JSON asset'i indirilir.
- Ağ erişimi, asset adı, sürüm doğrulama ve hata mesajları bu işte ele alınacak; mevcut `catalog.json` importu değişmeden kullanılacak.

## 11. Kampanya JSON içe/dışa aktarma (uygulandı)

- Kaynak: `docs/scrapper/kampanyalar_20261122-142627.json` (`schema_version` 1.0, 25 kampanya).
- `campaigns.external_id` slug; `campaigns.source_url`; `campaign_versions.conditions` JSONB, `source_category`, `source_product_count`, `scraped_at`.
- Import eşleştirmesi: önce slug, yoksa ad + tarih; ürünler önce ürün ID'si/alias, yoksa ad. Bulunamayan ürünler uyarıyla atlanır, kampanya yine oluşturulur.
- JSON'da yapısal indirim alanı olmadığı için kampanyalar `Genel` + `Sadece bilgi` olarak aktarılır; koşullar detay ekranında açılır/kapanır panelde gösterilir.
- Aynı şema JSON dışa aktarmada üretilir; kampanya listesi ve detayında JSON butonları vardır.
- Migration: `0019_campaign_scraper_metadata`.
