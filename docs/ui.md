# BayiOS UI/UX Sözleşmesi

Bu belge, BayiOS web arayüzünün güncel üretim yapısını ve kullanıcı deneyimi sözleşmesini tanımlar. Prototip aşaması tamamlanmıştır; `prototype/index.html` artık ürünün parçası değildir. Arayüz FastAPI + Jinja2 ile sunucuda render edilir, HTMX yalnızca kısmi güncellemeler için, Alpine.js ise yalnızca yerel UI durumu için kullanılır.

## Kullanıcı ve bilgi mimarisi

MVP'de rol ve hesap yoktur. Her kullanıcı aynı sol navigasyonu görür:

- Ana Sayfa
- Ürünler
- Kampanyalar
- Teklifler
- Rezervasyonlar
- Stok/Sayım
- Hızlı Teslim
- Ayarlar

Ana Sayfa varsayılan ekrandır. Üst arama tüm ekranlardan ürün aramaya götürür. MVP'de Ana Sayfa, Ürünler, Stok/Sayım ve Rezervasyonlar aktiftir; diğer modüller navigasyonda "yakında" etiketiyle devre dışı görünür.

## Uygulama kabuğu

- Üst çubuk marka bağlantısını, global ürün aramasını ve sol menü aç/kapat düğmesini içerir.
- Sol menüde her öğe için bir ikon bulunur; daraltılmış görünümde yalnızca ikonlar kalır, geniş görünümde etiketler de görünür.
- Masaüstünde (≥1280px) sol menü varsayılan olarak açıktır ve kullanıcı tarafından daraltılabilir.
- Küçük ekranlarda (<1280px) sol menü varsayılan olarak kapalıdır; aç/kapat düğmesiyle ekranı kaplayan bir çekmece olarak açılır. Arka plan katmanına veya bir menü bağlantısına dokunmak menüyü kapatır.
- Ekran boyutu 1280px sınırını geçtiğinde menü otomatik olarak açılır, altına düştüğünde otomatik olarak kapanır.
- Menü durumu `aria-expanded` ve `aria-controls` ile bildirilir; aktif sayfa `aria-current="page"` taşır.
- Yazdırma görünümünde üst çubuk, sol menü ve arka plan katmanı gizlenir.

## Görsel yön

- Ferah, minimal ve satışa indirgenmemiş operasyon arayüzü.
- Açık zemin, lacivert/indigo vurgu, sakin durum renkleri ve net tipografi.
- Ürünlerde tablo; operasyon listelerinde filtre, durum rozeti ve sayfalama.
- Renk tek başına anlam taşımaz; durumlar metinle birlikte gösterilir.
- Masaüstü ve mobil aynı bilgi mimarisini kullanır; mobilde ürün satırları kart görünümüne dönüşür ve içerik yatay kaydırma gerektirmeden okunabilir.

## Ekranlar

### Ana Sayfa

- Modül kartları kullanıcıyı ilgili ekrana götürür.
- Henüz açılmamış modüller "Yakında" rozetiyle devre dışı gösterilir.
- Global arama üst çubuktan ürün aramasına yönlendirir.

### Ürünler

- Başlık, ürün sayısı ve katalog açıklaması; "Yeni Ürün Ekle", "CSV / Excel İçe Aktar", "CSV Dışa Aktar" ve "Excel Dışa Aktar" eylemleri.
- Arama kutusu ve "Ara" düğmesi mobilde ve masaüstünde aynı satırda kalır; metin dikey kırılmaz. Durum filtresi (Aktif / Arşivdekiler / Tümü), kategori filtresi ve "Temizle" eylemi dar ekranda alt satıra geçebilir.
- Arama HTMX ile tabloyu yeniler ve URL'yi günceller; sonuçlar sayfalanır.
- Satır seçimi checkbox ile yapılır; seçim varken toplu işlem çubuğu görünür. Seçilenler arşivlenebilir veya iki aşamalı onayla kalıcı olarak silinebilir. Dar ekranda karta dokunmak da satırı seçer (bağlantı, buton ve giriş alanları hariç).
- Tablo kolonları: seçim, Ürün Adı, Kategori, Normal Fiyat, Oliz / Web İndirimli, Fiziksel Stok, Son Fiyat Değişimi ve İşlem.
- Her satırda fiziksel stok alanı ve "Stok" düğmesi ile doğrudan güncelleme, ayrıca "Detay" bağlantısı bulunur.
- Arşivdeki ürünler soluk gösterilir ve "Arşivde" rozeti taşır.
- Boş sonuç ve arama eşleşmemesi durumları görünür metinle bildirilir.

#### Ürün tablosu responsive kuralları

- Geniş ekranda (≥1024px) ürünler tablo olarak gösterilir; tablo gerekirse kendi kabında yatay kaydırılır ve sayfa gövdesi yatay kaymaz.
- Masaüstü tabloda işlem kolonu sağa sabitlenir; "Stok" ve "Detay" eylemleri kaydırma sırasında görünür kalır.
- Dar ekranda (<1024px) her ürün satırı kart görünümüne dönüşür. Kart; ürün adı, kategori, fiyatlar, fiziksel stok, son fiyat değişimi ve işlem eylemlerini etiketleriyle birlikte gösterir.
- Başlıklar ve metinler yalnızca kelime sınırlarında sarılır; kelimeler karakter karakter bölünmez.
- Fiyat ve stok değerleri tek satırda kalır; tarih alanı gerekirse tarih ve saat olarak iki satıra ayrılır.
- Dar ekranda hücre iç boşlukları azalır; "Stok" ve "Detay" düğmeleri sıkışmadan görünür kalır.

### Ürün Detayı

- Ürün adı, kayıt numarası ve arşiv durumu; "Düzenle", "Stok Güncelle", "Arşivle / Arşivden Çıkar", "Sil" ve "Listeye Dön" eylemleri.
- Özet kartları: Normal Fiyat, Oliz / Web İndirimli, Alış Maliyeti, Fiziksel Stok ve Açık Rezervasyon.
- Fiyat Geçmişi tablosu: tarih, fiyat türü, eski/yeni değer, kaynak ve işlemi yapan.
- Stok Hareket Geçmişi tablosu: tarih, hareket türü, önceki miktar, değişim, yeni miktar, not ve işlemi yapan.
- Düzenleme ve stok güncelleme modalları; stok güncellemede açıklama/not alanı.
- Silme iki aşamalı onay ister; ikinci adım açık teyit olmadan kalıcı silme yapılmaz.

### Ürün Kataloğu İçe Aktarma

- CSV ve Excel (.xlsx) dosyası yükleme; desteklenen format, fiyat, stok ve indirim kuralları ekranda açıklanır.
- Önizleme ekranında toplam satır, yeni ürün, güncellenecek ve hatalı satır sayaçları gösterilir.
- Satır bazında karar: Yeni Ürün Aç, Güncelle, Atla veya İndirimli Fiyatı Temizle.
- Toplu kararlar: Tümünü Güncelle, Tümünü Atla, Tümünü Yeni Ürün ve Sorunluları Atla.
- Hatalı ve uyarılı satırlar görünür biçimde işaretlenir; önizleme onaylanmadan veritabanına yazılmaz.
- Onay tek transaction içinde atomik olarak uygulanır; sonuç özeti ürünler ekranında bildirilir.

### Rezervasyonlar

- Liste; müşteri araması, durum filtresi (Açık / Teslim edildi / İptal / Hatırlatması geciken / Tümü) ve sayfalama sunar; arama HTMX ile tabloyu yeniler.
- Satırlar rezervasyon numarası, müşteri, tarih, hatırlatma tarihi ve durumu, özet durum (Rezerve / Kısmi süreçte / Teslim edildi / İptal) ile açık/toplam miktarı gösterir.
- Yeni rezervasyon ekranı müşteri adı (zorunlu), tarih, not ve ürün satırlarından oluşur; ürün aramasından "Ekle" ile satır eklenir, miktar satır bazında girilir ve aynı ürün ikinci kez eklenmez.
- Detay ekranı satır bazında miktar, teslim, iptal, açık miktar, durum ve işlemleri (durum değiştir, teslim et, iptal et, miktar güncelle, satır sil, satır ekle) sunar; hareket ve erteleme geçmişi açılır bölümlerde görünür.
- Durum adımları opsiyoneldir ve teslimden önce geri alınabilir; teslim her aktif durumdan yapılabilir. Teslim ve iptal kendi formlarından yürütülür.
- Düşük stokta teslim, gerekçe girildiğinde onaylanır; fiziksel stok negatife düşebilir ve bu durum görünür metinle bildirilir.
- Hatırlatma rezervasyon tarihinden 13 ay sonrasına otomatik atanır; varsayılan erteleme 1 aydır ve geçmişi tutulur. Tüm satırlar kapanınca hatırlatma "Tamamlandı" olur.
- A4 çıktısı depo ve bayi kopyasını tek yazdırmada (arada sayfa sonu) ya da tek kopya olarak verir; rezervasyon listesi de A4 basılabilir.
- Ana ekranda gecikmiş ve önümüzdeki 30 gün içindeki hatırlatmalar görünür.

### Tarih seçici

- Takvim **Flatpickr 4.6.13** ile gelir ve `static/vendor/flatpickr/` altından yerel olarak servis edilir; CDN veya çalışma zamanı internet bağımlılığı yoktur. Lisans metni ve SHA-256 özetleri vendor klasöründe/`VERSIONS.txt` içinde tutulur.
- Takvim dili tarayıcı dilinden bağımsız olarak Türkçedir: aylar (Ocak…Aralık), günler (Pzt…Paz), hafta Pazartesi başlar; `Bugün` ve `Temizle` düğmeleri bulunur. Mobil/dokunmatik cihazlarda da aynı Türkçe takvim açılır.
- Alan görünürde sayısal `10.11.2026` biçimini gösterir; altında `10 Kasım 2026` önizlemesi canlı güncellenir. Forma gönderilen değer ISO (`2026-11-10`) kalır; elle `GG.AA.YYYY` yazımı da kabul edilir.
- Takvim, modal içinde kırpılmadan açılır; Escape ile kapanır; yazdırma görünümünde basılmaz.
- JS yüklenmezse native `<input type="date">` fallback'i çalışır; sunucu `GG.AA.YYYY`, `GG-AA-YYYY` ve `YYYY-MM-DD` biçimlerini kabul eder.

## Davranış sözleşmesi

- Veri oturum boyunca mock state'te tutulmaz; kalıcı veritabanına yazılır.
- Arama ve filtreleme sunucu tarafında çalışır; HTMX yalnızca tablo parçasını yeniler.
- Rezervasyon oluşturmak fiziksel stoğu düşürmez ve ürün ayırmaz; fiziksel stok doğrudan satılabilir stoktur. Teslimat fiziksel stoğu düşürür.
- Rezervasyon satırında durum değiştirmek ve iptal etmek stok hareketi üretmez; yalnızca teslim edilen miktar `delivery_out` hareketiyle fiziksel stoktan düşer ve aynı işlem tekrar gönderildiğinde ikinci hareket oluşmaz.
- Açık rezervasyonu olan ürün veritabanından silinemez; kullanıcıya bunun nedenini açıklayan uyarı gösterilir.
- Fiziksel stok ve fiyat değişiklikleri geçmiş tablolarına kaydedilir.
- Arşivleme ürünü normal listeden gizler; kalıcı silme yalnızca iki aşamalı doğrulamadan sonra yapılır ve ilişkili geçmiş kayıtlarını da kaldırır.
- Başarı, hata ve boş durumları yalnızca renkle değil, görünür metinle bildirilir.
- Modal ve çekmece katmanları küçük ekranda taşmaz; uzun içerik dikey kaydırılır.
- Hareket azaltma tercihine saygı gösterilir.
- Tarihler `10.11.2026` ve `10 Kasım 2026` biçiminde, Europe/Istanbul saat diliminde gösterilir; tarih seçici tarayıcı dilinden bağımsız Türkçedir (bkz. Tarih seçici).

## Kapsam dışı

Kimlik doğrulama, rol yönetimi, kamera/barkod çözümleme, kampanya/teklif/hızlı teslim modüllerinin tam ekranları ve bu modüllerin yazdırma şablonlarının detaylı tasarımı bu UI sözleşmesinin kapsamı dışındadır. Bu modüller navigasyonda devre dışı görünür ve ilgili milestone'larda açılır.
