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
- satılabilir stok ve temin ihtiyacını hesaplama;
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

### Milestone 1 — Product catalog ve import

**Domain ve veri**

- Product aggregate: `name`, `name_normalized`, prices, cost, physical quantity, category, active/archive metadata.
- Price history, import batch, import rows/decisions ve stock movements migration'ları.
- `name_normalized` unique index; Unicode NFKC, trim, whitespace collapse ve Türkçe I/İ/ı/i kuralları tek saf normalizer'da.

**Use-case akışları**

1. `SearchProducts`: exact normalized search semantics ve baştaki sıfırları koruyan arama.
2. `PreviewProductImport`: `utf-8-sig`, cp1254 fallback, comma/semicolon CSV ve `.xlsx`; header mapping; row classification.
3. `CommitProductImport`: staging kararlarını validate et, stale batch conflict kontrol et, tek transaction'da upsert/history/movement yaz.
4. `ExportProducts`: tüm ürünleri explicit field mapping ile CSV/XLSX çıkar; filtreli export MVP dışıdır.

Boş `quantity` mevcut değeri korur, `0` sıfırlar. Boş `website_discounted_price` mevcut değeri korur; temizleme yalnızca explicit decision ile yapılır. Kaynakta olmayan ürün silinmez/arşivlenmez.

**HTTP/UI**

- `/products`, `/products/{id}`, `/imports/products/preview`, `/imports/products/commit` page/API çiftleri.
- Preview ekranı conflict/error/update/skip/clear kararlarını satır bazında ve toplu gösterecek.
- Commit sonrası özet ve değişen fiyat/stok geçmişi açık success/error feedback ile gösterilecek.

**Davranış testleri**

- `07325 A` aynı ürünü bulur; `07325A` ayrı üründür.
- Aynı ürün tekrar import edilince duplicate oluşmaz.
- Fiyat değişince history, değişmeyince gereksiz history oluşmaz.
- Boş quantity korunur; zero quantity movement üretir.
- Hatalı satır valid satırları sessizce bozmaz.
- Preview sonrası ürün değişmişse commit stale conflict döner; aynı commit retry duplicate yaratmaz.

**Çıkış kriteri**

Örnek CSV/XLSX preview'da tüm kararları görünür; onay olmadan DB değişmez; commit atomiktir; ürün/fiyat/stok geçmişi geriye dönük okunur.

### Milestone 2 — Reservation ve A4

**Domain ve veri**

- Reservation aggregate; reservation item; item event ve reminder history tabloları.
- `quantity`, `delivered_quantity`, `cancelled_quantity` gerçek miktar alanlarıdır.
- `status` yalnızca geçerli operasyon state'lerini temsil eder; `delivered + cancelled <= quantity` her write'ta korunur.

**Use-case akışları**

1. Reservation create: fiziksel stok düşmeden open reservation artır.
2. Item event: `RESERVED → DELIVERY_REQUESTED → DEPOT_READY → SERVICE_ASSIGNED`; servis tarihi/notları taşı.
3. Deliver: kalan miktarı doğrula, düşük stokta açık uyarı ve gerekçe iste, movement + event + idempotency'yi atomik yaz.
4. Cancel: açık miktarı azalt, fiziksel stoktan çıkış yapma.
5. Remind/snooze: 13 aylık default ve 1 aylık snooze tarihçesi.
6. Print: depot ve dealer copy ayrı başlıklarla, `@media print` ile A4.

**Davranış testleri**

- Başlangıç fiziksel 5 iken 2 reservation sonrası physical 5, open 2, sellable 3.
- Delivery requested/depot ready/service assigned physical stock'u değiştirmez.
- 1 teslim sonrası physical 4, open 1 olur; kalan teslim sonrası physical 3, open 0 olur.
- Aynı idempotency key veya aynı teslim command retry'si ikinci movement üretmez.
- Kısmi teslim ve çok ürünlü reservation diğer açık satırları bozmaz.
- A4 depot/dealer çıktıları müşteri/ürün/miktar bilgilerini taşır.

**Çıkış kriteri**

Bir reservation uçtan uca takip edilir; duplicate stock deduction mümkün değildir; çıktı siyah-beyaz A4'te okunur.

### Milestone 3 — Stock count ve özet

**Use-case akışları**

- Product detail ve stock listesi physical/open/sellable/temin ihtiyacı query'sini aynı hesap policy'sinden alır.
- Category ile count session açılır; sistem quantity snapshot'lanır.
- Counted quantity girilir; difference kullanıcıya gösterilmeden complete edilemez.
- Completion sırasında current stock version kontrol edilir; conflict varsa yeniden hesaplama/review istenir.
- Farklar stock adjustment movement olarak ledger'a yazılır; movement silinmez.

**Davranış testleri**

- Sellable negatif gösterilmez; temin ihtiyacı pozitif görünür.
- CSV, delivery ve count movement türleri ayrıştırılır.
- Eşzamanlı movement sonrası eski count sessizce overwrite etmez.
- Completed session tekrar complete edilince duplicate movement üretmez.
- A4 kategori listesi elle yazılabilir alanları içerir.

**Çıkış kriteri**

Kategori sayımı uygulamaya işlenir, fark ve actor/time history görünür, movement geçmişi denetlenebilir.

### Milestone 4 — Campaign ve dealer price guide

**MVP sınırı**

Campaign modeli basit ve ürün ilişkili rehberdir: ad, açıklama, geçerlilik, active/history, şart ürünleri, fayda ürünleri, indirim türü/oranı/tutarı, fiyat tabanı ve hediye notu. Ürün bazlı “A alınca B indirimli” gibi ilişkiler saklanabilir.

Genel rule engine, optimal sepet seçimi, WMS/POS entegrasyonu ve otomatik satış fiyatı uygulaması yapılmaz. Çalışan campaign'i rehberden seçer ve Offer snapshot'ına alır.

**Davranış testleri**

- Tarih dışı campaign active listede görünmez, history filtresinde görünür.
- Normal 25.999, Oliz 23.999 ve %10 örneği hediye var/yok senaryolarını doğru gösterir.
- %10 yalnızca default öneridir; çalışan %15 girebilir.
- Campaign değişince eski Offer snapshot'ı değişmez.
- Ürün özel nakit/kart minimumları genel oranla karışmaz.

**Çıkış kriteri**

Çalışan aylık ürün campaign'lerini anlaşılır rehber olarak görür, senaryo seçimini Offer'a kaydeder; otomatik POS iddiası oluşmaz.

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

