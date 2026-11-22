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
- banka ve kategori adını normalize etme ve canonical görünen adı üretme; ürün adını yalnız eşleştirme/arama için normalize etme;
- komisyon oranını ve taksit limitini banka özel/bankasız kapsamda çözümleme;
- import satırı kararlarını üretme;
- tarihsel durum özetini üretme.

Bu fonksiyonlar DB session'ı, HTTP request'i, global saat veya dosya sistemi almaz. Yan etkili işlemler application command'lerinde ve adapter'larda kalır. Class kullanımı framework model/şema, repository, unit-of-work ve adapter sınırlarıyla sınırlıdır; domain davranışı class hiyerarşisine dağıtılmaz.

### 2.3 Persistence ve transaction

- Sistem kaynağı PostgreSQL'dir; SQLite fallback'i yoktur.
- İç ID'ler UUID, kullanıcıya gösterilen reservation/offer/import numaraları ayrı unique alanlardır.
- Banka ve kategori adlarında tekil anahtar `*_normalized` sütunu, canonical görünen ad ayrı sütundur; ürün adı yazıldığı gibi saklanır ve `products.name_normalized` yalnız eşleştirme/arama içindir. Komisyon tekil kapsamı `scope_key` üzerinden banka boş değerini de kapsar.
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
- Kullanıcıya gösterilen tüm validation, conflict ve warning metinleri Türkçedir. Domain katmanı kullanıcıya ulaşabilecek hata ve uyarıları Türkçe üretir; İngilizce teknik mesaj doğrudan UI'a taşınmaz.
- Broad catch, sessiz fallback ve hatayı başarı gibi gösteren cevap kullanılmaz.

### 2.6 Örnek veri ve gizli ticari veri sınırı

Korunan bilgi, şirketin herkese açık kataloğunda görünmeyen iç ticari veridir: gerçek komisyon anlaşmaları, alış maliyeti, bayiye özel taban fiyat, kâr hedefi ve müşteri verisi kodda, testlerde, fixture'larda, dokümanlarda ve örnek dosyalarda yer almaz (PRD §3.4). Katalog ürün adları ve liste fiyatları herkese açık veridir; örnek dosyalarda bulunabilir. Belgelerdeki ve testlerdeki banka adları, oran ve limit örnekleri temsilîdir; gerçek sözleşme değeri olmadıkça kullanılabilir. `.env`, veritabanı dökümü ve maliyet/komisyon içeren dosyalar `.gitignore` kapsamındadır. Gerçek sözleşme verisi olduğundan şüphelenilen bir değer PR'da görülürse değişiklik reddedilir.

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
   - `website_discounted_price` kolonu varsa ve hücre boş/`0` ise: Güncellemede mevcut Oliz/indirimli fiyat otomatik silinir (Oliz kampanyası bitti kabul edilir). Kolon hiç yoksa mevcut değer korunur; `clear_discount` kararı yalnızca kolon yokken manuel temizlik için opsiyonel kalır.
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
   - `canonical_display_name`: Banka ve kategori adları için Türkçe kurallarıyla başlık biçimi (`AKBANK`/`akbank`/`AkbanK` -> `Akbank`, `ÇAMAŞIR MAKİNESİ` -> `Çamaşır Makinesi`). Rakam içeren token'lar ve kısa büyük harf kısaltmaları (`TV`, `LED`, `HP`) korunur. **Ürün adlarına uygulanmaz**; ürün adı yazıldığı gibi kalır ve `normalize_product_name` yalnız eşleştirme/arama içindir. Python'un dil duyarsız `title()` davranışı kullanılmaz.
   - Satır sınıflandırma politikası: `create` (yeni ürün), `update` (fiyat/stok değişimi), `skip` (fark yok veya kullanıcı kararı), `error` (eksik ad veya geçersiz sayı), `clear_discount` (kolon yokken manuel indirimli fiyat temizleme; boş/0 hücre artık otomatik temizler).
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
   - **Arama kutusu düzeni:** Arama input alanı ve yanındaki "Ara" butonu responsive flex yapısında yan yana kalır (`whitespace-nowrap shrink-0`); buton metninin `AR<br>a` şeklinde kırılması engellenir. Arama/filtre kartı üstte sticky kalır.
   - **Seçim ve toplu işlem:** Seçim varken toplu işlem çubuğu `position: fixed` alt footer olarak gösterilir; tablo altına spacer eklenir. Çubukta tümünü seç checkbox'ı yer alır ve tablo başlığındaki seçimle senkron çalışır. Satır boş alanı tıklaması tüm ekranlarda seçim yapar; etkileşimli öğeler hariçtir.
   - `GetProductDetail`: Normal fiyat, Oliz fiyatı, maliyet, fiziksel stok, açık rezervasyon (M1'de 0), fiyat geçmişi ve stok hareket günlüğü.
8. **Katalog dışa aktarma (`ExportProducts`):**
   - Tüm ürünleri CSV (`utf-8-sig`) veya `.xlsx` olarak export etme.
   - Kolonlar: `product_name`, `category`, `regular_price`, `website_discounted_price`, `quantity`, `cost_price`.
   - `category` içe aktarmada opsiyonel, dışa aktarmada her zaman bulunur.
   - Filtreli export MVP dışıdır.
9. **Web arayüzü ve HTMX entegrasyonu:**
   - `/products`: Ürün listesi, responsive arama kutusu ("Ara" butonu tek satırda), "Yeni Ürün Ekle" butonu, sayfalama.
   - Üst arama/filtre alanı sticky; seçim varken toplu işlem çubuğu ekran altında sticky footer olarak gösterilir (seçilen sayısı, "Tümünü seç", "Kategori Ata", "Seçilenleri Arşivle", "Seçilenleri Sil") ve içerik için alt boşluk bırakılır.
   - Satırın boş alanına tıklama tüm ekran boyutlarında satır seçimini değiştirir; bağlantı, buton, checkbox ve form alanları hariçtir. "Tümünü seç" hem tablo başlığında hem sticky çubukta bulunur; dar ekranda başlık gizlense de çubuktan kullanılabilir.
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
- `ÇAMAŞIR MAKİNESİ` ve `çamaşır makinesi` aynı kategoriyi eşler ve görünen ad `Çamaşır Makinesi` olur. Ürün adı `901 KMX` yazıldığı gibi kalır; `901 kmx` araması onu bulur.
- Aynı ürün ikinci kez aktarıldığında yeni ürün açılmaz, mevcut güncellenir.
- Fiyat değişmemişse `ProductPriceHistory` oluşturulmaz; değişmişse eski/yeni değerlerle tarihçe yazılır.
- Boş `quantity` mevcut stoku korur; `0` stoku sıfırlar ve stok hareketi oluşturur.
- Oliz kolonu varsa boş/`0` hücre güncellemede mevcut Oliz fiyatını otomatik siler ve fiyat geçmişi yazar; kolon hiç yoksa mevcut Oliz değeri korunur.
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
- Ürün satırının boş alanına tıklama masaüstü ve mobilde satır seçimini değiştirir; bağlantı/buton/checkbox/form tıklamaları seçimi değiştirmez.
- Seçim varken toplu işlem çubuğu ekran altında sticky footer olarak görünür; tablo altında boşluk bırakır ve "Tümünü seç" checkbox'ı tablo başlığıyla senkron çalışır.
- Seçili satır mavi dolgu yerine accent kenarlıkla vurgulanır; bu stil masaüstü tablo ve mobil kart görünümünde aynıdır. Masaüstünde sol menü sticky ve kendi içinde kaydırılabilir.
- Dar ekranda tablo başlığı gizlense de "Tümünü seç" sticky çubuktan kullanılabilir; seçilen sayısı ve toplu eylemler görünür kalır.
- Arama/filtre kartı sayfa kaydırıldığında üstte sticky kalır.
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
- **Dil:** Kullanıcıya gösterilen doğrulama hataları ve senaryo uyarıları dahil tüm metinler Türkçedir. Domain katmanı kullanıcıya ulaşabilecek mesajları Türkçe üretir; İngilizce teknik mesaj UI'a sızmaz.

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

**MVP sınırı**

Komisyonlar aylık dönemler halinde yönetilir. Her kanalda banka isteğe bağlıdır: bankasız satır tüm bankalar için genel orandır, bankaya özel satır yalnız o bankada genel oranı geçersiz kılar. Chippin'de genel 1 taksit (tek çekim) tüm bankalara açıkken banka/kart bazlı taksit limitleri ayrıca tanımlanır. Klima tek ayrı komisyon grubudur; TV ayrı oran grubu değildir, `other` oranlarını kullanır ve yalnız taksit üst sınırıyla ayrışır. Kategori sınırı (örnek TV 4) kodda sabit değildir; dönem verisidir ve aylık düzenlenebilir. Ödero komisyonu Diğer ürünlerde sepet toplamına göre 20.000 TL altı/üstü olarak ayrılır; Klima'da bant kullanılmaz. Business kart yalnızca taksit üst sınırını 2'ye indirir.

Teklifler fiyat katmanlarını ve önerileri gösterir; nihai nakit/kart birim fiyatını çalışan girer. Kampanya satır bazında tek seçilir; kampanya seçilirse Oliz uygulanmaz ve iki kampanya birleşmez. Bayi indirimi teklif genelinde tek orandır ve teklif başına override edilebilir.

Çoklu banka/taksit yan yana karşılaştırma, karma ödeme, otomatik POS fiyatı uygulaması ve genel kâr optimizasyonu M5 dışıdır.

**Domain ve veri**

- `commission_periods`: `period_key` (`YYYY-MM`), `valid_from`, `valid_until`, durum (`draft`, `active`, `archived`) ve `copied_from_id`. Ay başında yeni dönem önceki dönemi kopyalayarak açılır; geçmiş dönem değişmez.
- `banks`: `name` (canonical görünen ad) ve `name_normalized` (unique). Yazım varyantları aynı kaydı verir; formdan hızlı ekleme `EnsureBank` use-case'i üzerinden çalışır.
- `commission_rates`: dönem, kanal (`pos`, `odero`, `chippin`), banka (nullable = bankasız genel oran, her kanalda), ürün grubu (`klima`, `other`), taksit ve Ödero tutar bandı (`under_20000`, `over_20000`; yalnız Ödero + Diğer). TV oranı `other` grubunu kullanır; Klima'da bant zorunlu değildir.
- `commission_rates` tekilliği: `(period_id, scope_key)`; `scope_key` banka ve tutar bandı boş değerlerini `-` ile temsil eder. Çözümleme banka özel -> genel -> hata sırasıyla yapılır.
- `commission_limits`: dönem, kanal, banka, ürün grubu, kategori ve kart tipi için nullable kapsam alanları ve `max_installments`. Çözümleme: o banka için eşleşen banka özel satır varsa bankasız genel limitlerin yerine geçer ve limiti yükseltebilir/düşürebilir. `category_id` yalnız bankasız kategori sınırlarında kullanılır; kategori sınırı tüm bankalarda geçerlidir ve banka özel satırla yükseltilemez. Etkin sınır, kalan banka/kart limitlerinin, kategori sınırının ve oran satırlarının minimumudur. Başlangıç değerleri yalnız örnektir ve dönem verisidir: Ödero genel 5, Chippin genel 1, Chippin/Akbank business 3, Klima 10, TV 4, telefon 3, business 2. Hiçbir limit kodda sabit tutulmaz.
- `profit_targets`: global veya ürün kapsamında yüzde/TL hedef; tanımsızsa referans fiyat üretilmez ve açık uyarı gösterilir.
- `product_categories`: `commission_group` (`klima`, `other`) ve `name_normalized` (unique). Klima kategori adıyla backfill edilir; TV ayrı grup değildir. Kategoriye özel taksit sınırı `commission_limits.category_id` ile verilir.
- `offers`: teklif numarası, müşteri, durum, ödeme tipi, kanal, banka (nullable), `bank_name_snapshot`, taksit, kart tipi, bayi indirimi, komisyon snapshot'ı ve `commission_source` (`bank_specific`, `general`, `none`), toplamlar, not ve `converted_reservation_id`.
- `offer_items`: ürün snapshot'ı, miktar, normal/Oliz/maliyet snapshot'ı, seçilen kampanya sürümü ve snapshot'ı, hediye var/yok, fiyat tabanı, önerilen ve nihai nakit/kart fiyatları, satır toplamları ve uyarı metni. Kampanya seçilirse Oliz kullanılmaz.
- `offer_history`: durum değişiklikleri; sunuldu/kabul/lost/expired sonrası fiyat snapshot'ı değişmez.

**Use-case akışları**

1. Banka: `EnsureBank` komisyon ve teklif formlarından çağrılır; ad `canonical_display_name` + normalize ile işlenir, mevcut kayıt varsa o döner, yoksa oluşturulur; seçim çağırana geri verilir.
2. Komisyon dönemi: yeni dönem aç, önceki ayı kopyala (bankasız genel satırlar dahil), matris ve limitleri düzenle, dönemi aktifleştir.
3. Komisyon çözümleme: kanal + banka + ürün grubu + taksit + kart tipi + Ödero bandına göre oran ve etkin üst sınır; önce bankaya özel satır, yoksa bankasız genel satır; seçilen taksit geçersizse veya hiç oran yoksa açık hata.
4. `CalculateReferencePrice`: `(maliyet + hedef kâr) / (1 - komisyon)`; `%0` ve tanımsız hedef kâr guard'ları; `Decimal`, iki hane `ROUND_HALF_UP`.
5. Teklif oluştur: müşteri/ödeme bilgisi, ürün ve miktarlar, satır bazında kampanya ve hediye seçimi; ürünün aktif kampanyası otomatik atanır, çalışan değiştirebilir veya kapatabilir; fiyat katmanlarını ve önerileri hesapla; manuel nakit/kart fiyatlarını al; toplamları kaydet. Banka boş bırakılabilir.
6. Teklif güncelle: yalnızca taslakta; satır ekle/çıkar ve fiyatları değiştir. Sunuldu ve sonrası fiyat snapshot'ı değişmez.
7. Durum geçişi: `draft → presented → accepted | lost | expired`; her geçiş history'ye yazılır.
8. A4: müşteri kopyasında maliyet, iç kâr ve komisyon detayı yok; ürün, miktar, birim/toplam fiyat, ödeme biçimi, banka (varsa)/taksit ve kampanya açıklaması bulunur.
9. `ConvertOfferToReservation`: kabul edilmiş teklif snapshot'ından rezervasyon üret; offer immutable kalır; retry aynı rezervasyonu döndürür.
10. Komisyon ayarları: dönem listesi, kanal sekmeleri, "Genel (tüm bankalar)" satırı, banka seçimi, matris, limitler, Ödero eşiği, kategori grup eşlemesi ve değişiklik geçmişi.
11. Teklif listesi araması yazarken otomatik çalışır; sonuçlar HTMX ile Ara butonuna basmadan güncellenir.

**Davranış testleri**

- 30.000 maliyet + 1.500 hedef kâr ve %5 komisyon → 33.157,89 TL.
- %0 komisyon → maliyet + hedef kâr; tanımsız hedef kâr açık uyarı.
- Örnek Banka POS 2 taksit %5, 3 taksit %6 (temsilî değerler).
- Bankasız genel oran %6 iken banka özel satırı olmayan her bankada %6 uygulanır; Örnek Banka B'ye %4 tanımlanırsa yalnız o banka %4 kullanır.
- Bankaya özel satırı olmayan taksit genel orana döner; hiçbiri yoksa açık Türkçe hata gösterilir.
- Ödero 20.000 TL altı/üstü farklı oran; eşik sepet toplamına uygulanır.
- Business kart max 2 ve TV kategorisi max 4 ayrı boyut olarak uygulanır; kategori sınırı bankaya bağlı değildir. Ödero genel limit 5 iken Ödero/Akbank 8 tanımlanırsa Akbank'ta 8, Ödero/Yapı Kredi 2 ise Yapı Kredi'de 2 geçerlidir; banka özel limit genel limiti geçersiz kılar, diğer bankaları etkilemez.
- Klima Ödero oranı bantsız tanımlanır ve 20.000 TL altı/üstü aynı oranı kullanır; Diğer grupta bant zorunludur.
- Chippin genel 1 taksit tüm bankalarda geçerlidir; Akbank business 3 limiti business kartta 3, diğer kartlarda 1 taksit verir. Limit sonraki dönem 2 yapıldığında kod değişmez.
- TV kategorisi 3 veya 9 yapılınca kod değişmez; kategori sınırları dönem verisidir.
- `AKBANK`/`akbank`/`AkbanK` tek banka kaydıdır ve `Akbank` görünür; hızlı ekleme mevcut kaydı döndürür.
- Banka seçilmemiş kart teklifi genel oranla hesaplanır; A4'te banka boş basılır ve eski teklif snapshot'ı değişmez.
- Kampanya seçilince Oliz uygulanmaz; iki kampanya birleşmez. Ürünün aktif kampanyası teklif satırına otomatik atanır; çalışan değiştirebilir.
- Teklif listesi araması yazarken otomatik çalışır; “Ara” butonuna basmadan sonuçlar güncellenir.
- 50.000 normal / 46.000 Oliz / 45.000 düğün örneğinde %10 bayi indirimi 40.500 TL önerir; çalışan 40.000 veya 36.000 girebilir ve floor uyarısı engellemez.
- Dönem/oran değişince eski teklif değişmez.
- Multi-item teklif ve müşteri A4 çıktısı maliyet/iç kâr sızdırmaz.
- Conversion retry duplicate rezervasyon oluşturmaz.

**Çıkış kriteri**

Bankasız genel ve bankaya özel oranlar aynı dönemde birlikte çalışır; banka adı yazım farkı kopya kayıt üretmez; kategori taksit sınırı kod değişmeden düzenlenebilir; komisyon dönemleri aylık yönetilir ve geçmiş korunur; teklifler fiyat/komisyon snapshot'ıyla bağımsızdır; örnek hesaplar ve limitler doğrudur; müşteri çıktısı iç veri içermez; kabul edilen teklif idempotent biçimde rezervasyona dönüşür.

### Milestone 5.1 — Teklif taksit karşılaştırma, silme ve bayi indirimi

**Kapsam ve kararlar**

- Teklif ekranında **tüm kanallar/bankalar ve taksitler** için komisyon, müşteri aylık taksiti, komisyon sonrası net, kampanya/Oliz hakedişi, maliyet, kâr/zarar ve marj gösterilecek. Çalışan + müşteri bu tablodan bir satır seçecek; teklif seçilen kanal/banka/taksit/kart tipiyle kaydedilecek.
- Karşılaştırma **bankasız genel oran** ve **bankaya özel** oranları birlikte gösterecek; bankaya özel satır genel satırı ezdiği için aynı banka/taksit için tek geçerli satır gösterilecek.
- Ödero 20.000 TL eşiği, Klima bant muafiyeti ve Chippin banka/kart bazlı limitleri mevcut domain kurallarıyla aynı hesaplanacak.
- Teklif silme eklenecek. **Tüm durumlardaki teklifler** (taslak, sunuldu, kabul, kaybedildi, geçersiz, rezervasyona dönüşmüş) onay verilerek silinebilecek; yanlışlıkla silmeyi önlemek için çift onay istenecek. Silme, teklif satırları ve durum geçmişini birlikte kaldıracak (hard delete). Rezervasyona dönüşmüş teklif silinirse bağlı rezervasyon **silinmez**; onay metni bunu açıkça söyler. Listede çoklu seçimle toplu silme P1 kapsamındadır.
- Kart ve nakit için **ayrı bayi indirimi yüzdeleri** teklif bazında düzenlenebilir olacak; ikisi de çalışan tarafından değiştirilebilecek. Yeni teklifte varsayılan `dealer_discount_settings` değerinden gelecek; mevcut `dealer_discount_percent` kart indirimi olarak korunacak, nakit için yeni alan eklenecek.

**Domain ve veri**

- Yeni saf hesaplayıcı: `build_installment_options` (veya `OfferComparison` value object'i). Girdi: kart satış toplamı, satır bazlı maliyet/kampanya/Oliz hakedişleri, kart tipi, kategori kimlikleri, aktif dönem oran/limitleri, banka listesi. Çıktı: kanal + banka + taksit başına `InstallmentOption`:
  - `channel`, `bank_id`/`bank_name` (bankasız için "Genel"), `installment_count`
  - `commission_percent`, `commission_source` (`general`/`bank_specific`)
  - `card_total`, `monthly_payment`, `net_after_commission`, `campaign_share`, `oliz_share`, `total_revenue`, `cost`, `profit`, `margin_percent`, `is_available`, `unavailable_reason`
- Hesaplama mevcut `matching_commission_rate`, `commission_percent_for`, `effective_max_installments` fonksiyonlarını kullanacak; dönem oran/limitleri bir kez yüklenip tüm banka/taksit kombinasyonları için tekrar tekrar sorgulanmayacak.
- **Komisyon matrahı kart satış toplamıdır (#4).** Ödero 20.000 TL bandı `card_total` üzerinden seçilecek; nakit için komisyon yok. Kart birim fiyatı girilmemişse önerilen kart fiyatı geçici matrah olacak ve nihai fiyat girilince yeniden hesaplanacak.
- Çok ürünlü teklifte komisyon oranı tüm satırlara aynı uygulanacak; kâr/zarar satır bazında hesaplanıp toplam gösterilecek. Kategori taksit sınırı, teklifteki tüm kategorilerin en kısıtlayıcısı olacak.
- Karşılaştırma **kalıcı snapshot değildir**; aktif dönemden canlı hesaplanır. Seçilen seçenek mevcut `commission_percent_snapshot`, `commission_period_*`, `bank_name_snapshot` ve `commission_options_snapshot` alanlarına yazılır; eski teklifler dönem değişince değişmez.
- Yeni migration (`0015_offer_card_cash_discounts`) gerekir: teklif ve teklif satırlarına nakit bayi indirimi alanı; mevcut `dealer_discount_percent` kart indirimi olarak korunur ve nakit alanı mevcut değerle backfill edilir. Silme için repository `delete(offer_id)` metodu ve application use-case eklenir (satır/geçmiş FK'ları zaten CASCADE).

**Use-case ve akışlar**

1. `BuildOfferComparison`: teklif formundaki güncel ürün/fiyat/indirim/kart tipi girdisini (kaydetmeden) alır; kanal/banka/taksit tablosunu döndürür. Formda **"Taksit Seçeneklerini Gör"** butonu bu use-case'i HTMX ile çağırır.
2. Formdaki karşılaştırma tablosunda her satırda **"Seç"** butonu bulunur; seçim, formdaki gizli/mevcut `channel`, `bank_id`, `installment_count`, `card_type` alanlarını doldurur. Kaydetme yine kullanıcının **Teklif Oluştur/Kaydet** eylemiyle olur.
3. Teklif detayında da aynı tablo **"Taksit Seçenekleri"** kartı olarak gösterilir. Taslak teklifte satır seçimi `SelectOfferPaymentOption` command'i ile banka/taksit/kart tipi ve komisyon snapshot'ını günceller; sunulmuş/kabul edilmiş teklifte seçim yapılamaz.
4. Detay seçimi yalnızca taslakta çalışır; komisyon yeniden çözülür, snapshot ve seçili toplam güncellenir. Durum geçmişi değişmez; istenirse ayrı bir "seçenek değişti" audit kaydı sonraki adımda eklenir.
5. `DeleteOffer`: tüm durumlardaki teklifi siler; çift onay zorunludur. `converted_reservation_id` doluysa onay metni bağlı rezervasyonun silinmeyeceğini söyler ve yalnız teklif kaydı kaldırılır. Detay ve listede **Sil** eylemi; P1'de listede çoklu seçim + toplu silme. Başarıda listeye `msg=deleted` (toplu silmede silinen sayısı) ile dönülür.
6. Bayi indirimi: iki ayrı `type=number`, `min=0`, `max=100`, `step=0.01`, yüzde işaretli input — **Kart Bayi İndirimi** ve **Nakit Bayi İndirimi**. İkisi de çalışan tarafından değiştirilebilir; yeni teklifte varsayılan ayardan, düzenlemede mevcut değerden gelir. Değişiklik anında önerilen kart/nakit fiyatları ve kâr önizlemesi güncellenir; sunucu 0–100 doğrulaması yapar ve değerleri teklif/satır snapshot'ına yazar.

**UI**

- Teklif formunda **Kart Bayi İndirimi (%)** ve **Nakit Bayi İndirimi (%)** yan yana, ikisi de düzenlenebilir; ürün/fiyatların altında **"Taksit Seçeneklerini Gör"** butonu ve açılan karşılaştırma paneli: Ödeme, Kanal, Banka, Taksit, Aylık Taksit, Komisyon, Komisyon Sonrası, Kampanya, Oliz, Maliyet, Kâr/Zarar, Marj, Seç.
- Karşılaştırma panelinin başında **Nakit** satırı (komisyonsuz, nakit indirimiyle) yer alır; altında kart banka/taksit satırları gelir. Nakit satırı seçilirse ödeme tipi nakit olur.
- Panelde kanal filtresi (POS / Ödero / Chippin / Tümü), kart tipi filtresi (Bireysel / Business) ve "yalnız kârlı" / "en yüksek kâr" sıralaması. Bankasız genel satır "Genel (tüm bankalar)" etiketiyle.
- Eksik maliyetli satırlarda kâr "—" ve sarı uyarı; negatif kâr kırmızı. Limit/oran olmayan kombinasyonlar tabloya ya hiç eklenmez ya da "kullanılamaz" nedeniyle soluk gösterilir.
- Teklif detayında aynı tablo; seçili satır vurgulu, taslak dışında seçim butonları pasif.
- Teklif listesinde satır işlemlerine **Sil** eklenir; detayda da "Teklifi Sil" butonu. Tüm durumlarda görünür; çift onay modalı kullanılır. Rezervasyona dönüşmüş teklifte modal "bağlı rezervasyon silinmez" uyarısı verir. P1'de liste satırlarında checkbox ve toplu silme çubuğu eklenir.
- Mobilde tablo yatay kaydırılır; seçim butonu sticky sağ kolonda kalır.

**Davranış testleri**

- 3 banka + bankasız genel oranla karşılaştırma üretilir; her satırın komisyon, aylık taksit, net, kâr ve marjı beklenen değerlerle eşleşir.
- Bankaya özel oran genel oranı aynı banka/taksitte ezer; diğer bankalarda genel oran görünür.
- Ödero 20.000 TL eşiği kart toplamına göre uygulanır; Klima'da bant kullanılmaz; Chippin banka/kart limiti doğru yansır.
- Çok ürünlü teklifte toplam kâr satır kârlarının toplamıdır; eksik maliyet varsa toplam kâr/marj "eksik" uyarısı verir.
- Seçilen seçenek form alanlarını doldurur ve kaydedilen teklifin snapshot'ı seçilen banka/taksit/oranla oluşur.
- Detayda seçenek değişimi yalnız taslakta çalışır; sunulmuş teklif reddedilir; eski snapshot değişmez.
- Her durumdaki teklif (taslak, sunuldu, kabul, kaybedildi, geçersiz, rezervasyonlu) çift onayla silinir; satır/geçmiş kaybolur. Rezervasyona dönüşmüş teklif silinince bağlı rezervasyon korunur. Toplu silmede seçilenlerin sayısı doğru raporlanır.
- Kart ve nakit indirimi varsayılan ayardan gelir; ikisi ayrı ayrı %10 ve %15 gibi farklı değerlere çekilir, kaydedilir ve teklif detayında/snapshot'ta görünür; %101 reddedilir.
- Nakit satırı komisyonsuz kâr/zararı, kart satırları komisyon düşülmüş kâr/zararı gösterir; kart/nakit indirimleri birbirini etkilemez.
- Formdaki "Taksit Seçeneklerini Gör" kayıt oluşturmadan tablo döndürür; seçim yapılmadan teklif kaydedilirse mevcut davranış korunur.

**Kararlar**

1. **Silme:** Tüm durumlardaki teklifler çift onayla silinebilir; rezervasyona dönüşmüş teklif silinirse bağlı rezervasyon korunur. Listede P1 toplu silme. *(Kapandı.)*
2. **Karşılaştırma:** Kanal sekmeleri (POS / Ödero / Chippin) + "Tümü" filtresi; bankasız genel satır ve nakit seçeneği dahil. *(Kapandı.)*
3. **Komisyon matrahı:** Kart komisyonu **#4 kart satış toplamı** üzerinden hesaplanır; nakit için komisyon yoktur. *(Kapandı.)*
4. **Seçenek değişikliği audit'i:** İlk teklif kaydında seçim yapılacağı ve snapshot yeterli olacağı için ayrı audit kaydı yok. *(Kapandı.)*
5. **Karşılaştırma yeri:** Formda "Taksit Seçeneklerini Gör" (kaydetmeden) + detayda aynı tablo ile taslak güncelleme. *(Kapandı.)*
6. **Kart/nakit bayi indirimi:** İki ayrı yüzde alanı; ikisi de çalışan tarafından değiştirilebilir. *(Kapandı.)*

**Fiyat katmanları**

1. **Perakende:** `regular_price`.
2. **Şirket indirimi / Oliz:** `website_discounted_price`. Kampanya seçilirse kampanya fiyatı bunun yerine geçer.
3. **Maliyet / bayinin alışı:** `cost_price`.
4. **Kart son fiyatı:** `unit_price_card` (çalışan girer; boşsa kart indiriminden önerilen fiyat).
5. **Nakit son fiyatı:** `unit_price_cash` (çalışan girer; boşsa nakit indiriminden önerilen fiyat).

`base_total` = (kampanya varsa kampanya, yoksa Oliz, yoksa perakende) x adet. Yani **#2'dir**; bayi indirimi ve #4/#5 son fiyatları değildir. Müşterinin karttan ödediği tutar `card_total` (#4), nakit ödediği tutar `cash_total` (#5)'tir.

**Komisyon matrahı: kart satış toplamı (#4)**

Kart komisyonu `card_total = sum(unit_price_card x quantity)` üzerinden çözülür. Ödero 20.000 TL bandı bu toplamdan seçilir. Nakit için komisyon olmadığından bant yalnız kart/Ödero hesabında kullanılır.

Örnek (oranlar temsilî):

- Ödero bandı: 20.000 TL altı %4, 20.000 TL ve üzeri %5.
- `base_total` (#2) = 21.000 TL; kart bayi indirimi %10 -> müşterinin ödediği #4 = **18.900 TL**.
- Doğru hesap: #4 = 18.900 -> **%4** bant -> 18.900 x %4 = **756 TL komisyon**, net **18.144 TL**.
- Eski `base_total` hesabı: 21.000 -> %5 bant -> 18.900 x %5 = **945 TL komisyon**, net **17.955 TL**.
- Fark: **189 TL**; eski akış komisyonu fazla kesip kârı düşük gösterir.

Kart fiyatı henüz girilmemişse önerilen kart fiyatı geçici matrah olur; çalışan nihai kart fiyatını girince bant ve komisyon yeniden hesaplanır. Çok ürünlü teklifte bant toplam `card_total` üzerinden uygulanır.

**Kart/nakit bayi indirimi**

- **Kart bayi indirimi:** mevcut `dealer_discount_percent` alanı bu anlamda korunur (gerekirse yeniden adlandırılır). Önerilen kart fiyatı: `base_price x (1 - kart_indirimi / 100)`.
- **Nakit bayi indirimi:** yeni `dealer_discount_cash_percent` alanı. Önerilen nakit fiyatı: `base_price x (1 - nakit_indirimi / 100)`.
- İki oran da formda ayrı input olarak çalışan tarafından değiştirilebilir; 0–100 aralığında doğrulanır. Yeni teklifte ikisi de `dealer_discount_settings` varsayılanından gelir; düzenlemede teklifteki değerler kullanılır.
- Çalışan nihai kart/nakit birim fiyatlarını ayrıca elle değiştirebilir; elle girilen fiyat öneriyi ezer. Kâr/zarar her zaman **nihai fiyat** üzerinden hesaplanır:
  - Kart: `card_total - komisyon + kampanya/Oliz hakedişi - maliyet`
  - Nakit: `cash_total + kampanya/Oliz hakedişi - maliyet`
- Kampanya fiyatı şirket tabanı olarak kullanılır; bayi indirimi kampanya fiyatına **bir kez** uygulanır. Kampanya hesabında bayi indiriminin ikinci kez uygulanması engellenir ve testle doğrulanır.
- Migration `0015_offer_card_cash_discounts`: teklif ve teklif satırlarına nakit indirimi alanı eklenir; mevcut tekliflerde nakit alanı mevcut kart indirimiyle backfill edilir. Eski teklif snapshot'ları değişmez.

**Çıkış kriteri**

Nakit ve tüm kanal/banka/taksit kombinasyonları kâr-zararla görülebilir; kart komisyonu kart satış toplamından hesaplanır; kart ve nakit bayi indirimleri ayrı ayrı düzenlenip doğrulanır; seçilen seçenek teklife snapshot'lanır; her durumdaki teklif onayla silinebilir; eski teklifler dönem/oran değişiminden etkilenmez.

### Milestone 5.2 — Teklif kâr/zarar doğruluğu, senaryo tablosu ve canlı taksit karşılaştırma

**Durum:** Faz 0 (sıfır Oliz temizliği + kampanya oranı düzeltmesi) ve Faz 1 (v2 fiyat motoru, senaryo özeti, canlı taksit tablosu, sepet toplamları ve kampanya rozetleri) uygulandı. Migration `0017_offer_pricing_v2` çalıştırıldı.

**Sorun**

- Ürünün Oliz fiyatı `0.00` ise kod bunu “Oliz fiyatı var” kabul ediyor. `base_price` sıfıra düşüyor ve kâra `(normal - 0) x %85` “Oliz hakedişi” ekleniyor. 10121 örneğinde bu, satış fiyatı ne olursa olsun yaklaşık `33.999 TL` hayali gelir ve tamamen yanlış kâr/zarar demektir. Aynı sorun veritabanındaki 1.470 üründe vardır.
- Kampanya fiyatı `campaign_scenarios` içinde kampanyanın kendi yüzdesi yerine bayi indirimi oranını kullanıyordu; bu düzeltildi. Doğru sıra: 40.000 → %10 kampanya → 36.000 → %10 bayi → 32.400.
- Kampanya hakedişi nihai satış fiyatı üzerinden hesaplanıyor; kampanya indirim tutarı üzerinden hesaplanmalı. Bayi indirimi hakediş üretmez.
- Teklif formunda sepet toplamları, normal/Oliz toplamı ve kampanya etkisi görünmüyor; taksit tablosu yalnız “Gör”e basılınca ve yalnız bir kez hesaplanıyor.

**Kararlar**

1. **Sıfır Oliz yoktur.** `website_discounted_price` ve `website_price_snapshot` için `0` değeri `NULL` kabul edilir; veri temizlenir ve yeni kayıtlarda sıfır kabul edilmez. Oliz yoksa Oliz hakedişi gösterilmez; kâr normal fiyat üzerinden bayi indirimiyle hesaplanır.
2. **İndirim sırası:** normal fiyat -> şirket indirimi (kampanya veya Oliz) -> bayi indirimi -> varsa elle girilen nihai fiyat. Kampanya ve bayi indirimi üst üste uygulanır: `40.000 -> düğün %10 -> 36.000 -> bayi %10 -> 32.400`.
3. **Şirket indirimi seçimi:** kampanya varsa ve Oliz de varsa, normal fiyattan en yüksek indirimi veren kaynak seçilir (`normal - kampanya fiyatı` ile `normal - Oliz` karşılaştırılır). Çalışan belirli bir kampanyayı seçerse o kampanya kullanılır; “Kampanya yok” seçilirse yalnız Oliz değerlendirilir.
4. **Hakediş:** seçilen şirket indiriminin `%85`’i bayi geliridir. Kampanya seçildiyse kampanya indirim tutarının, Oliz seçildiyse `normal - Oliz` farkının `%85`’i; ikisi aynı anda ödenmez. Hakediş, bayi indiriminden veya elle girilen fiyattan bağımsızdır; bu indirimleri bayi kendi marjından yapar.
5. **Kâr/zarar:** nakit için `satış + hakediş - maliyet`; kart için `satış x (1 - komisyon/100) + hakediş - maliyet`. Marj, gelir (komisyon sonrası satış + hakediş) üzerinden hesaplanır. Maliyet yoksa kâr/marj gösterilmez.
6. **Senaryolar:** normal fiyat, bayi indirimi, Oliz (varsa), kampanya, kampanya + bayi indirimi ve elle girilen fiyat ayrı senaryolar olarak gösterilir. Üstte senaryo özeti, altta seçili teklifin tüm nakit/kart/kanal/banka/taksit detayı yer alır.
7. **Canlı güncelleme:** taksit tablosu formun en üstünde, “Gör” butonu olmadan; bayi indirimi, ürün, miktar, kampanya veya ödeme alanı değiştiğinde otomatik yenilenir. Seçim tablodan yapılır ve form alanlarını doldurur.
8. **Sepet:** her satırda normal fiyat, Oliz (varsa), seçilen kampanya adı ve etkisi (“Düğün: normal fiyattan %10 indirim -> 36.000 TL”), maliyet, önerilen/nihai nakit-kart fiyatı görünür. Sepet altında toplam normal, toplam Oliz, toplam şirket indirimi, toplam maliyet, nakit/kart toplamı ve kâr/zarar özeti bulunur.
9. **Toplu alım/bedava ürün** kampanyaları bu adımda yalnız bilgi/rozet olarak gösterilir; adet bazında otomatik fiyatlama kapsam dışıdır.

**Fiyat modeli (v2)**

Her teklif satırı için:

- `N` normal fiyat, `O` Oliz fiyatı (`NULL` olabilir), `C` maliyet, `Q` adet.
- Kampanya fiyatı `P_k`: kampanya tabanı (normal/Oliz/elle) üzerinden kampanyanın kendi `discount_value` değeri uygulanır. Yüzde kampanyasında bayi indirimi burada **uygulanmaz**.
- Oliz fiyatı `P_o = O`; Oliz indirimi `N - O`.
- Seçilen şirket fiyatı `P`: otomatik modda `max(N - P_k, N - P_o)`; açık kampanya seçiminde `P_k`; “Kampanya yok”ta `O` varsa `P_o`, yoksa `N`.
- Bayi indirimi: nakit `S_cash = P x (1 - nakit_indirimi/100)`, kart `S_card = P x (1 - kart_indirimi/100)`. Elle girilen nihai fiyat `S`’yi ezer.
- Hakediş `H`: kampanya seçildiyse `kampanya_indirim_tutarı x 85 / 100`; Oliz seçildiyse `(N - O) x 85 / 100`; yoksa `0`.
- Kâr: nakit `S_cash + H - C`; kart `S_card x (1 - komisyon/100) + H - C`.

**10121 örneği (maliyet 32.077,86 TL, Oliz yok)**

- Kampanyasız, kart bayi indirimi %10: satış 35.999,10; 2 taksit %5 komisyonda net 34.199,15; hakediş 0; kâr **2.121,29 TL**.
- Düğün %10: kampanya fiyatı 35.999,10; hakediş 3.399,92. Bayi %10 sonrası satış 32.399,19; 2 taksit %5’te net 30.779,23 + 3.399,92 = 34.179,15; kâr **2.101,29 TL**.
- Düğün + bayi %10 + elle 32.000: hakediş 3.399,92; 2 taksit %5’te net 30.400 + 3.399,92 = 33.799,92; kâr **1.722,06 TL**.
- Kampanyasız + elle 32.000: hakediş 0; 2 taksit %5’te 30.400 - 32.077,86 = **-1.677,86 TL**.

Not: 10121’in normal fiyatı 39.999 TL olduğu için 40.000’lik örnekteki 32.400 yerine 32.399,19 çıkar. Yukarıdaki hakedişler yalnız kampanya indiriminden hesaplanır; bayi indirimi hakediş üretmez.

**UI**

- Form sırası: müşteri/not -> ödeme ve indirimler -> **Taksit Seçenekleri** (senaryo özeti + detay tablo) -> sepet -> ürün ekle -> kaydet.
- Taksit tablosu `hx-post="/offers/compare"` ile `change`/`input delay` tetiklenir; ilk açılışta sunucu tarafında hesaplanıp render edilir. Tablo boş sepet için “Ürün ekleyin” durumunu gösterir.
- Senaryo özeti bilgi amaçlıdır; detay tablo seçili teklifi gösterir. Detay tabloda “Seç” butonu ödeme alanlarını doldurur. Senaryo satırını teklife dönüştürme (manuel fiyatı doldurma) sonraki adımdadır.
- Sepette kampanya rozeti: kampanya adı, indirim türü/değeri ve hesaplanan kampanya fiyatı. Sabit indirim, özel fiyat, hediye ve bilgi kampanyaları aynı rozet dilini kullanır; bedava ürün yalnız açıklama olarak gösterilir.
- Oliz fiyatı olmayan tekliflerde Oliz kolonu/hakediş satırı gösterilmez; karışık sepette yalnız Oliz’i olan satırlarda değer bulunur.

**Veri ve migration**

- **Faz 0 (uygulandı) `0016_normalize_zero_oliz_prices`:**
  - `products.website_discounted_price = 0` -> `NULL`; `offer_items.website_price_snapshot = 0` -> `NULL`.
  - Temizlenen her ürün için `product_price_history` kaydı (`source='other'`).
  - `products.website_discounted_price` ve `offer_items.website_price_snapshot` için `> 0 OR NULL` check constraint.
- **Faz 1 (uygulandı) `0017_offer_pricing_v2`:**
  - `offers.pricing_version` (`legacy`/`v2`, yeni teklifler `v2`).
  - `offer_items.company_discount_source` (`campaign`/`oliz`/`none`), `company_discount_amount`, `company_share_amount`, `campaign_discount_amount`, `campaign_base_price`, `campaign_price`.
  - Teklif toplamları `regular_total`, `oliz_total`, `company_discount_total` ve `cost_total`.
- Eski teklifler `legacy` olarak okunur; yeni hesaplama yalnız `v2` snapshot’larında kullanılır. Eski snapshot satırları geriye dönük değiştirilmez.
- Ürün oluşturma/güncelleme, içe aktarma ve teklif hazırlama katmanlarında `0` Oliz değeri `None`’a normalize edilir. Ürün formu ve Excel içe aktarma `0` değerini “Oliz yok” olarak kabul eder.

**Use-case ve domain**

- Yeni saf domain modülü: `bayios.domain.offers.pricing` (veya mevcut `offers` içinde ayrı fonksiyonlar):
  - `company_price_candidates(...)`
  - `select_company_price(...)`
  - `quote_offer_item_v2(...)`
  - `profit_for_option(...)`
  - `build_scenarios(...)`
- `preview_offer_comparison` senaryoları ve tüm taksitleri tek geçişte üretir; `build_offer_line_analyses` v2 snapshot’larından okur.
- `create_offer`/`update_offer` v2 snapshot alanlarını yazar; toplamlar `regular_total`, `oliz_total`, `company_discount_total` ve `cost_total` olarak teklifte saklanır (mevcut `cash_total`, `card_total`, `selected_total` korunur).

**Testler**

- `OfferPriceLayers(website_price=0)` -> `base_price` normal fiyat; Oliz hakedişi 0.
- 10121 senaryo tablosu yukarıdaki dört sayıyı üretir; kampanyasız elle 32.000’de kâr negatiftir.
- `%10 kampanya + %10 bayi` -> 32.400; kampanya hakedişi 4.000 x %85 = 3.400; bayi indirimi hakediş üretmez.
- Kampanya ve Oliz birlikteyken otomatik seçim en yüksek indirimi seçer; açık kampanya seçimi override eder.
- Sıfır Oliz içeren ürün içe aktarma ve ürün kaydı `NULL` üretir; migration sonrası 1.470 ürün temizlenir.
- Karşılaştırma tablosu bayi indirimi değişince yenilenir; formda toplam normal/Oliz/maliyet/kâr görünür.
- Sepette kampanya adı ve etkisi görünür; Oliz yoksa Oliz kolonu gizlenir.
- Eski `legacy` teklifin snapshot’ı ve görünen değerleri değişmez.

**Çıkış kriteri**

10121 gibi Oliz’siz ürünlerde kâr/zarar yalnız gerçek indirim sonrası satış, komisyon ve varsa gerçek hakediş üzerinden hesaplanır; kampanya + bayi indirimi sırası doğrudur; tüm taksit ve senaryolar tek ekranda canlı görünür; sıfır Oliz verisi temizlenmiştir; eski teklif snapshot’ları korunur.

### Milestone 6 — Scraper ürün ID'si, JSON detayları ve çoklu import ID desteği

**Kapsam ve kararlar**

- Dış scraper çıktısı içe aktarılır; uygulama içinde scraping yapılmaz.
- Ürün kimliği: iç UUID korunur; scraper ID'si `products.external_id` alanındadır.
- `product_external_id_history` eski ID'leri alias olarak saklar. Ürün kataloğu yeni ID getirdiğinde `external_id` doğrudan güncellenir, eski ID alias'a yazılır; boş ID mevcut değeri korur.
- Teklif/rezervasyon/kampanya importları ID'yi yalnızca çözer (güncel veya alias); ID dolu ama bulunamazsa hata verir, ada göre fallback yapmaz. ID boşsa adla legacy eşleşir; aynı ad birden fazlaysa ID istenir.
- Ürün adı tekilliği kaldırıldı; manuel ekleme/düzenleme formundaki çift-ad koruması devam eder.
- `products.details` JSONB: `features[]` ve `specifications[]`; `source_url`, `kind` (`product`/`warranty`/`explicit`), `scraped_at` saklanır.
- Excel/CSV 9/10/11/12 sütunlu dosyaları destekler; 11. sütun JSON detayıdır, 12. sütun `scraped_at`. `catalog.json` schema_version `1.0` aynı preview/commit modeline dönüşür.
- Boş JSON hücresi mevcut detayı korur; boş listeler temizler; bozuk JSON'da ürün alanları güncellenir, detay korunur ve hata raporlanır.
- Normal fiyat boş/0 ise korunur; Oliz boş/0/null ise silinir. `catalog.json`'da `discounted_price: null` da Oliz'i siler.
- Ürün detayında ID, tür, kaynak URL, scraper tarihi, öne çıkan özellikler ve teknik özellikler gösterilir; arama ad veya ID ile çalışır.
- Import önizlemesi ID, tür ve detay özetini gösterir; `.json` yükleme aynı ekrandan yapılır.

**Veri ve migration**

- `0018_scraper_product_details`: `external_id`, `details`, `source_url`, `kind`, `scraped_at`; `name_normalized` unique kaldırılır; `external_id` unique index; `product_external_id_history`; `product_import_batches.file_type` `json`; `product_price_history.source` `scraper_import`.

**Testler**

- 9/10/11/12 sütunlu CSV/XLSX; başlıksız dosya hatası.
- `catalog.json` parse ve şema kontrolü.
- ID güncelleme + eski ID alias; aynı ID tekrarında ilk kayıt.
- ID'siz garanti satırı ada göre eşleşme/oluşturma.
- Boş JSON koruma, boş liste temizleme, bozuk JSON kısmi güncelleme.
- Teklif/rezervasyon/kampanya importlarında ID-öncelikli eşleşme, legacy ad eşleşmesi ve ID bulunamadı hatası.
- Ürün detayında özellikler/teknik özellikler/kaynak gösterimi.

**Çıkış kriteri**

Scraper Excel/CSV ve catalog.json aynı ürün modeline düşer; yeni ID eski ürünü günceller ve eski ID alias olarak korunur; teklif/rezervasyonlar güncel ID'yi gösterir; detaylar JSONB'de saklanır ve ürün ekranında görünür; eski 9/10 sütunlu dosyalar çalışmaya devam eder.

### Cross-milestone — Ayarlar (banka ve kategori ana verisi)

**Kapsam**

`Ayarlar` navigasyonu banka ve kategori ana verisini tek yerden yönetir. Banka/kategori hızlı ekleme bağlama duyarlı formlarda (komisyon, teklif, ürün detayı) kalabilir; stok sayfasındaki ayrı kategori ekleme modalı kaldırılır.

**Use-case akışları**

1. Banka listesi: arama, tekli/toplu ekleme (önizlemeli), yeniden adlandırma, pasifleştirme/aktifleştirme, birleştirme, kullanılmayan bankayı çift onaylı silme. Oran/limitlerde kullanılan banka, bağlı oran/limit satırları da silinerek çift onayla silinebilir; tekliflerde kullanılan banka silinemez.
2. Kategori listesi: arama, tekli/toplu ekleme (önizlemeli), yeniden adlandırma, komisyon grubu değiştirme, birleştirme, yalnız kullanılmayan kategoriyi çift onaylı silme.
3. Banka/kategori Excel içe/dışa aktarma; banka `Banka, Aktif`, kategori `Kategori, Komisyon Grubu`.
4. Banka birleştirme: oran ve limitler hedefe taşınır (çakışan satırlar hedefte varsa kaynak satır atlanır), tekliflerin `bank_id` değeri hedefe çevrilir, `bank_name_snapshot` korunur, kaynak banka silinir.
5. Kategori birleştirme: ürünler hedef kategoriye taşınır, kategori limitleri hedefe taşınır (çakışan limit atlanır), kaynak kategori silinir.
6. Kullanım sayıları: banka için oran/limit/teklif, kategori için ürün/limit. Kullanımdaki kayıt silinemez; pasifleştirme veya birleştirme önerilir.
7. Komisyon Excel importu bilinmeyen bankayı önizlemede "yeni" gösterip oluşturur (varsayılan açık). Teklif Excel importu aynı davranışı yalnız kullanıcı onay kutusuyla yapar (varsayılan kapalı).

**Davranış testleri**

- `AKBANK`/`akbank`/`AkbanK` aynı banka kaydına düşer; görünen ad `Akbank`.
- Toplu ekleme önizlemesi yeni/mevcut/hatalı satırları ayırır; hatalı satır varken commit engellenir.
- Kullanılmayan banka/kategori çift onayla silinir. Oran/limitlerde kullanılan banka bağlı satırlarla silinebilir; tekliflerde kullanılan banka ve kullanımdaki kategori silinemez.
- Banka birleştirme oran/limit/teklif referanslarını hedefe taşır; eski teklif banka adı değişmez.
- Kategori birleştirme ürünleri ve limitleri hedefe taşır; çakışan limit kaynakta atlanır.
- Excel banka/kategori roundtrip'i oluşturur/güncelleştirir.
- Komisyon importu yeni bankayı oluşturur; teklif importu bayrak kapalıyken hata verir, açıkken oluşturur.

**Çıkış kriteri**

Banka ve kategori ana verisi tek ekrandan toplu yönetilir; kullanımdaki kayıtlar silinmez; birleştirme referansları korur; Excel içe/dışa aktarma ve import davranışları testlerle doğrulanır.

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

## V2 adayları (v1 dışı)

### Hızlı Teslim / Code 128 (v2 adayı)

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
