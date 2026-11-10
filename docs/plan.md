# BayiOS Detailed Implementation Planı

## 1. Amaç ve kapsam

Bu belge, [PRD](./prd.md)'deki Milestone 0–6'nın nasıl kodlanacağını tanımlar. Bu bir görev listesi değil; domain kurallarının hangi sınırda çalışacağını, yan etkilerin nerede tutulacağını, kritik davranışların nasıl doğrulanacağını ve her milestone'un hangi koşulda tamamlanmış sayılacağını belirleyen uygulama planıdır.

Mevcut repository henüz minimal bir Python paketidir. Bu nedenle ilk iş, mevcut prototipi production sözleşmesi olarak kabul etmeden, aşağıdaki modüler monolit iskeletini kurmaktır.

## 2. Değişmez tasarım kararları

### 2.1 Mimari

- Tek deploy edilen `src/bayios` paketi kullanılacak.
- `domain/` saf kuralları ve value object'leri içerir; FastAPI, SQLAlchemy, dosya sistemi ve zamanı doğrudan bilmez.
- `application/` command/query use-case'lerini, transaction orkestrasyonunu ve portları içerir.
- `adapters/` PostgreSQL/SQLAlchemy, CSV/XLSX, barcode decoder, clock ve backup entegrasyonlarını içerir.
- `web/` FastAPI route'ları, Pydantic HTTP şemaları, Jinja template'leri, HTMX fragment'ları ve local static asset'leri içerir.
- Route fonksiyonları iş kuralı uygulamaz; request'i parse eder, `ActorContext` oluşturur, use-case çağırır ve sonucu render eder.
- JSON API ve HTML/HTMX aynı application use-case'lerini çağırır.

Önerilen yapı:

```text
src/bayios/
  domain/
    products/
    imports/
    inventory/
    reservations/
    campaigns/
    offers/
    quick_deliveries/
    shared/
  application/
    commands/
    queries/
    ports/
    errors.py
  adapters/
    db/
      models/
      repositories/
      unit_of_work.py
    imports/
    barcode/
    clock.py
  web/
    api/
    pages/
    templates/
    static/
    errors.py
  jobs/
  bootstrap.py
  main.py
alembic/
tests/
  domain/
  application/
  integration/
  browser/
compose.yaml
```

### 2.2 Functional core / imperative shell

Saf domain fonksiyonları aşağıdaki türden işlemleri yapar:

- ürün adını normalize etme ve kesin eşleşme kararını verme;
- stok görünümünü (fiziksel stok ve açık rezervasyon) üretme;
- rezervasyon miktarlarını ve geçiş önkoşullarını doğrulama;
- kampanya rehberi senaryosunu hesaplama;
- komisyon ve minimum fiyat referansını `Decimal` ile hesaplama;
- import satırı kararlarını üretme;
- tarihsel durum özetini üretme.

Bu fonksiyonlar DB session'ı, HTTP request'i, global saat veya dosya sistemi almaz. Yan etkili işlemler application command'lerinde ve adapter'larda kalır. Class kullanımı framework model/şema, repository, unit-of-work ve adapter sınırlarıyla sınırlıdır; domain davranışı class hiyerarşisine dağıtılmaz.

### 2.3 Persistence ve transaction

- Sistem kaynağı PostgreSQL'dir; SQLite fallback'i yoktur.
- İç ID'ler UUID, kullanıcıya gösterilen reservation/offer/import numaraları ayrı unique alanlardır.
- Para alanları `NUMERIC/DECIMAL` olarak saklanır. Hesaplama ve sunum `ROUND_HALF_UP` ile iki kuruşta tutarlıdır.
- Zamanlar UTC saklanır, `Europe/Istanbul` ile gösterilir. “13 ay” takvimsel ay aritmetiğidir.
- Reservation + items aggregate kabul edilir.
- Teslim command'i reservation item miktarını, stock snapshot'ını, stock movement ledger'ını ve idempotency kaydını tek transaction'da günceller.
- Stokta snapshot hızlı okuma içindir; silinmeyen `stock_movements` geçmişin kaynağıdır.
- Import preview staging batch'tir. Commit, batch kararlarını ve kaynak version/checksum kontrolünü tek transaction'da uygular.
- Stock count completion, oturum açıldığından beri değişen stok varsa eski değeri sessizce ezmez; version conflict üretir.

### 2.4 HTTP ve UI

- Tek FastAPI uygulaması hem `/api/v1` JSON endpoint'lerini hem sayfa route'larını sunar.
- HTMX endpoint'leri gerektiğinde HTML fragment döndürür; JSON endpoint'leri HTML üretmez.
- Jinja2 server-rendered HTML temel UI'dır. Alpine.js yalnızca lokal UI state'i içindir.
- CDN ve runtime internet bağımlılığı yoktur. Node/Tailwind build zinciri eklenmez; versioned local CSS, print CSS ve sabitlenmiş/vendor HTMX-Alpine asset'leri uygulamadan servis edilir.
- Clipboard akışı tarayıcının `paste` olayıyla çalışır; `navigator.clipboard.read()` temel akış değildir.

### 2.5 Hata ve actor sözleşmesi

- `ActorContext`, `client_id` ve cihaz adını audit metadata olarak taşır; güvenlik veya yetkilendirme değildir.
- Çalışan adı nullable açıklayıcı kayıt alanıdır.
- Typed domain/application errors merkezi mapper ile HTTP ve HTMX cevaplarına çevrilir: validation, not found, conflict, stale version, duplicate barcode ve insufficient stock warning gibi sınıflar açıkça ayrılır.
- Broad catch, sessiz fallback ve hatayı başarı gibi gösteren cevap kullanılmaz.

## 3. Test stratejisi

Testler implementation ayrıntısını değil gözlenebilir davranışı güvenceye alır.

### 3.1 Katmanlar

1. **Domain unit testleri:** Yalnızca karmaşık, saf ve hata maliyeti yüksek kurallar: normalize/eşleştirme, stok formülleri, Decimal hesapları, campaign senaryosu ve state transition.
2. **Application/integration testleri:** Ana güvence. Gerçek PostgreSQL ve Alembic migration'larıyla command/query davranışı, transaction rollback, idempotency, snapshot ve concurrency doğrulanır.
3. **HTTP/HTMX acceptance testleri:** Kullanıcının kritik akışlarını endpoint sınırında doğrular; JSON shape veya fragment selector'ları yalnızca kullanıcı davranışı için kontrol edilir.
4. **Browser smoke:** Ayrı marker/komutla küçük set: ürün arama, HTMX form kaydı, clipboard barkod akışı ve print görünümü. Geniş HTML snapshot suite yoktur.
5. **Performance:** Milestone regression ölçümleri; release öncesi 5.000 ürün/4 client Locust gate'i.

Her test ortamı `DATABASE_URL` bekler. PostgreSQL Compose servisi local dev/test için sağlanabilir; bağlantı yoksa testler sessizce SQLite'a dönmez, açık environment hatası verir.

### 3.2 Özellikle test edilmeyecek alanlar

- trivial getter/setter ve framework'ün zaten doğruladığı alanlar;
- her template satırının snapshot'ı;
- her repository methodu için tekrar eden mock testleri;
- campaign için MVP'de desteklenmeyen genel sepet optimizasyonu;
- gerçek decoder görüntüsünün her application testinde tekrar çözülmesi.

## 4. Milestone uygulama planı

### Milestone 0 — Proje altyapısı

**Vertical slice sırası**

1. `pyproject.toml` içine FastAPI, SQLAlchemy, Alembic, Pydantic, Jinja2, PostgreSQL driver, pytest ve HTTP test araçlarını ekle; `uv` ile lock/kurulum akışını sabitle.
2. `src/bayios/bootstrap.py` içinde config, DB engine, session factory, unit-of-work ve dependency wiring oluştur.
3. `compose.yaml` ile app ve PostgreSQL servislerini ayır; Postgres portunu host'a publish etme, app portunu LAN kullanımına aç.
4. `/health` ve temel layout/navigation sayfasını ekle.
5. İlk migration, startup/shutdown ve structured logging akışını kur.
6. Ayrı backup command/container ve restore runbook'unu ekle.

**Kod sözleşmesi**

- `ApplicationSettings` environment'tan okur; production secret'ları image içine koymaz.
- `UnitOfWork` transaction sınırını açıkça açar/commit eder/rollback yapar.
- `get_actor` tek HTTP dependency'sidir.
- `/health` DB bağlantısını ve migration durumunu yanlış pozitif üretmeden raporlar.

**Davranış testleri**

- Compose PostgreSQL'e bağlanan uygulama health endpoint'i başarılı döner.
- Bir migration sonrası process restart kayıt kaybı yaratmaz.
- DB write exception'ı transaction'ı rollback eder ve success response üretmez.
- Bir desktop ve bir mobile user-agent temel layout'u yatay scroll olmadan alır.

**Çıkış kriteri**

Windows host üzerinde Docker veya Podman Compose ile app/PostgreSQL başlar; LAN'dan bir desktop ve mobile istemci erişir; DB volume kalıcıdır; backup/restore komutları belgelenmiştir.

### Milestone 1 — Product catalog ve import (Ürün Kataloğu ve CSV/Excel İçe Aktarma)

**Amaç ve Kapsam**

Ürün kataloğunu oluşturmak, aramak, detaylarını görüntülemek ve Arçelik bayi operasyonunun gerçek CSV dosyalarını (`arcelik-06-09-2026.csv`) ile Excel (`.xlsx`) dosyalarını önizleme/onay mekanizmasıyla hatasız içe aktarmak. Bu milestone; fiyat ve stok hareket geçmişini, kesin ürün adı normalizasyonunu, staging batch yönetimini ve atomik commit akışını kapsar.

**Gerçek CSV Formatı ve Doğrulama Kuralları (`arcelik-06-09-2026.csv`)**

Gerçek bayi dosyasının incelenmesi sonucunda saptanan biçim özellikleri ve domain kuralları:

1. **Başlık yapısı:** `product_name,regular_price,website_discounted_price,quantity`
2. **Fiyat formatı (Türkçe para gösterimi):**
   - Fiyatlar `38.099 TL`, `475 TL`, `10.349 TL` gibi `TL` soneki ve binlik basamak ayracı olarak nokta (`.`) içerir.
   - Normalizasyon; `TL`, `TRY`, `₺` soneklerini ve aradaki/sondaki boşlukları temizler.
   - Nokta (`.`) binlik ayracı olarak yorumlanır (`38.099 TL` -> `38099.00`). Varsa virgül (`,`) ondalık kuruş ayracıdır (`38.099,50 TL` -> `38099.50`, `12,50` -> `12.50`).
   - Negatif fiyatlar engellenir; geçersiz veya sayıya çevrilemeyen metinler `error` ("Regular Price must be a number") olarak işaretlenir.
3. **Eksik ve boş kolon toleransı:**
   - Bazı satırlarda 4. kolon (`quantity`) hiç bulunmaz (örn. `07325 A,38.099 TL,34.099 TL` — satır sonu virgülü yoktur). Parser `restval=None` ile okur, eksik kolonda çökmez.
   - Bazı satırlarda `quantity` boştur (örn. `0.58m  with Anderson cable,475 TL,`).
   - `quantity` boş/eksik olduğunda: Mevcut ürünün fiziksel stoku korunur (`quantity=None`), stok hareketi oluşturulmaz.
   - `quantity=0` olduğunda: Fiziksel stok sıfırlanır ve `stock_movements` tablosuna `csv_update` hareketi yazılır.
   - `website_discounted_price` boş olduğunda: Mevcut Oliz/indirimli fiyat korunur; indirimi kaldırmak için önizleme ekranından açıkça `clear_discount` kararı seçilmelidir.
4. **Ürün adı özellikleri ve normalizasyonu:**
   - Baştaki sıfırlar anlamlıdır ve korunur (`07325 A`, `09325 A`, `09605`).
   - Unicode NFKC normalizasyonu uygulanır (örn. `16343\xa0TVN` gibi bölünemez boşluk `\xa0` karakterleri standart boşluğa dönüştürülür).
   - Ardışık boşluklar tek boşluğa indirilir (`0.58m  with Anderson cable` -> `0.58m with Anderson cable`).
   - Kesin eşleşme `products.name_normalized` unique sütunu üzerinden yapılır; Türkçe `İ/I/ı/i` duyarsızlaştırması bu kolonda sağlanır.
5. **Katalogda olmayan ürünler:**
   - CSV dosyasında bulunmayan mevcut ürünler kesinlikle silinmez ve arşivlenmez.

**Vertical slice sırası**

1. **Domain normalizer ve kuralları:**
   - `normalize_product_name`: Unicode NFKC, strip, whitespace collapse, baştaki sıfırları koruma, Türkçe `İ/ı` dönüşümü.
   - `_normalize_decimal`: Türkçe binlik nokta ve `TL` sonekli değerleri (`38.099 TL`, `475 TL`), kuruşlu değerleri (`12,50`), düz sayıları (`1200`) hatasız `Decimal` string'e çevirme.
   - `_normalize_quantity`: Boşluk, tam sayı ve negatif olmama kontrolü.
   - `normalize_category_name`: Kategori eşleştirmesi için NFKC, strip, whitespace collapse ve Türkçe `İ/ı` duyarsızlaştırması.
   - Satır sınıflandırma politikası: `create` (yeni ürün), `update` (fiyat/stok değişimi), `skip` (fark yok veya kullanıcı kararı), `error` (eksik ad veya geçersiz sayı), `clear_discount` (indirimli fiyatı temizleme).
2. **CSV/Excel içe aktarma önizlemesi ve sorunlu satır yönetimi (`PreviewProductImport`):**
   - `utf-8`, `utf-8-sig` (BOM), `cp1254` (Windows-1254) fallback ve otomatik virgül/noktalı virgül delimiter algılama.
   - `.xlsx` desteği (`openpyxl` streaming `iter_rows`).
   - `product_import_batches` için staging batch kaydı (UUID, `source_checksum` SHA-256, `status='previewed'`).
   - **Sorunlu satırların önceliği:** Önizleme tablosunda hatalı (`error`) veya çakışmalı (`conflict`) satırlar daima listenin **en başında (en üstte)** sıralanır (`sort_key = (0 if is_problematic else 1, row_number)`).
   - **"Sorunluları Atla" butonu:** Toplu işlem seçeneklerinde "Tümünü güncelle" ve "Tümünü atla" butonlarının yanında, yalnızca sorunlu/hatalı satırların kararını `skip` yapan hedefli "Sorunluları Atla" butonu sunulur. Bu buton geçerli satırların kararına dokunmaz.
3. **Atomik içe aktarma onay mekanizması ve doğru sayaçlar (`CommitProductImport`):**
   - Tek `UnitOfWork` transaction sınırı.
   - Concurrency / Stale batch kontrolü: Dosya checksum veya önizleme zamanından sonra değişen ürün varsa commit reddedilir (`ConflictError`).
   - Yeni ürünler için `Product` insert, mevcutlar için update; atlanan satırlar için hiçbir yazma işlemi yapılmaz.
   - Yalnızca fiilen değişen fiyatlar için `ProductPriceHistory` kaydı (fiyat aynıysa gereksiz tarihçe oluşturulmaz).
   - Fiziksel stok değiştiğinde `StockMovement` kaydı (`movement_type='csv_update'`, `quantity_before`, `quantity_after`, `quantity_delta`, batch'e bağlı `idempotency_key`).
   - **Kategori:** `category` kolonu opsiyoneldir. Dolu gelirse `normalize_category_name` ile mevcut kategorilerle eşleşir; bilinmeyen adlar otomatik oluşturulur. Boş gelirse mevcut ürünün kategorisi korunur, yeni ürün kategorisiz açılır.
   - **Doğru istatistik bildirimi:** Batch özeti (`created_count`, `updated_count`, `skipped_count`, `error_count`) fiilen icra edilen işlemlere göre hesaplanır. Önizlemede atlanan satırlar kesinlikle eklenen veya güncellenen sayılarına dahil edilmez. Özet bilgi kutusu: `{created_count} yeni ürün eklendi, {updated_count} ürün güncellendi, {skipped_count} satır atlandı` şeklinde gerçeği tam yansıtır.
4. **Manuel yeni ürün oluşturma (`CreateProduct`):**
   - `CreateProduct` command'i: `product_name`, `regular_price`, `website_discounted_price`, `cost_price`, `physical_stock`, `category_id`.
   - Başlangıç fiyat geçmişi (`source='manual'`) ve başlangıç stok hareketi (`movement_type='manual_adjustment'`) kaydı.
   - UI'da "Yeni Ürün Ekle" modalı ve HTMX formu.
5. **Ürün arşivleme ve çift onaylı silme (`ArchiveProducts`, `DeleteProducts`):**
   - Çoklu seçim desteği: Tabloda satır bazında checkbox'lar ve "Tümünü Seç" kutusu.
   - `ArchiveProducts` ve `UnarchiveProducts`: Tekil veya çoklu ürünleri `is_archived=True/False` yapar. Arşivdekiler filtre ile görüntülenir.
   - `DeleteProducts` (Veritabanından Kalıcı Silme): Tekil veya çoklu silme.
   - **İki aşamalı doğrulama (Çift Onay):** Yanlışlıkla silinmeyi önlemek için arayüzde 1. aşama uyarı modalı (silinecek ürün sayısı ve risk bilgisi), ardından 2. aşama açık teyit adımı işletilir.
   - Açık rezervasyonu olan ürünlerin silinmesi domain kuralı ile engellenir (`ProductHasOpenReservationsError`).
6. **Ürünler sekmesinden doğrudan stok güncelleme (`AdjustProductStock`):**
   - Ürün detay kartında veya liste satırında fiziksel stok düzeltme girişi.
   - `movement_type='manual_adjustment'`, `quantity_delta` ve not ile stok hareketi yazılır.
   - Fiziksel stok doğrudan satılabilir stoktur; ayrı türetilmiş bir "satılabilir stok" alanı yoktur.
   - Bu akış Milestone 3'teki kapsamlı stok sayım modülü ile tam entegre çalışacak temeli oluşturur.
7. **Ürün kataloğu arama, UI ergonomisi ve detay sorguları:**
   - `SearchProducts`: Normalleştirilmiş ad ve baştaki sıfırları koruyan substring arama; kategori ve arşiv filtresi; sayfalama desteği.
   - **Arama kutusu düzeni:** Arama input alanı ve yanındaki "Ara" butonu responsive flex yapısında yan yana kalır (`whitespace-nowrap shrink-0`); buton metninin `AR<br>a` şeklinde kırılması engellenir.
   - `GetProductDetail`: Normal fiyat, Oliz fiyatı, maliyet, fiziksel stok, açık rezervasyon (M1'de 0), fiyat geçmişi ve stok hareket günlüğü.
8. **Katalog dışa aktarma (`ExportProducts`):**
   - Tüm ürünleri CSV (`utf-8-sig`) veya `.xlsx` olarak export etme.
   - Kolonlar: `product_name`, `category`, `regular_price`, `website_discounted_price`, `quantity`, `cost_price`.
   - `category` içe aktarmada opsiyonel, dışa aktarmada her zaman bulunur.
   - Filtreli export MVP dışıdır.
9. **Web arayüzü ve HTMX entegrasyonu:**
   - `/products`: Ürün listesi, responsive arama kutusu ("Ara" butonu tek satırda), "Yeni Ürün Ekle" butonu, checkbox seçim çubuğu ("Seçilenleri Arşivle", "Seçilenleri Sil", "Kategori Ata"), sayfalama.
   - `/products/new`: Manuel ürün ekleme modalı/formu.
   - `/products/{id}`: Ürün detay kartı, kategori bilgisi, doğrudan stok güncelleme alanı, fiyat ve stok hareket geçmişi sekmeleri.
   - `/products/archive`, `/products/delete`, `/products/bulk-category`: Toplu arşivleme, çift onaylı silme ve toplu kategori atama endpoint'leri.
   - `/imports/products`: CSV/XLSX dosya yükleme alanı (drag & drop ve dosya seçici).
   - `/imports/products/preview`: Önizleme tablosu; sorunlu satırlar en başta; "Sorunluları Atla" butonu; satır bazında ve toplu kararlar.
   - `/imports/products/commit`: Onay butonu ve tam gerçeği yansıtan özet bildirim paneli (toast/banner).
10. **Ürünlere kategori atama (`AssignProductsCategory`):**
    - Ürün detayındaki düzenleme formu kategori seçimini destekler (`update_product`).
    - Ürün listesinde seçilen birden fazla ürün için `AssignProductsCategory` command'i `category_id` veya `None` (kategorisiz) alır.
    - Toplu işlem stok, fiyat, arşiv ve geçmiş kayıtlarına dokunmaz; yalnızca `products.category_id` güncellenir.
    - Başarı bildirimi güncellenen ürün sayısını gösterir.
11. **Sayfalama ve doğrudan sayfa geçişi:**
    - Ürünler listesinde mevcut önceki/sonraki butonlarına ek olarak sayfa numarası girişi ve "Git" butonu bulunur.
    - Sayfa geçişi `q`, `status`, `category_id` ve `limit` gibi mevcut filtre parametrelerini korur.
    - Aynı ortak sayfalama bileşeni stok sayfası ve sayım satırlarında yeniden kullanılır.

**Kod sözleşmesi**

- Domain parser'lar saf Python fonksiyonlarıdır; DB veya HTTP bilmez.
- Commit işlemi tamamen atomiktir; kısmi hata durumunda hiçbir satır yazılmaz.
- `ProductImportBatch.source_checksum` mükerrer onayları engeller.
- `products.name_normalized` üzerindeki UNIQUE kısıt duplikasyonu DB seviyesinde garantiler.

**Davranış testleri**

- Gerçek `arcelik-06-09-2026.csv` satırları (`38.099 TL`, `475 TL,`, `07325 A,38.099 TL,34.099 TL`) sıfır hatayla ayrıştırılır ve doğru `Decimal` değerlerine normalize edilir.
- `07325 A` ile `07325A` farklı ürünler olarak saklanır; arama baştaki sıfırları korur.
- Aynı ürün ikinci kez aktarıldığında yeni ürün açılmaz, mevcut güncellenir.
- Fiyat değişmemişse `ProductPriceHistory` oluşturulmaz; değişmişse eski/yeni değerlerle tarihçe yazılır.
- Boş `quantity` mevcut stoku korur; `0` stoku sıfırlar ve stok hareketi oluşturur.
- CSV'de bulunmayan ürünler silinmez ve `is_archived=True` yapılmaz.
- Hatalı satırlar geçerli satırların önizlemesini veya aktarımını engellemez; önizleme listesinde hata nedeni gösterilir.
- Önizleme tablosunda hatalı ve çakışmalı satırlar listenin en başında listelenir.
- "Sorunluları Atla" tıklandığında yalnızca hatalı satırlar `skip` kararına geçer; geçerli satırların kararları korunur.
- Önizlemede tümü atlandığında commit sonucu "0 yeni ürün eklendi, 0 ürün güncellendi, X satır atlandı" bilgisini tam doğrulukla raporlar; yanlış ekleme/güncelleme sayısı üretmez.
- Manuel ürün ekleme formu geçerli verilerle yeni ürün kaydı açar; başlangıç fiyat ve stok geçmişi oluşturur.
- Seçilen ürünler toplu olarak arşivlenebilir (`is_archived=True`); arşivdekiler varsayılan aramada gizlenir ve istendiğinde geri alınabilir.
- Silme işlemi iki aşamalı doğrulama (çift onay) tamamlanmadan DB'den kayıt silmez; 2. onay verildiğinde kalıcı silinir. Açık rezervasyonu olan ürün için silme talebi reddedilir.
- Ürün ekranından doğrudan stok güncellendiğinde fiziksel stok değişir ve `manual_adjustment` hareketi yazılır.
- Ürün arama kutusu ve "Ara" butonu mobilde ve masaüstünde `whitespace-nowrap` ile tek satırda yan yana durur; metin bölünmesi (`AR<br>a`) oluşmaz.
- Ürün detayından kategori seçilip kaydedildiğinde kategori güncellenir; stok ve fiyat değişmez.
- Birden fazla ürün seçilip toplu kategori atandığında tüm seçilen ürünlerin `category_id` değeri aynı olur; "Kategorisiz" seçimi kategoriyi temizler ve bildirim doğru sayıyı gösterir.
- Ürünler listesinde sayfa numarası girilerek doğrudan son sayfaya gidilebilir; `q` ve `status` filtreleri korunur.
- Önizleme onaylanmadan DB'de ürün veya stok değişikliği yapılmaz.
- Önizleme sonrası ürün değişmişse commit stale conflict döner; aynı commit retry duplicate yaratmaz.

**Çıkış kriteri**

Gerçek `arcelik-06-09-2026.csv` dosyası web arayüzünden veya API'den önizlenir; hatalı satırlar en üstte listelenir; "Sorunluları Atla" butonu ve doğru commit özet sayaçları doğrulanır; manuel ürün eklenebilir; çoklu arşivleme ve çift onaylı silme hatasız çalışır; ürün detayından ve çoklu seçimle kategori atanabilir; sayfa numarası yazarak doğrudan geçiş çalışır; ürünler sekmesinden doğrudan stok güncellenebilir; arama butonu dikey kırılmaz; kullanıcı onayıyla tek transaction'da DB'ye kaydedilir; ürün arama ve detay sayfalarında anında sorgulanabilir.

### Milestone 2 — Reservation ve A4

**Domain ve veri**

- Reservation aggregate; reservation item; item event ve reminder history tabloları.
- `quantity`, `delivered_quantity`, `cancelled_quantity` gerçek miktar alanlarıdır; `quantity > 0` ve `delivered + cancelled <= quantity` her write'ta korunur.
- `reservation_items.product_id` nullable ve `ON DELETE SET NULL`'dır: açık rezervasyon satırı olan ürün silinemez, teslim/iptal edilmiş satır ise ürün silinse de `product_name_snapshot` ile geçmişte kalır. Rezervasyonda telefon alanı yoktur (PRD 4.5).
- **Durum politikası:** `RESERVED`, `DELIVERY_REQUESTED`, `DEPOT_READY`, `SERVICE_ASSIGNED` arasında ileri atlama serbesttir ve teslimden önce bir önceki duruma dönüş serbesttir; bu geçişlerin hiçbiri stoğa dokunmaz. `DELIVERED` ve `CANCELLED` terminaldir ve yalnızca deliver/cancel use-case'leriyle üretilir. Teslim, herhangi bir aktif durumdan yapılabilir; `SERVICE_ASSIGNED` önkoşulu yoktur.
- **Düzenleme:** müşteri adı/not güncellenebilir; açık satırın miktarı değiştirilebilir; satır eklenebilir veya silinebilir. Teslim veya iptal miktarı bulunan satırda miktar `delivered + cancelled` altına inemez ve satır silinemez.
- **İptal:** kalem bazında kısmi miktar iptali, isteğe bağlı notla yapılır; fiziksel stoktan düşüm veya stok hareketi üretmez. Teslim edilmiş miktar iptal edilemez.
- **Takvim:** 13 aylık varsayılan hatırlatma ve 1 aylık varsayılan erteleme takvimsel ay aritmetiğidir ve ay sonunda kırpılır (31 Ocak + 1 ay → 28/29 Şubat). Tüm satırlar terminal olduğunda hatırlatma otomatik `resolved` olur. Teslim edilmiş miktarın ters hareketle geri alınması M2 kapsamı dışıdır.
- **Tarih seçici (UX):** Rezervasyon tarih alanları yerel vendor edilen **Flatpickr 4.6.13** + resmi `tr` locale ile sunulur; CDN yoktur, dosyalar `static/vendor/flatpickr/` altında, SHA-256 özetleri `VERSIONS.txt` içinde ve MIT lisansı yanındadır. Alan görünürde `GG.AA.YYYY` sayısal tarih, altında `10 Kasım 2026` önizlemesi gösterir; forma giden değer ISO kalır, `Bugün`/`Temizle` düğmeleri vardır, mobilde de Flatpickr açılır ve JS yüklenmezse native `date` input fallback'i çalışır.
- Açık rezervasyon toplamı `quantity - delivered_quantity - cancelled_quantity` üzerinden hesaplanır ve ürün detayı, stok özeti ve ana ekran aynı policy'yi kullanır.
- M5 teklif→rezervasyon dönüşümü aynı `CreateReservation` use-case'ini ürün/miktar girdisiyle kullanacak; rezervasyonda fiyat snapshot'ı tutulmaz.

**Use-case akışları**

1. Reservation create: müşteri adı zorunlu, en az bir satır; fiziksel stok düşmeden open reservation artır; 13 aylık hatırlatma tarihi atanır. Arşivli ürün de rezervasyona girebilir.
2. Reservation edit: müşteri adı/not, açık satır miktarı, satır ekleme/silme; her değişiklik item event geçmişine yazılır.
3. Item status: aktif durumlar arasında opsiyonel ileri atlama ve geri dönüş; servis tarihi/notları taşınır; canlı durum değişikliği stok hareketi üretmez.
4. Deliver: istenen miktarı açık miktara karşı doğrula, düşük stokta gerekçe iste, `delivery_out` movement + item event + idempotency kaydını tek transaction'da yaz; item ve ürün satırları kilitlenir.
5. Cancel: kalan miktardan düş, stoktan çıkış yapma, item event yaz.
6. Remind/snooze: 13 aylık default, 1 aylık snooze tarihçesi; terminal satırlarda otomatik resolved; ana ekranda gecikmiş/yaklaşan uyarı.
7. Print: tek çıktıda depo + bayi kopyası (arada sayfa sonu) ve `copy=depot|dealer` tekil kopya; rezervasyon listesi ve detayı `@media print` ile A4.
8. Entegrasyon: ürün detayı/stok özeti açık rezervasyon toplamını gösterir; açık rezervasyonu olan ürünün hard delete'i `ProductHasOpenReservationsError` ile engellenir.

**Davranış testleri**

- Başlangıç fiziksel 5 iken 2 reservation sonrası physical 5, open 2 olur; fiziksel stok değişmez.
- Delivery requested/depot ready/service assigned physical stock'u değiştirmez.
- 1 teslim sonrası physical 4, open 1 olur; kalan teslim sonrası physical 3, open 0 olur.
- Aynı idempotency key veya aynı teslim command retry'si ikinci movement üretmez.
- Kısmi teslim ve çok ürünlü reservation diğer açık satırları bozmaz.
- A4 depot/dealer çıktıları müşteri/ürün/miktar bilgilerini taşır.

**Çıkış kriteri**

Bir reservation uçtan uca takip edilir; duplicate stock deduction mümkün değildir; çıktı siyah-beyaz A4'te okunur.

### Milestone 3 — Stock count ve özet

**Use-case akışları**

- Product detail ve stock listesi physical/open görünümünü aynı hesap policy'sinden alır.
- Category ile count session açılır; sistem quantity snapshot'lanır.
- Counted quantity girilir; difference kullanıcıya gösterilmeden complete edilemez.
- Completion sırasında current stock version kontrol edilir; conflict varsa yeniden hesaplama/review istenir.
- Farklar stock adjustment movement olarak ledger'a yazılır; movement silinmez.

**Kullanım kolaylığı gereksinimleri**

1. Stok sayfası açıldığında `open` ve `review` durumundaki oturumlar ürün tablosunun üstünde ayrı bir "Açık Sayım Oturumları" bölümünde listelenir; her satırda "Devam Et" bağlantısı bulunur. Tamamlanmış oturum geçmişi sayfanın altında kalır.
2. Stok ürün listesi `page`/`limit` parametreleriyle sayfalanır; arama (`q`) ve kategori filtresi korunur. Kategori seçimi ve arama yazımı "Ara" butonuna gerek kalmadan sonuçları otomatik yeniler.
3. Sayım oturumu ürün satırları da sayfalanır; sayılan miktar formu yalnızca görünen sayfadaki alanları gönderir, diğer sayfalardaki kayıtlı değerler korunur.
4. Ortak sayfalama bileşeni önceki/sonraki butonları, sayfa numarası girişi ve "Git" butonu içerir; kullanıcı doğrudan son sayfaya atlayabilir.
5. Açık sayım oturumunda "Miktarları Kaydet" butonu `position: fixed` eylem çubuğunda ekranın altında durur; içerik için alt boşluk bırakılır ve yazdırma CSS'inde gizlenir.

**Davranış testleri**

- CSV, delivery ve count movement türleri ayrıştırılır.
- Rezervasyon açılışı fiziksel stoğu değiştirmez; yalnızca teslimat fiziksel stoğu düşürür.
- Eşzamanlı movement sonrası eski count sessizce overwrite etmez.
- Completed session tekrar complete edilince duplicate movement üretmez.
- A4 kategori listesi elle yazılabilir alanları içerir.
- Stok sayfasında açık/incelemedeki oturumlar üst bölümde görünür ve "Devam Et" doğru oturuma gider.
- Stok listesi ve sayım satırlarında sayfa numarasıyla doğrudan son sayfaya geçiş çalışır; filtre parametreleri kaybolmaz.
- Açık sayım oturumunda "Miktarları Kaydet" butonu HTML'de sabit eylem çubuğu içinde bulunur ve formu gönderir.

**Çıkış kriteri**

Kategori sayımı uygulamaya işlenir, fark ve actor/time history görünür, movement geçmişi denetlenebilir; açık oturumlar üstte erişilebilir; uzun listelerde sayfalama ve sabit kaydet butonu kullanılabilir.

### Milestone 4 — Campaign ve dealer price guide

**MVP sınırı**

Campaign modeli basit ve ürün ilişkili rehberdir: ad, açıklama, geçerlilik, active/history, şart ürünleri, fayda ürünleri, indirim türü/oranı/tutarı, fiyat tabanı ve hediye notu. Ürün bazlı “A alınca B indirimli” gibi ilişkiler saklanabilir.

Genel rule engine, optimal sepet seçimi, WMS/POS entegrasyonu ve otomatik satış fiyatı uygulaması yapılmaz. Çalışan campaign'i rehberden seçer ve Offer snapshot'ına alır.

**Domain ve veri**

- **Sürümleme:** `campaigns` yalnızca kimliği, arşiv durumunu ve `current_version_id` işaretçisini taşır. Kampanya alanları ve ürün ilişkileri `campaign_versions` / `campaign_version_products` içinde değişmez sürümler olarak tutulur. Her düzenleme yeni sürüm üretir; eski sürüm hiçbir zaman güncellenmez. Fiili değişiklik yoksa yeni sürüm oluşturulmaz. Kampanya kalıcı silinmez, arşivlenir; sürüm geçmişi audit amaçlı korunur.
- **Ürün ilişkisi:** Sürüm ürünlerinde `relation_type` (`qualifying`, `benefit`, `gift`, `related`) ve isteğe bağlı `quantity_required` bulunur. `product_id` nullable ve `ON DELETE SET NULL`'dır; `product_name_snapshot` sayesinde ürün silinse de sürüm geçmişi okunabilir kalır. Ürün grubu, aynı sürümde birden fazla ürün ilişkisiyle temsil edilir; kategori bazlı toplu ilişki kapsam dışıdır.
- **Tipler:** `general`, `product_discount`, `bundle`, `gift`, `coupon`, `special` tiplerinin tamamı kaydedilebilir. İndirim türleri `percent`, `fixed_amount`, `special_price`, `gift`, `info_only`'dir. Fiyat senaryosu yalnızca yüzde, sabit tutar, özel fiyat ve hediye tiplerinde hesaplanır; `info_only` ve kupon tipi açıklama olarak gösterilir.
- **Takvim:** `starts_at`–`ends_at` aralığı ve arşiv durumu aktif/geçmiş filtresini belirler. Tarihi geçmiş veya arşivlenmiş kampanya aktif listede görünmez, geçmiş filtresinde görünür. Aktif kampanya sorgusu güncel sürümün tarihleriyle yapılır; eski sürümler sorgu için zaman makinesi değildir.
- **Senaryo:** Hediye varsa bayi indirimi normal fiyat üzerinden; hediye yoksa Oliz fiyatı varsa Oliz, yoksa normal fiyat üzerinden hesaplanır. Varsayılan oran `dealer_discount_settings` içinden gelir ve başlangıç değeri %10'dur; çalışan oranı %0–100 aralığında değiştirebilir. Hesap `Decimal` ve `ROUND_HALF_UP` ile iki hanede yapılır. Çalışanın girdiği oran yalnızca ekrandaki senaryoda kalır; kalıcı snapshot M5 teklifinde alınır.
- **Bayi fiyatı:** Her ürün için tek güncel `dealer_pricing` kaydı (`cash_floor_price`, `card_floor_price`) tutulur. Her fiili değişiklik `dealer_pricing_history` içine eski/yeni değer, tarih, çalışan ve isteğe bağlı notla değişmez satır olarak yazılır. `valid_from`/`valid_until` kullanılmaz; değişiklik anında geçerli olur. Geçmiş, ileride eklenecek hesaplayıcı için korunur. Ürüne özel nakit/kart tabanları genel bayi indirimi oranıyla karıştırılmaz ve ayrı alanlarda gösterilir.
- **Varsayılan oran:** `dealer_discount_settings` güncel varsayılan oranı, `dealer_discount_setting_history` ise değişiklik geçmişini tutar. Oran değişikliği de yalnızca fiili değişiklikte geçmişe yazılır.
- **Kapsam dışı:** Kredi kartı taksit başına komisyon ve kart hesaplayıcısı M4'te yoktur; M5 ve sonrasına bırakılır. M4 yalnızca bu hesaplayıcının kullanacağı fiyat geçmişini güvenilir biçimde saklar.

**Use-case akışları**

1. Campaign create: ad, açıklama, tip, geçerlilik, fiyat tabanı, indirim/hediye alanları ve ürün ilişkileriyle ilk sürümü (`v1`) oluştur; `current_version_id` bu sürümü gösterir.
2. Campaign update: alan veya ürün ilişkisi değiştiyse yeni değişmez sürüm ekle ve işaretçiyi güncelle; değişiklik yoksa mevcut sürümü koru.
3. Campaign archive/restore: kampanyayı kalıcı silmeden arşivle veya geri al; sürümler korunur.
4. Campaign list: arama, genel/ürün bazlı, aktif/geçmiş/tümü ve tarih aralığı filtreleriyle sayfalı liste; her satırda güncel sürümün özeti görünür.
5. Campaign detail: güncel sürüm, sürüm geçmişi, ürün ilişkileri ve seçilen ürün için hediye var/yok fiyat senaryosu; çalışan oranı anlık değiştirebilir.
6. Dealer pricing: ürün detayında nakit/kart tabanını güncelle; yalnızca değişen değer için history yaz; fiyat geçmişini göster.
7. Default dealer discount: kampanyalar ekranındaki panelden varsayılan oranı güncelle; history'yi göster.
8. Product detail: ürünle ilişkili aktif kampanyaları ve ürünün nakit/kart taban fiyatlarını göster.
9. Print: kampanya listesi ve detayı A4'e basılabilir; senaryo ve fiyat tabanı okunaklı kalır.

**Davranış testleri**

- Tarih dışı campaign active listede görünmez, history filtresinde görünür.
- Normal 25.999, Oliz 23.999 ve %10 örneği hediye var/yok senaryolarını doğru gösterir.
- Oliz fiyatı olmayan üründe bayi indirimi normal fiyat üzerinden örneklenir.
- %10 yalnızca default öneridir; çalışan %15 girebilir.
- Campaign değişince eski sürüm ve eski Offer snapshot'ı değişmez.
- Ürün özel nakit/kart minimumları genel oranla karışmaz.
- Değişiklik olmayan düzenleme yeni sürüm veya history satırı üretmez.
- Bayi fiyatı geçmişi eski/yeni değeri, tarihi ve çalışanı korur; ürün silinse kampanya sürümü ürün adı snapshot'ıyla okunabilir kalır.

**Çıkış kriteri**

Çalışan aylık ürün campaign'lerini anlaşılır rehber olarak görür, senaryo seçimini Offer'a kaydeder; otomatik POS iddiası oluşmaz. Kampanya düzenlemeleri değişmez sürümlerle izlenebilir; bayi nakit/kart tabanları ve varsayılan indirim oranı geçmişiyle birlikte yönetilir.

### Milestone 5 — Offer ve commissions

**Use-case akışları**

1. Bank/taksit commission period CRUD.
2. `CalculateReferencePrice`: cost + target profit / `(1 - commission)`; `Decimal`, `%0` ve undefined target profit guard'ları.
3. Çok ürünlü Offer create/update; her kalemde fiyatlama, campaign, commission ve ürün adı snapshot'ı.
4. Nakit/kart seçimi; tek bank/taksit constraint'i.
5. Offer history ve A4 customer copy; cost/internal profit müşteri çıktısında yok.
6. Açık `ConvertOfferToReservation` command'i; Offer immutable kalır, yeni Reservation snapshot'tan doğar ve retry idempotent'tir.

**Davranış testleri**

- 30.000 + 1.500 hedef ve %5 commission sonucu 33.157,89 TL'dir.
- %0 commission sonucu cost + profit'tir.
- Tanımsız hedef kâr açık uyarıdır.
- Commission değişince eski Offer değişmez.
- Multi-item Offer ve müşteri A4 çıktısı iç kâr sızdırmaz.
- Conversion retry duplicate Reservation oluşturmaz.

**Çıkış kriteri**

Offer geçmişi fiyat/commission değişimlerinden bağımsızdır; örnek hesaplar geçer; müşteri çıktısı iç verileri içermez.

### Milestone 6 — Hızlı Teslim / Code 128

**Sınır**

`BarcodeDecoder` application port'udur. Gerçek `pyzbar`/Code 128 adapter'ı görüntüden değer döndürür; application testleri deterministic fake kullanır. Original image kalıcı saklanmaz.

**Use-case akışları**

1. Upload veya clipboard input'u validate et.
2. Decoder sonucu yoksa açık retry error; birden fazlaysa kullanıcı seçimi.
3. İnsan-okunabilir metinle decoded değer uyuşmuyorsa confirm etme.
4. Kullanıcı doğrulamasından sonra customer + exact barcode + source/time metadata'yı kaydet.
5. `barcode_value` unique conflict'i mevcut kaydı gösterir.

Manuel barcode input, product lookup ve WMS request'i yoktur. UI'da “WMS çıkışı bu uygulamada yapılmaz” açıklaması bulunur.

**Davranış testleri**

- Aynı görüntü upload ve clipboard'dan aynı exact Code 128 değerini üretir.
- Baş/son haneler korunur.
- Decode failure success-shaped response üretmez.
- Birden çok barcode selection gerektirir.
- Human-readable mismatch kayıt oluşturmaz.
- Aynı barcode ikinci kez kaydedilemez.
- WMS'e network call yapılmaz.

**Çıkış kriteri**

Hızlı Teslim kaydı doğrulanmış tek Code 128 değeri taşır; görüntü saklanmaz; duplicate ve mismatch açıkça yönetilir.

## 5. Release ve doğrulama sırası

Her milestone şu sırayla teslim edilir:

1. Migration ve saf domain policy.
2. Application command/query ve integration test.
3. JSON API ve HTMX/page route.
4. Mobil/print UI.
5. Migration rollback/backup kontrolü.
6. İlgili browser smoke ve performance regression.
7. Milestone çıkış kriteriyle manuel pilot doğrulaması.

Final release öncesi 5.000 ürün ve 4 concurrent client ile PRD p95 hedefleri Locust'ta ölçülür. Hedef aşılırsa yeni özellik eklenmez; query/index/host kararı alınır.

