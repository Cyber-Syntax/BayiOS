# BayiOS Excel İçe/Dışa Aktarma Başvurusu

Bu belge, BayiOS'ta kullanılan Excel/CSV kolonlarını ve içe aktarma davranışlarını özetler.
Kullanıcıya gösterilen tüm metinler Türkçedir; teknik hata ayrıntıları loglara gider.

## Ortak kurallar

- Yeni modüller **.xlsx** kabul eder; ürünler ayrıca **.csv** (UTF-8/UTF-8-SIG veya cp1254, `,`/`;`) kabul eder.
- Başlıklar Türkçe veya İngilizce olabilir; `Ürün Adı` = `Urun Adi` = `product_name` eşleşir.
- Boş hücre “mevcut değeri koru”; `-`, `temizle`, `clear` “değeri kaldır”.
- Para hücreleri `38.099,50`, `38099.50`, `38.099 TL` gibi biçimleri kabul eder.
- Tarihler `GG.AA.YYYY`, `GG/AA/YYYY`, `YYYY-MM-DD` ve Excel tarih hücresi olarak kabul edilir.
- Evet/Hayır, Var/Yok, 1/0, TRUE/FALSE boolean olarak kabul edilir.
- Önizleme onaylanmadan yazılmaz; commit tek transaction'dır. Aynı import token'ı tekrar gönderilirse önceki sonuç döner.
- Ürün adı metin olarak tutulmalıdır; Excel sayısal hücreye çevirirse baştaki sıfırlar kaybolabilir.

## Ürünler

**Dışa aktarma kolonları**

| Kolon | Açıklama |
|---|---|
| Ürün Adı | Zorunlu; normalize ada göre eşleşir |
| Kategori | Boşsa mevcut korunur; bilinmeyen kategori otomatik oluşturulur |
| Perakende Fiyat | Boşsa korunur; `-` temizler |
| Oliz İndirimli Fiyat | Boşsa korunur; `-` temizler |
| Fiziksel Stok | Boşsa korunur; `0` sıfırlar |
| Alış Fiyatı | Maliyet; boşsa korunur; `-` temizler |
| Kredi Kartı Taban Fiyatı | Dealer pricing; boşsa korunur; `-` temizler |
| Nakit Taban Fiyatı | Dealer pricing; boşsa korunur; `-` temizler |
| Aktif Kampanya | Salt okunur; import'ta kampanya oluşturmaz |

Ürün import'u fiyat ve dealer pricing değişikliklerinde geçmiş kaydı yazar; stok değişiminde `csv_update` hareketi oluşturur.

## Kampanyalar

**Kampanyalar sayfası:** `Kampanya ID, Kampanya Adı, Açıklama, Kampanya Tipi, Başlangıç Tarihi, Bitiş Tarihi, Fiyat Tabanı, İndirim Türü, İndirim Değeri, Hediye Açıklaması, Hediye İsteğe Bağlı, Hediye Varsa Taban, Hediye Yoksa Taban, Çalışan Notu, Durum, Sürüm No, Arşivde`

**Kampanya Ürünleri sayfası:** `Kampanya ID, Kampanya Adı, Başlangıç Tarihi, Bitiş Tarihi, Ürün Adı, İlişki Türü, Gerekli Adet`

- `Kampanya Adı`, `Başlangıç Tarihi`, `Bitiş Tarihi` zorunludur.
- İlişki türleri: `Şart ürünü`, `Fayda ürünü`, `Hediye ürünü`, `İlgili ürün`.
- Hediye kampanyasında `Hediye Açıklaması` zorunludur.
- Eşleşme önce `Kampanya ID` ile, yoksa normalize ad + başlangıç + bitiş ile yapılır. Aynı sözleşme yeni sürüm üretmez.
- Tek sayfa şirket dosyası da kabul edilir; aynı kampanya satırları kampanya adı ve tarihlerle gruplanır.
- `Kampanya Ürünleri` sayfası yoksa mevcut ilişkiler korunur.
- Kampanya detayından yapılan dışa aktarma yalnızca `Ürün Adı, İlişki Türü, Gerekli Adet` kolonlarını içerir. Aynı dosyaya yüzlerce ürün satırı eklenip detaydan içe aktarılabilir; kampanya başlığı tekrar edilmez.

## Teklifler

**Teklifler sayfası:** `Teklif No, Teklif Anahtarı, Müşteri Adı, Telefon, Oluşturma Tarihi, Durum, Ödeme Türü, Kanal, Banka, Taksit, Kart Tipi, Bayi İndirimi %, Komisyon Dönemi, Komisyon %, Nakit Toplam, Kart Toplam, Seçili Toplam, Not, Rezervasyon No, Oluşturan`

**Teklif Satırları:** `Teklif No, Teklif Anahtarı, Sıra, Ürün Adı, Adet, Normal Fiyat, Oliz Fiyatı, Maliyet, Kampanya, Hediye Durumu, Fiyat Tabanı, Önerilen Nakit, Önerilen Kart, Birim Nakit, Birim Kart, Satır Toplam Nakit, Satır Toplam Kart, Uyarı`

**Kâr Detayı:** `Teklif No, Teklif Anahtarı, Ürün Adı, Taksit, Komisyon %, Komisyon Sonrası, Kampanya Hakedişi, Oliz Hakedişi, Toplam Gelir, Maliyet, Kâr/Zarar, Kâr Marjı %`

- Import yalnızca taslak teklif oluşturur/günceller. Durum, komisyon ve kâr kolonları salt okunurdur; sunucu yeniden hesaplar.
- Yeni tekliflerde `Teklif Anahtarı` satırları gruplar; mevcut taslaklar `Teklif No` ile güncellenir.
- Kartta kanal, taksit, kart tipi zorunlu; POS/Ödero'da banka zorunlu, Chippin'de banka boş olmalıdır.

## Komisyonlar

**Komisyon Oranları:** `Dönem, Kanal, Banka, Ürün Grubu, Ödero Bandı, Taksit, Oran %`

**Taksit Limitleri:** `Dönem, Kanal, Banka, Ürün Grubu, Kart Tipi, Max Taksit`

- Oranlar ve limitler ayrı dosyalarda ve ayrı ekranlarda işlenir.
- `Dönem` `YYYY-MM`; yoksa taslak dönem oluşturulur. Arşivli dönem reddedilir.
- Aynı `scope_key` varsa güncellenir; yoksa eklenir. Dosyada olmayan satırlar silinmez.
- Banka adı normalize edilerek bulunur; bilinmeyen banka hata verir.

## Rezervasyonlar

**Rezervasyonlar:** `Rezervasyon No, Rezervasyon Anahtarı, Müşteri Adı, Rezervasyon Tarihi, Hatırlatma Tarihi, Hatırlatma Durumu, Gecikmiş, Durum, Toplam Adet, Teslim Edilen, İptal Edilen, Açık Adet, Not, Oluşturan`

**Rezervasyon Satırları:** `Rezervasyon No, Rezervasyon Anahtarı, Ürün Adı, Miktar, Teslim Edilen, İptal Edilen, Açık, Durum, Servis Tarihi, Diğer Bayi Notu, Satır Notu`

- Import yeni ve açık rezervasyon oluşturur; mevcut `Rezervasyon No` atlanır.
- `Müşteri Adı` ve `Rezervasyon Tarihi` zorunludur; tarih boşsa hata verir.
- `Hatırlatma Tarihi` boşsa rezervasyon tarihinin 13 ay sonrası kullanılır.
- Teslim/iptal/durum alanları salt okunurdur; geçmiş hareket yazılmaz.

## Stok / Sayım

**Stok:** `Ürün Adı, Kategori, Fiziksel Stok, Açık Rezervasyon, Kullanılabilir, Durum`

Salt okunur export'tur. Fiziksel stok güncellemesi ürün import'u veya sayım oturumuyla yapılır.
