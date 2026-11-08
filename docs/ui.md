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

Ana Sayfa varsayılan ekrandır. Üst arama tüm ekranlardan ürün aramaya götürür. MVP'de yalnızca Ana Sayfa ve Ürünler aktiftir; diğer modüller navigasyonda "yakında" etiketiyle devre dışı görünür.

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
- Arama kutusu ve "Ara" düğmesi mobilde ve masaüstünde aynı satırda kalır; metin dikey kırılmaz. Durum filtresi (Aktif / Arşivdekiler / Tümü) ve "Temizle" eylemi dar ekranda alt satıra geçebilir.
- Arama HTMX ile tabloyu yeniler ve URL'yi günceller; sonuçlar sayfalanır.
- Satır seçimi checkbox ile yapılır; seçim varken toplu işlem çubuğu görünür. Seçilenler arşivlenebilir veya iki aşamalı onayla kalıcı olarak silinebilir.
- Tablo kolonları: seçim, Ürün Adı, Normal Fiyat, Oliz / Web İndirimli, Fiziksel Stok, Satılabilir Stok, Son Fiyat Değişimi ve İşlem.
- Her satırda fiziksel stok alanı ve "Stok" düğmesi ile doğrudan güncelleme, ayrıca "Detay" bağlantısı bulunur.
- Arşivdeki ürünler soluk gösterilir ve "Arşivde" rozeti taşır.
- Boş sonuç ve arama eşleşmemesi durumları görünür metinle bildirilir.

#### Ürün tablosu responsive kuralları

- Geniş ekranda (≥1024px) ürünler tablo olarak gösterilir; tablo gerekirse kendi kabında yatay kaydırılır ve sayfa gövdesi yatay kaymaz.
- Masaüstü tabloda işlem kolonu sağa sabitlenir; "Stok" ve "Detay" eylemleri kaydırma sırasında görünür kalır.
- Dar ekranda (<1024px) her ürün satırı kart görünümüne dönüşür. Kart; ürün adı, fiyatlar, fiziksel/satılabilir stok, son fiyat değişimi ve işlem eylemlerini etiketleriyle birlikte gösterir.
- Başlıklar ve metinler yalnızca kelime sınırlarında sarılır; kelimeler karakter karakter bölünmez.
- Fiyat ve stok değerleri tek satırda kalır; tarih alanı gerekirse tarih ve saat olarak iki satıra ayrılır.
- Dar ekranda hücre iç boşlukları azalır; "Stok" ve "Detay" düğmeleri sıkışmadan görünür kalır.

### Ürün Detayı

- Ürün adı, kayıt numarası ve arşiv durumu; "Düzenle", "Stok Güncelle", "Arşivle / Arşivden Çıkar", "Sil" ve "Listeye Dön" eylemleri.
- Özet kartları: Normal Fiyat, Oliz / Web İndirimli, Alış Maliyeti, Fiziksel Stok, Açık Rezervasyon, Satılabilir Stok ve Temin İhtiyacı.
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

## Davranış sözleşmesi

- Veri oturum boyunca mock state'te tutulmaz; kalıcı veritabanına yazılır.
- Arama ve filtreleme sunucu tarafında çalışır; HTMX yalnızca tablo parçasını yeniler.
- Rezervasyon oluşturmak fiziksel stoğu düşürmez. Satılabilir stok = fiziksel stok − açık rezervasyon. Teslimat fiziksel stoğu düşürür.
- Fiziksel stok ve fiyat değişiklikleri geçmiş tablolarına kaydedilir.
- Arşivleme ürünü normal listeden gizler; kalıcı silme yalnızca iki aşamalı doğrulamadan sonra yapılır ve ilişkili geçmiş kayıtlarını da kaldırır.
- Başarı, hata ve boş durumları yalnızca renkle değil, görünür metinle bildirilir.
- Modal ve çekmece katmanları küçük ekranda taşmaz; uzun içerik dikey kaydırılır.
- Hareket azaltma tercihine saygı gösterilir.

## Kapsam dışı

Kimlik doğrulama, rol yönetimi, kamera/barkod çözümleme, kampanya/teklif/rezervasyon/stok sayımı/hızlı teslim modüllerinin tam ekranları ve yazdırma şablonlarının detaylı tasarımı bu UI sözleşmesinin kapsamı dışındadır. Bu modüller navigasyonda devre dışı görünür ve ilgili milestone'larda açılır.
