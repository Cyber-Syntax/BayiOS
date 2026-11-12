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

Ana Sayfa varsayılan ekrandır. Üst arama tüm ekranlardan ürün aramaya götürür. MVP'de Ana Sayfa, Ürünler, Kampanyalar, Teklifler, Komisyonlar, Stok/Sayım ve Rezervasyonlar aktiftir; diğer modüller navigasyonda "yakında" etiketiyle devre dışı görünür.

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
- Ürüne özel bayi nakit/kart taban fiyatları ve değişiklik geçmişi; "Fiyatları Güncelle" modalı.
- Ürünle ilişkili aktif kampanyalar ve hediye var/yok bayi fiyat senaryoları.
- Silme iki aşamalı onay ister; ikinci adım açık teyit olmadan kalıcı silme yapılmaz.

### Kampanyalar

- Liste; kampanya adı/açıklaması araması, tip, aktif/geçmiş/tümü ve tarih aralığı filtreleri sunar; arama ve filtreler HTMX ile tabloyu yeniler, liste sayfalanır.
- Satırlar kampanya adı, tip, geçerlilik, durum (Aktif / Yaklaşan / Süresi geçti / Arşivde), indirim veya hediye özeti ve ürün sayısını gösterir.
- Yeni ve düzenleme formu; ad, tip, başlangıç/bitiş tarihi, açıklama, fiyat tabanı, indirim türü/değeri, hediye açıklaması ve hediye var/yok fiyat tabanı, çalışan notu ve ürün ilişkilerini (şart, fayda, hediye, ilgili) içerir.
- Her fiili düzenleme değişmez yeni sürüm oluşturur; değişiklik yoksa yeni sürüm üretilmez. Detay ekranında sürüm geçmişi ve her sürümün ürün ilişkileri görünür.
- Detay ekranı seçilen ürün için hediye var/yok bayi fiyat senaryosunu gösterir; varsayılan oran %10'dur ve çalışan tarafından değiştirilebilir. Ürüne özel nakit/kart taban fiyatları genel oranla karıştırılmaz.
- Kampanyalar ekranında global bayi indirimi varsayılanı ve değişiklik geçmişi yönetilir.
- Kampanya listesi ve detayı A4 basılabilir; çıktı otomatik fiyat uygulaması değil, çalışan rehberidir.
- Listede "Excel İçe Aktar" ve "Excel Dışa Aktar" eylemleri vardır; içe aktarma önizlemesi kampanya başlığı ve ürün ilişkilerini ayrı satırlarda gösterir.
- Kampanya detayında da "Excel İçe Aktar" ve "Excel Dışa Aktar" bulunur. Detay dışa aktarması yalnızca **Ürün Adı, İlişki Türü, Gerekli Adet** kolonlarını içeren "Kampanya Ürünleri" sayfasını indirir; 100'e kadar ürün satırı bu sayfaya eklenebilir. Detaydan açılan içe aktarma yalnızca o kampanyayı günceller; ürün satırları kampanya başlığı tekrar edilmeden yüklenebilir.

### Teklifler

- Liste; müşteri/durum/tarih filtreleri ve teklif numarası, müşteri, tarih, durum, ödeme tipi, seçili toplam kolonlarıyla sayfalanır.
- Yeni/düzenleme ekranı müşteri adı, telefon, not, ödeme tipi (nakit/kart), kartta kanal (POS/Ödero/Chippin), banka, taksit, kart tipi (bireysel/business) ve teklif genelinde bayi indirimi içerir.
- Ürün satırlarında ürün arama, miktar, satır bazında tek kampanya ve hediye var/yok seçimi bulunur. Kampanya seçilirse Oliz uygulanmaz; iki kampanya birleşmez.
- Her satırda toptan vadeli alış, normal fiyat, Oliz, seçilen kampanya fiyatı, bayi indirimi, önerilen nakit ve komisyonlu kart referansı gösterilir; nihai nakit/kart birim fiyatını çalışan girer. Floor veya kâr referansı altında uyarı verilir, kayıt engellenmez.
- Detay ekranı toplamları, komisyon snapshot'ını, durum geçmişini ve iç kâr özetini gösterir; müşteri A4 çıktısında maliyet, iç kâr ve komisyon detayı bulunmaz.
- Taslak teklif düzenlenebilir; sunuldu/kabul/lost/expired sonrası fiyat snapshot'ı değişmez. Kabul edilen tekliften rezervasyona dönüşüm retry edildiğinde aynı rezervasyon döner.
- Detay ekranında "Kâr / Komisyon Özeti" kartı her zaman görünür; seçili taksitin komisyonu, kampanya/Oliz hakedişi, maliyet, kâr ve marjı gösterir. A4 müşteri çıktısında bu bilgiler yer almaz.
- Listede "Excel İçe Aktar" ve "Excel Dışa Aktar" eylemleri vardır; dışa aktarılan çalışma kitabı Teklifler, Teklif Satırları ve Kâr Detayı sayfalarını içerir. İçe aktarma yalnızca taslak teklif oluşturur/günceller.

### Komisyonlar

- Aylık komisyon dönemleri listelenir; yeni dönem önceki dönemi kopyalayarak açılır, düzenlenir ve aktifleştirilir. Geçmiş dönem değişmez.
- Kanal sekmeleri POS, Ödero ve Chippin'dir. POS ve Ödero banka bazlı, Chippin bankadan bağımsızdır.
- Matris; ürün komisyon grubu ve taksit kolonlarıyla oran girişi sunar. Klima ayrı gruptur; TV standart oranı kullanır ama max 4 taksit, diğerleri max 5, Chippin max 6, business kart max 2 taksit olarak sınırlanır.
- Ödero için 20.000 TL altı/üstü tutar bantları ayrı düzenlenir; eşik sepet toplamına uygulanır.
- Limitler paneli kanal, banka/kanal, ürün grubu ve kart tipi limitlerini gösterir; etkin üst sınır canlı önizlenir.
- Kategori komisyon grubu eşlemesi, değişiklik geçmişi ve P1 komisyon A4 listesi bulunur.
- Komisyon oranları ve taksit limitleri ayrı Excel dosyalarıyla içe/dışa aktarılır; dönem detayında döneme özel, listede tüm dönemler için export butonları bulunur.

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
- Listede "Excel İçe Aktar" ve "Excel Dışa Aktar" eylemleri vardır; export müşteri, tarih, hatırlatma, durum ve ürün başına teslim/iptal/açık miktarlarını iki sayfada verir. Import yeni açık rezervasyon oluşturur; mevcut numaraları ve geçmiş teslim/iptal alanlarını atlar.
- Ana ekranda gecikmiş ve önümüzdeki 30 gün içindeki hatırlatmalar görünür.

### Excel İçe/Dışa Aktarma

- Ürünler, Kampanyalar, Teklifler, Komisyonlar ve Rezervasyonlar için Türkçe başlıklı Excel (.xlsx) export vardır; Ürünler ayrıca CSV export/import destekler.
- Yeni modüllerin import ekranlarında "Şablon İndir" bağlantısı bulunur; şablonun "Kullanım" sayfası kolonları, zorunlulukları ve kabul edilen değerleri açıklar.
- Import akışı: dosya seç → önizleme (hatalı/uyarılı satırlar üstte, yeni/güncellenecek/hatalı sayaçları) → satır veya toplu karar → tek transaction commit. Önizleme onaylanmadan veritabanına yazılmaz.
- Ürün import'unda Alış Fiyatı, Kredi Kartı Taban Fiyatı ve Nakit Taban Fiyatı güncellenebilir; boş hücre mevcut değeri korur, `-` temizler. Aktif Kampanya salt okunurdur.
- Kampanya import'u kampanya başlığı + ürün ilişkisi satırlarını kabul eder; başlangıç/bitiş tarihi zorunludur. Aynı sözleşme yeni sürüm oluşturmaz.
- Komisyon oranları ve taksit limitleri ayrı dosya/ekranlarda içe ve dışa aktarılır; dönem yoksa taslak dönem oluşturulur.
- Rezervasyon import'u yalnızca yeni açık rezervasyon oluşturur; mevcut Rezervasyon No atlanır. Teslim/iptal geçmişi import edilmez.
- Aynı dosyanın çift gönderimi import token'ı ile engellenir; sonuç listelerde Türkçe özet bandıyla gösterilir.
- Geniş tablolarda yatay kaydırma gerekliyse tablo kabı `data-table-scroll` ile işaretlenir. [table-scroll.js](../src/bayios/web/static/js/table-scroll.js) tablonun altına yapışan, her zaman görünür bir yatay scrollbar ve "Yatay kaydır" ipucu ekler. Yeni geniş tablolarda aynı desen kullanılmalıdır; kullanıcı scrollbar'ı fark etmek için tabloyu ayrıca keşfetmek zorunda kalmaz.

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
- Kampanya düzenlemeleri değişmez sürümler olarak saklanır; eski sürüm ve geçmiş teklif snapshot'ı sonradan değişmez.
- Bayi nakit/kart taban fiyatı yalnızca fiili değer değişikliğinde geçmişe yazılır; global bayi indirimi oranından ayrı tutulur.
- Kampanya rehberi otomatik POS fiyatı uygulamaz; senaryo sonucu yalnızca çalışanın gördüğü öneridir.
- Arşivleme ürünü normal listeden gizler; kalıcı silme yalnızca iki aşamalı doğrulamadan sonra yapılır ve ilişkili geçmiş kayıtlarını da kaldırır.
- Başarı, hata ve boş durumları yalnızca renkle değil, görünür metinle bildirilir.
- Modal ve çekmece katmanları küçük ekranda taşmaz; uzun içerik dikey kaydırılır.
- Hareket azaltma tercihine saygı gösterilir.
- Tarihler `10.11.2026` ve `10 Kasım 2026` biçiminde, Europe/Istanbul saat diliminde gösterilir; tarih seçici tarayıcı dilinden bağımsız Türkçedir (bkz. Tarih seçici).

## Kapsam dışı

Kimlik doğrulama, rol yönetimi, kamera/barkod çözümleme, hızlı teslim modülünün tam ekranı ve yazdırma şablonunun detaylı tasarımı bu UI sözleşmesinin kapsamı dışındadır. Bu modül navigasyonda devre dışı görünür ve ilgili milestone'da açılır.
