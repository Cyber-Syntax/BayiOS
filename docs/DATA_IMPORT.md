# BayiOS Excel İçe/Dışa Aktarma Başvurusu

Bu belge, BayiOS'ta kullanılan Excel/CSV kolonlarını ve içe aktarma davranışlarını özetler.
Kullanıcıya gösterilen tüm metinler Türkçedir; teknik hata ayrıntıları loglara gider.

## Ortak kurallar

- Yeni modüller **.xlsx** kabul eder; ürünler ayrıca **.csv** (UTF-8/UTF-8-SIG veya cp1254, `,`/`;`) ve scraper **catalog.json** (schema_version 1.0) kabul eder. Teklifler, rezervasyonlar ve kampanyalar ayrıca **JSON** (schema_version 1.0) içe/dışa aktarır; CSV/Excel yedek/geçiş formatı olarak korunur.
- Başlıklar Türkçe veya İngilizce olabilir; `Ürün Adı` = `Urun Adi` = `product_name`, `Madde Kodu` = `Ürün ID` = `external_id` eşleşir. Ürün referanslı tüm importlarda `Ürün ID` (madde kodu) kolonu opsiyoneldir; önce madde kodu, kod boşsa ad ile eşleşir.
- Boş hücre genelde “mevcut değeri koru”; **Oliz İndirimli Fiyat istisnadır**: kolon varsa boş/`0` hücre güncellemede Oliz fiyatını siler. `-`, `temizle`, `clear` her zaman “değeri kaldır” anlamına gelir.
- Para hücreleri `38.099,50`, `38099.50`, `38.099 TL` gibi biçimleri kabul eder.
- Tarihler `GG.AA.YYYY`, `GG/AA/YYYY`, `YYYY-MM-DD` ve Excel tarih hücresi olarak kabul edilir.
- Evet/Hayır, Var/Yok, 1/0, TRUE/FALSE boolean olarak kabul edilir.
- Önizleme onaylanmadan yazılmaz; commit tek transaction'dır. Aynı import token'ı tekrar gönderilirse önceki sonuç döner.
- Büyük `catalog.json` dosyaları preview/commit arasında Base64 olarak taşınır; commit multipart parça limiti 32 MB'tır. 8–10 MB dosyalar desteklenir. Ters proxy kullanılıyorsa `client_max_body_size` en az Base64 boyutu (~1.34× dosya) kadar olmalıdır.
- Ürün adı metin olarak tutulmalıdır; Excel sayısal hücreye çevirirse baştaki sıfırlar kaybolabilir.

## Ürünler

**Dışa aktarma kolonları**

| Kolon | Açıklama |
|---|---|
| Ürün ID (Madde Kodu) | Ürünün madde kodu; güncel veya eski alias ile eşleşir; boşsa ad kullanılır |
| Ürün Adı | ID yoksa zorunlu; normalize ada göre eşleşir |
| Kategori | Boşsa mevcut korunur; bilinmeyen kategori otomatik oluşturulur |
| Perakende Fiyat | Boşsa korunur; `-` temizler |
| Oliz İndirimli Fiyat | Boş veya `0` ise güncellemede mevcut Oliz fiyatı silinir; doluysa güncellenir. Kolon hiç yoksa mevcut değer korunur; `-` yine temizler |
| Fiziksel Stok | Boşsa korunur; `0` sıfırlar |
| Alış Fiyatı | Maliyet; boşsa korunur; `-` temizler |
| Kredi Kartı Taban Fiyatı | Dealer pricing; boşsa korunur; `-` temizler |
| Nakit Taban Fiyatı | Dealer pricing; boşsa korunur; `-` temizler |
| Aktif Kampanya | Salt okunur; import'ta kampanya oluşturmaz |
| Ürün Özellikleri (JSON) | `features` + `specifications`; boş hücre korur, boş listeler temizler, bozuk JSON ürün alanlarını yine günceller |
| scraped_at | ISO tarih; boşsa mevcut değer korunur |

Ürün import'u fiyat ve dealer pricing değişikliklerinde geçmiş kaydı yazar; stok değişiminde `csv_update` hareketi oluşturur. Yeni ID geldiğinde ürünün `external_id` değeri güncellenir, eski ID alias olarak saklanır; boş ID mevcut değeri korur. `catalog.json` null `discounted_price` mevcut Oliz fiyatını siler.

**Madde kodu (`external_id`) eşleştirme kuralları**

- Madde kodu doluysa yalnızca güncel `external_id` veya `product_external_id_history` alias'ı ile eşleşir; kod bulunamazsa satır hata verir, ada göre fallback yapılmaz.
- Madde kodu boşsa normalize ürün adıyla legacy eşleşir; aynı ad birden fazla ürüne denk gelirse madde kodu girmesi istenir. Bu satırlar sarı uyarı alır (ör. ek garanti ürünleri); ürün adı biçimi ayrıca denetlenmez.
- Ürün kataloğu importunda yeni madde kodu, mevcut ürünün adıyla tek eşleşiyorsa `external_id` güncellenir; eski kod alias olarak saklanır. Aynı ad farklı kodla ayrı ürün olabilir.
- Yalnızca gerçek alan değişiklikleri "Güncellenecek" sayılır; hiçbir iş alanı değişmiyorsa satır "Değişiklik yok" olarak atlanır ve güncellenen sayısına eklenmez.
- Teklif/rezervasyon/kampanya importları ürünün madde kodunu yalnızca çözer; ürünün güncel kodunu değiştirmez.

## Kampanyalar

**Kampanyalar sayfası:** `Kampanya ID, Kampanya Adı, Açıklama, Kampanya Tipi, Başlangıç Tarihi, Bitiş Tarihi, Fiyat Tabanı, İndirim Türü, İndirim Değeri, Hediye Açıklaması, Hediye İsteğe Bağlı, Hediye Varsa Taban, Hediye Yoksa Taban, Çalışan Notu, Durum, Sürüm No, Arşivde`

**Kampanya Ürünleri sayfası:** `Kampanya ID, Kampanya Adı, Başlangıç Tarihi, Bitiş Tarihi, Ürün ID, Ürün Adı, İlişki Türü, Gerekli Adet`

- `Kampanya Adı`, `Başlangıç Tarihi`, `Bitiş Tarihi` zorunludur.
- İlişki türleri: `Şart ürünü`, `Fayda ürünü`, `Hediye ürünü`, `İlgili ürün`.
- Hediye kampanyasında `Hediye Açıklaması` zorunludur.
- Eşleşme önce `Kampanya ID` ile, yoksa normalize ad + başlangıç + bitiş ile yapılır. Aynı sözleşme yeni sürüm üretmez; önizlemede "Değişiklik yok" olarak atlanır ve güncellenen sayısına eklenmez.
- Tek sayfa şirket dosyası da kabul edilir; aynı kampanya satırları kampanya adı ve tarihlerle gruplanır.
- `Kampanya Ürünleri` sayfası yoksa mevcut ilişkiler korunur.
- Kampanya detayından yapılan dışa aktarma `Ürün ID, Ürün Adı, İlişki Türü, Gerekli Adet` kolonlarını içerir. Aynı dosyaya yüzlerce ürün satırı eklenip detaydan içe aktarılabilir; kampanya başlığı tekrar edilmez.

### Kampanyalar JSON

**Dosya:** `kampanyalar_*.json` · `schema_version` `1.0`

```json
{
  "schema_version": "1.0",
  "scraped_at": "2026-11-22T14:26:27Z",
  "campaigns": [
    {
      "id": "kampanya-slug",
      "name": "Kampanya adı",
      "category": "beyaz-esya-kampanyalari",
      "url": "https://...",
      "start_date": "2026-11-01",
      "end_date": "2026-11-30",
      "date_text": "1 Kasım - 30 Kasım 2026",
      "conditions": ["Koşul 1", "Koşul 2"],
      "product_count": 2,
      "products": [
        {
          "name": "Ürün adı",
          "product_id": "9000",
          "relationship": "İlgili ürün",
          "required_quantity": null
        }
      ],
      "scraped_at": "2026-11-22T14:26:27Z"
    }
  ]
}
```

- Kampanya kimliği `id` slug'ıdır; `campaigns.external_id` olarak saklanır. Aynı slug tekrar gelirse mevcut kampanya güncellenir; dosyada aynı slug iki kez varsa ilk kayıt işlenir.
- `conditions` listesi kampanya sürümünde JSONB olarak saklanır; detay ekranında açılır/kapanır panelde gösterilir.
- Ürünler önce `product_id` (güncel ID veya alias), bulunamazsa ad ile çözülür. Katalogda olmayan ürünler **commit sırasında fiyatsız/stoksuz otomatik oluşturulur** (`external_id` scraper ID'si, ad `product_name`); önizleme yalnızca uyarı gösterir ve veritabanına yazmaz. Aynı ürün birden fazla kampanyada geçerse tek kayıt oluşturulur.
- JSON'da yapısal indirim/tutar alanı yoktur; kampanya `Genel` / `Sadece bilgi` olarak içe aktarılır, koşullar bilgi amaçlıdır.
- Dışa aktarma aynı şemayı üretir. Kampanya listesi ve detayından **JSON Dışa Aktar**, import ekranından **Örnek JSON İndir** kullanılabilir.

## Teklifler

**Teklifler sayfası:** `Teklif No, Teklif Anahtarı, Müşteri Adı, Telefon, Oluşturma Tarihi, Durum, Ödeme Türü, Kanal, Banka, Taksit, Kart Tipi, Kart Bayi İndirimi %, Nakit Bayi İndirimi %, Komisyon Dönemi, Komisyon %, Nakit Toplam, Kart Toplam, Seçili Toplam, Nakit Toplam (Manuel), Kart Toplam (Manuel), Not, Rezervasyon No, Oluşturan, Ürünler`

**Teklif Satırları:** `Teklif No, Teklif Anahtarı, Sıra, Ürün ID, Ürün Adı, Adet, Normal Fiyat, Oliz Fiyatı, Maliyet, Kampanya, Hediye Durumu, Fiyat Tabanı, Önerilen Nakit, Önerilen Kart, Birim Nakit, Birim Kart, Satır Toplam Nakit, Satır Toplam Kart, Uyarı`

**Kâr Detayı:** `Teklif No, Teklif Anahtarı, Ürün Adı, Taksit, Komisyon %, Komisyon Sonrası, Kampanya Hakedişi, Oliz Hakedişi, Toplam Gelir, Maliyet, Kâr/Zarar, Kâr Marjı %`

- Import yalnızca taslak teklif oluşturur/günceller. Durum, komisyon ve kâr kolonları salt okunurdur; sunucu yeniden hesaplar. Değişmeyen taslak teklifler "Değişiklik yok" olarak atlanır.
- Yeni tekliflerde `Teklif Anahtarı` satırları gruplar; mevcut taslaklar `Teklif No` ile güncellenir.
- Kartta kanal, taksit, kart tipi zorunlu; banka isteğe bağlıdır (boşsa genel oran kullanılır). Kart ve nakit bayi indirimi ayrı kolonlardadır; boş bırakılan nakit indirimi kart indirimini kullanır.
- `Nakit Toplam (Manuel)` / `Kart Toplam (Manuel)` boşsa otomatik hesap kullanılır; doluysa toplam, mevcut satır satış toplamlarına göre orantılı olarak satır birim fiyatlarına dağıtılır. Kuruş yuvarlama artığı kalırsa kâr özetinde manuel fark olarak gösterilir.
- `Ürünler` sütunu **export-only**'dir; import'ta okunmaz veya opsiyonel olarak yok sayılır. Ürün satırları `Teklif Satırları` sayfasından gelir.

### Teklifler JSON

`schema_version` 1.0, `offers[]`. Her teklifte müşteri, tarih, durum, ödeme/kanal/banka/taksit/kart tipi, indirimler, nakit/kart/seçili toplamlar, manuel toplamlar, not ve `items[]` bulunur. `items[]`: `product_id` (önce scraper ID/alias, yoksa iç UUID veya ad), `product_name`, `quantity`, `campaign_id` (opsiyonel; dışa aktarımda doldurulur), `campaign_name`, `unit_price_cash`, `unit_price_card`.

- Import önce `offer_number` ile eşleşir; yalnızca taslak teklif güncellenir. Yeni tekliflerde durum, geçerli geçişlerle (taslak → sunuldu → kabul) geri yüklenir.
- Aynı taslak teklif değişmeden tekrar yüklenirse satır "Değişiklik yok" olarak atlanır; güncellenen sayısına eklenmez. `campaign_id` dışa aktarımda yazılır ve geri yüklemede aynı kampanyayı eşler.
- Ürün ID'si bulunamazsa ad denenir; o da yoksa satır hata verir.
- JSON import/export, CSV/Excel'e alternatif değil; ikisi de desteklenir.


## Komisyonlar

**Komisyon Oranları:** `Dönem, Kanal, Banka, Ürün Grubu, Ödero Bandı, Taksit, Oran %`

**Taksit Limitleri:** `Dönem, Kanal, Banka, Ürün Grubu, Kategori, Kart Tipi, Max Taksit`

- Oranlar ve limitler ayrı dosyalarda ve ayrı ekranlarda işlenir.
- `Dönem` `YYYY-MM`; yoksa taslak dönem oluşturulur. Arşivli dönem reddedilir.
- Aynı `scope_key` varsa güncellenir; yoksa eklenir. Dosyada olmayan satırlar silinmez.
- Banka adı normalize edilerek bulunur; bilinmeyen banka hata verir. Banka tüm kanallarda isteğe bağlıdır; boş = genel.
- Ödero bandı yalnız Ödero + Diğer grubunda kullanılır; Klima'da boş bırakılır. Kategori limiti bankasız olmalıdır.
- Komisyon oran/limit importunda bilinmeyen banka önizlemede "yeni" olarak gösterilir ve commit'te oluşturulur (varsayılan açık). Teklif importunda bilinmeyen banka hata verir; "Bilinmeyen bankaları otomatik oluştur" onay kutusu açıkça seçilirse oluşturulur.

## Ayarlar

**Bankalar:** `Banka, Aktif`

**Kategoriler:** `Kategori, Komisyon Grubu`

- Ayarlar'dan tekli/toplu ekleme, yeniden adlandırma, pasifleştirme (banka), komisyon grubu değiştirme (kategori), birleştirme ve yalnız kullanılmayan kaydı silme yapılır.
- Banka/kategori Excel importu ada göre normalize eder; mevcut kaydı günceller, yenisini oluşturur.

## Rezervasyonlar

**Rezervasyonlar:** `Rezervasyon No, Rezervasyon Anahtarı, Müşteri Adı, Rezervasyon Tarihi, Hatırlatma Tarihi, Hatırlatma Durumu, Gecikmiş, Durum, Toplam Adet, Teslim Edilen, İptal Edilen, Açık Adet, Not, Oluşturan, Ürünler`

**Rezervasyon Satırları:** `Rezervasyon No, Rezervasyon Anahtarı, Ürün ID, Ürün Adı, Miktar, Teslim Edilen, İptal Edilen, Açık, Durum, Servis Tarihi, Diğer Bayi Notu, Satır Notu`

- `Ürünler` sütunu **export-only**'dir; import'ta opsiyonel/yok sayılır. Ürün satırları `Rezervasyon Satırları` sayfasından gelir.

### Rezervasyonlar JSON

`schema_version` 1.0, `reservations[]`. Her rezervasyonda müşteri, rezervasyon/hatırlatma tarihi, hatırlatma durumu, not ve `items[]` bulunur. `items[]`: ürün ID/ad, miktar, teslim/iptal adetleri, satır durumu, servis tarihi ve notlar.

- Import mevcut rezervasyon numaralarını atlar; yeni kayıtları mevcut durumlarıyla (teslim/iptal adetleri, satır durumu) oluşturur.
- Stok hareketi oluşturmaz; stok ayrı aktarılmalıdır.

- Import yeni ve açık rezervasyon oluşturur; mevcut `Rezervasyon No` atlanır.
- `Müşteri Adı` ve `Rezervasyon Tarihi` zorunludur; tarih boşsa hata verir.
- `Hatırlatma Tarihi` boşsa rezervasyon tarihinin 13 ay sonrası kullanılır.
- Teslim/iptal/durum alanları salt okunurdur; geçmiş hareket yazılmaz.

## Stok / Sayım

**Stok:** `Ürün Adı, Kategori, Fiziksel Stok, Açık Rezervasyon, Kullanılabilir, Durum`

Salt okunur export'tur. Fiziksel stok güncellemesi ürün import'u veya sayım oturumuyla yapılır.
