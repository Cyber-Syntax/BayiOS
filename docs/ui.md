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
- Ayarlar

Ana Sayfa varsayılan ekrandır. Üst arama tüm ekranlardan ürün aramaya götürür. MVP'de Ana Sayfa, Ürünler, Kampanyalar, Teklifler, Komisyonlar, Stok/Sayım, Rezervasyonlar ve Ayarlar aktiftir; Hızlı Teslim v2 adayıdır ve v1 navigasyonunda yer almaz.

## Uygulama kabuğu

- Üst çubuk marka bağlantısını, global ürün aramasını ve sol menü aç/kapat düğmesini içerir.
- Sol menüde her öğe için bir ikon bulunur; daraltılmış görünümde yalnızca ikonlar kalır, geniş görünümde etiketler de görünür.
- Masaüstünde (≥1280px) sol menü varsayılan olarak açıktır, üst çubuk ve sol menü sticky kalır; sol menü kendi içinde kaydırılabilir ve viewport yüksekliğini aşmaz.
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
- Arama/filtre alanı üstte sticky kalır. Satır seçimi checkbox veya satırın boş alanına tıklayarak yapılır; bu davranış tüm ekran boyutlarında geçerlidir (bağlantı, buton, checkbox ve form alanları hariç).
- Seçim varken toplu işlem çubuğu ekranın altında sticky footer olarak görünür; seçilen sayısı, "Tümünü seç" checkbox'ı, kategori atama, arşivleme ve iki aşamalı onaylı kalıcı silme eylemlerini taşır. Dar ekranda da "Tümünü seç" bu çubuktan kullanılabilir.
- Seçili satır mavi dolguyla değil, accent renkli kenarlık ve hafif vurguyla gösterilir; bu kural masaüstü tabloda da küçük ekran kartında da aynıdır.
- Tablo kolonları: seçim, Ürün Adı (altında scraper ID), Kategori, Normal Fiyat, Oliz / Web İndirimli, Fiziksel Stok, Son Fiyat Değişimi ve İşlem.
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
- Üst arama/filtre alanı ve alt toplu işlem çubuğu sticky kalır; sayfa kaydırıldığında erişilebilir olurlar. Toplu işlem çubuğu için içerik altında boşluk bırakılır.

### Ürün Detayı

- Ürün adı, kayıt numarası ve arşiv durumu; "Düzenle", "Stok Güncelle", "Arşivle / Arşivden Çıkar", "Sil" ve "Listeye Dön" eylemleri.
- Özet kartları: Normal Fiyat, Oliz / Web İndirimli, Alış Maliyeti, Fiziksel Stok ve Açık Rezervasyon. Ayrıca "Scraper Bilgisi" kartında güncel Ürün ID, Tür, kaynak URL ve scraper tarihi gösterilir.
- Fiyat Geçmişi tablosu: tarih, fiyat türü, eski/yeni değer, kaynak ve işlemi yapan.
- Stok Hareket Geçmişi tablosu: tarih, hareket türü, önceki miktar, değişim, yeni miktar, not ve işlemi yapan.
- Düzenleme ve stok güncelleme modalları; stok güncellemede açıklama/not alanı.
- Ürüne özel bayi nakit/kart taban fiyatları ve değişiklik geçmişi; "Fiyatları Güncelle" modalı.
- Ürünle ilişkili aktif kampanyalar ve hediye var/yok bayi fiyat senaryoları.
- Scraper detayları varsa "Ürün Özellikleri (N)" ve "Teknik Özellikler (N)" bölümleri **varsayılan kapalı** açılır-kapanır paneller olarak gösterilir; detay yoksa bu bölümler gizlenir.
- Silme iki aşamalı onay ister; ikinci adım açık teyit olmadan kalıcı silme yapılmaz.

### Kampanyalar

- Liste; kampanya adı/açıklaması araması, tip, aktif/geçmiş/tümü ve tarih aralığı filtreleri sunar; arama ve filtreler HTMX ile tabloyu yeniler, liste sayfalanır.
- Satırlar kampanya adı, tip, geçerlilik, durum (Aktif / Yaklaşan / Süresi geçti / Arşivde), indirim veya hediye özeti ve ürün sayısını gösterir.
- Yeni ve düzenleme formu; ad, tip, başlangıç/bitiş tarihi, açıklama, fiyat tabanı, indirim türü/değeri, hediye açıklaması ve hediye var/yok fiyat tabanı, çalışan notu ve ürün ilişkilerini (şart, fayda, hediye, ilgili) içerir.
- Her fiili düzenleme değişmez yeni sürüm oluşturur; değişiklik yoksa yeni sürüm üretilmez. Detay ekranında sürüm geçmişi ve her sürümün ürün ilişkileri görünür.
- Detay ekranı seçilen ürün için hediye var/yok bayi fiyat senaryosunu gösterir; varsayılan oran %10'dur ve çalışan tarafından değiştirilebilir. Ürüne özel nakit/kart taban fiyatları genel oranla karıştırılmaz.
- Scraper JSON'undan gelen kampanyalarda kaynak ID, kategori, kaynak URL ve scraper tarihi gösterilir; **Koşullar (N)** bölümü varsayılan kapalı açılır/kapanır paneldedir. Kaynakta olup Bayios kataloğunda eşleşmeyen ürünler için "kaynakta X, eşleşen Y" notu görünür.
- Kampanyalar ekranında global bayi indirimi varsayılanı ve değişiklik geçmişi yönetilir.
- Kampanya listesi ve detayı A4 basılabilir; çıktı otomatik fiyat uygulaması değil, çalışan rehberidir.
- Listede **"İçe Aktar (Excel/JSON)"**, **"Excel Dışa Aktar"** ve **"JSON Dışa Aktar"** eylemleri vardır; içe aktarma önizlemesi kampanya başlığı ve ürün ilişkilerini ayrı satırlarda gösterir.
- JSON kampanya importunda katalogda olmayan ürünler fiyatsız/stoksuz otomatik oluşturulur; çalışan ürün detayından fiyatı sonra girer.
- Kampanya detayında da **"İçe Aktar (Excel/JSON)"**, **"Excel Dışa Aktar"** ve **"JSON Dışa Aktar"** bulunur. Excel detay dışa aktarması yalnızca **Ürün Adı, İlişki Türü, Gerekli Adet** kolonlarını içeren "Kampanya Ürünleri" sayfasını indirir; 100'e kadar ürün satırı bu sayfaya eklenebilir. JSON detay dışa aktarması kampanyanın adı, tarihleri, koşulları ve ürün ilişkileriyle tek kampanyalı şema üretir. Detaydan açılan içe aktarma yalnızca o kampanyayı günceller; ürün satırları kampanya başlığı tekrar edilmeden yüklenebilir.

### Teklifler

- Liste; müşteri/durum/tarih filtreleri ve teklif numarası, müşteri, **Ürünler**, tarih, durum, ödeme tipi, seçili toplam kolonlarıyla sayfalanır. Ürünler hücresi `Ürün ×2 · Ürün ×1` biçimindedir.
- Yeni/düzenleme ekranı müşteri adı, telefon, not, ödeme tipi (nakit/kart), kartta kanal (POS/Ödero/Chippin), banka (isteğe bağlı), taksit, kart tipi (bireysel/business), **Kart Bayi İndirimi (%)** ve **Nakit Bayi İndirimi (%)** içerir. İki indirim de çalışan tarafından değiştirilebilir. Banka boş bırakılırsa genel komisyon oranı kullanılır; seçilen oranın genel mi bankaya özel mi olduğu gösterilir.
- Taksit seçenekleri açılır/kapanır paneldedir; ürün, miktar, kampanya, bayi indirimi veya ödeme alanı değiştiğinde otomatik yenilenir. Senaryo özeti sepetin hemen üstünde ayrı karttadır; altta seçili teklifin nakit/kart/kanal/banka/taksit detayı yer alır. Bir satırdaki **Seç** formdaki ödeme tipi/kanal/banka/taksit/kart tipi alanlarını doldurur; teklif ancak kullanıcı Kaydet dediğinde oluşur.
- Sepetin üstünde **Senaryo Özeti** kartı bulunur; ürün/ödeme değişince otomatik güncellenir. Sepette **Nakit Toplam (manuel)** ve **Kart Toplam (manuel)** alanları vardır; boş = otomatik, dolu = manuel nakit/kart toplamı. Manuel toplam satır fiyatlarına orantılı dağıtılır; yuvarlama artığı kâr özetinde ayrı gösterilir.
- **Taksit Seçenekleri** açılır/kapanır paneldedir; ürün eklenince/çıkarılınca `$nextTick` sonrası otomatik yenilenir.
- **Vazgeç** ve **Teklif Oluştur / Kaydet** butonları ekranın altında sticky bar olarak durur.
- Ürün satırlarında ürün arama, miktar, satır bazında tek kampanya ve hediye var/yok seçimi bulunur. "Otomatik" seçeneği kampanya ile Oliz arasından normal fiyattan en yüksek indirimi vereni seçer; çalışan belirli bir kampanyayı veya "Kampanya yok"u seçebilir. Kampanya ve bayi indirimi sırayla uygulanır: 40.000 → %10 kampanya → 36.000 → %10 bayi → 32.400. Bayi indirimi hakediş üretmez.
- Her satırda normal fiyat, varsa Oliz, seçilen kampanya adı/etkisi ve kampanya fiyatı, maliyet, kart/nakit bayi indirimi, önerilen nakit ve kart fiyatı gösterilir; nihai nakit/kart birim fiyatını çalışan girer. Sepet altında toplam normal, toplam Oliz (varsa), toplam şirket indirimi, toplam maliyet, nakit ve kart toplamı canlı gösterilir. Floor veya kâr referansı altında uyarı verilir, kayıt engellenmez.
- Detay ekranı toplamları, komisyon snapshot'ını, durum geçmişini ve iç kâr özetini gösterir; müşteri A4 çıktısında maliyet, iç kâr ve komisyon detayı bulunmaz.
- Taslak teklif düzenlenebilir; sunuldu/kabul/lost/expired sonrası fiyat snapshot'ı değişmez. Kabul edilen tekliften rezervasyona dönüşüm retry edildiğinde aynı rezervasyon döner.
- Teklif detayında ve listede **Sil** eylemi bulunur; tüm durumlardaki teklifler çift onayla silinebilir. Rezervasyona dönüşmüş teklifte onay metni bağlı rezervasyonun silinmeyeceğini belirtir.
- Teklif detayında ve A4 çıktısında ürünün **güncel scraper ID'si** gösterilir.
- Detay ekranında "Kâr / Komisyon Özeti" kartı her zaman görünür; seçili taksitin komisyonu, kampanya/Oliz hakedişi, satır toplamı maliyet, kâr ve marjı gösterir. Oliz fiyatı olmayan tekliflerde Oliz kolonu ve hakediş satırı gizlenir. A4 müşteri çıktısında bu bilgiler yer almaz.
- Teklif detayında iki hızlı işlem vardır: "Rezervasyon Aç" teklifi kabul edildi durumuna alıp rezervasyon oluşturur; "Teslim Et (Hızlı Sat)" aynı rezervasyonu açar ve tüm satırları teslim ederek fiziksel stoktan düşer. Stok yetersizse gerekçe alanı kullanılır; işlemler tekrar edildiğinde aynı rezervasyon kullanılır.
- Listede "Excel İçe Aktar" ve "Excel Dışa Aktar" eylemleri vardır; dışa aktarılan çalışma kitabı Teklifler, Teklif Satırları ve Kâr Detayı sayfalarını içerir. İçe aktarma yalnızca taslak teklif oluşturur/günceller.

### Komisyonlar

- Aylık komisyon dönemleri listelenir; yeni dönem önceki dönemi kopyalayarak açılır, düzenlenir ve aktifleştirilir. Geçmiş dönem değişmez.
- Kanal sekmeleri POS, Ödero ve Chippin'dir. Üç kanalda da banka isteğe bağlıdır: "Genel (tüm bankalar)" satırı bankasız oranı taşır, bankaya özel satır yalnız o bankada geneli geçersiz kılar. Chippin'de genel 1 taksit (tek çekim) tüm bankalara açıktır; taksit limitleri banka ve kart tipi bazında ayarlanır. Banka seçiminde yeni banka adı girilip "Banka Ekle" ile hızlı ekleme yapılır; ad canonical gösterilir.
- Ödero için 20.000 TL altı/üstü tutar bantları Diğer grupta ayrı düzenlenir; Klima'nın Ödero oranında bant kullanılmaz.
- Matris; ürün komisyon grubu (Klima/Diğer) ve taksit kolonlarıyla oran girişi sunar. TV ayrı oran grubu değildir, Diğer oranlarını kullanır. Taksit limitleri kanal, banka, ürün grubu, kategori ve kart tipi için dönem verisi olarak düzenlenir; kategori sınırları (TV 4, telefon 3 gibi) kodda sabit değildir ve aylık değiştirilebilir.
- Limitler paneli kanal, banka/kanal, ürün grubu, kategori ve kart tipi limitlerini gösterir; banka özel limit aynı kapsamdaki bankasız genel limitin yerine geçer ve etkin üst sınır canlı önizlenir.
- Kategori komisyon grubu eşlemesi, değişiklik geçmişi ve P1 komisyon A4 listesi bulunur.
- Komisyon oranları ve taksit limitleri ayrı Excel dosyalarıyla içe/dışa aktarılır; dönem detayında döneme özel, listede tüm dönemler için export butonları bulunur.

### Ayarlar

- "Ayarlar" navigasyonunda **Bankalar** ve **Kategoriler** sekmeleri bulunur.
- Bankalar listesi ad, aktif/pasif durumu ve kullanım sayılarını (oran/limit/teklif) gösterir; tekli ve toplu ekleme (her satıra bir ad, önizlemeli), yeniden adlandırma, pasifleştirme, birleştirme ve çift onaylı silme sunar. Oran/limitlerde kullanılan bankada silme, bağlı oran/limit satırlarının da silineceği uyarısıyla yapılır; tekliflerde kullanılan banka silinemez.
- Kategoriler listesi ad, komisyon grubu (Klima/Diğer) ve kullanım sayılarını (ürün/limit) gösterir; tekli/toplu ekleme, yeniden adlandırma, grup değiştirme, birleştirme ve yalnız kullanılmayan kaydı silme sunar.
- Banka ve kategori listeleri Excel ile içe/dışa aktarılır. Banka dosyası `Banka, Aktif`; kategori dosyası `Kategori, Komisyon Grubu` kolonlarını taşır.
- Stok sayfasında ayrı "Kategori Ekle" modalı yoktur; kategori ekleme ürün detayındaki hızlı alan ve Ayarlar'dadır.
- Teklif Excel içe aktarma ekranında "Bilinmeyen bankaları otomatik oluştur" onay kutusu bulunur; varsayılan kapalıdır. Komisyon Excel importunda bilinmeyen banka otomatik oluşturulur ve önizlemede yeni olarak işaretlenir.

### Ürün Kataloğu İçe Aktarma

- CSV, Excel (.xlsx) ve scraper catalog.json dosyası yükleme; dosya tipi otomatik algılanır, desteklenen format, ID, detay, fiyat ve stok kuralları ekranda açıklanır.
- Önizleme ekranında toplam satır, yeni ürün, güncellenecek ve hatalı satır sayaçları gösterilir; tabloda Ürün ID, Tür ve Detay özeti (özellik/teknik sayısı veya JSON hatası) yer alır.
- Satır bazında karar: Yeni Ürün Aç, Güncelle veya Atla. Oliz kolonu varsa boş/`0` hücre güncellemede Oliz fiyatını otomatik temizler; "İndirimli Fiyatı Temizle" yalnızca kolon yokken manuel seçenek olarak kalır.
- Toplu kararlar: Tümünü Güncelle, Tümünü Atla, Tümünü Yeni Ürün ve Sorunluları Atla.
- Hatalı ve uyarılı satırlar görünür biçimde işaretlenir; ID güncellenecek satırlar uyarı alır. Bozuk JSON satırında ürün alanları güncellenir, mevcut detay korunur ve hata gösterilir. Önizleme onaylanmadan veritabanına yazılmaz.
- Onay tek transaction içinde atomik olarak uygulanır; sonuç özeti ürünler ekranında bildirilir.

### Rezervasyonlar

- Liste; müşteri araması, durum filtresi (Açık / Teslim edildi / İptal / Hatırlatması geciken / Tümü) ve sayfalama sunar; arama HTMX ile tabloyu yeniler. **Ürünler** sütunu ürün adlarını teslim/iptal/kısmi durum etiketiyle tek hücrede gösterir.
- Satırlar rezervasyon numarası, müşteri, tarih, hatırlatma tarihi ve durumu, özet durum (Rezerve / Kısmi süreçte / Teslim edildi / İptal) ile açık/toplam miktarı gösterir.
- Yeni rezervasyon ekranı müşteri adı (zorunlu), tarih, not ve ürün satırlarından oluşur; ürün aramasından "Ekle" ile satır eklenir, miktar satır bazında girilir ve aynı ürün ikinci kez eklenmez.
- Detay ekranı satır bazında miktar, teslim, iptal, açık miktar, durum ve işlemleri (durum değiştir, teslim et, iptal et, miktar güncelle, satır sil, satır ekle) sunar; hareket ve erteleme geçmişi açılır bölümlerde görünür. Ürün satırında ürünün **güncel scraper ID'si** gösterilir; ürün ID'si değişince eski rezervasyonlar da yeni ID'yi gösterir.
- Durum adımları opsiyoneldir ve teslimden önce geri alınabilir; teslim her aktif durumdan yapılabilir. Teslim ve iptal kendi formlarından yürütülür.
- Düşük stokta teslim, gerekçe girildiğinde onaylanır; fiziksel stok negatife düşebilir ve bu durum görünür metinle bildirilir.
- Hatırlatma rezervasyon tarihinden 13 ay sonrasına otomatik atanır; varsayılan erteleme 1 aydır ve geçmişi tutulur. Tüm satırlar kapanınca hatırlatma "Tamamlandı" olur.
- A4 çıktısı depo ve bayi kopyasını tek yazdırmada (arada sayfa sonu) ya da tek kopya olarak verir; rezervasyon listesi de A4 basılabilir.
- Listede "İçe Aktar (Excel/JSON)", "Excel Dışa Aktar" ve "JSON Dışa Aktar" eylemleri vardır; export müşteri, tarih, hatırlatma, durum, **Ürünler** ve ürün başına teslim/iptal/açık miktarlarını verir. JSON import mevcut numaraları atlar; teslim/iptal adetleri ve satır durumlarını stok hareketi oluşturmadan geri yükler.
- Ana ekranda gecikmiş ve önümüzdeki 30 gün içindeki hatırlatmalar görünür.

### Excel İçe/Dışa Aktarma

- Ürünler, Kampanyalar, Teklifler, Komisyonlar ve Rezervasyonlar için Türkçe başlıklı Excel (.xlsx) export vardır; Ürünler ayrıca CSV export/import destekler. Teklifler, rezervasyonlar ve kampanyalar JSON içe/dışa aktarmayı da destekler; CSV/Excel yedek/geçiş formatı olarak korunur.
- Yeni modüllerin import ekranlarında "Şablon İndir" bağlantısı bulunur; şablonun "Kullanım" sayfası kolonları, zorunlulukları ve kabul edilen değerleri açıklar.
- Import akışı: dosya seç → önizleme (hatalı/uyarılı satırlar üstte, yeni/güncellenecek/hatalı sayaçları) → satır veya toplu karar → tek transaction commit. Önizleme onaylanmadan veritabanına yazılmaz.
- Ürün import'unda Alış Fiyatı, Kredi Kartı Taban Fiyatı ve Nakit Taban Fiyatı güncellenebilir; boş hücre mevcut değeri korur, `-` temizler. Aktif Kampanya salt okunurdur. Ürün ID güncel ID'yi günceller, eski ID alias olarak saklanır.
- Teklif, rezervasyon ve kampanya ürün satırlarında `Ürün ID` kolonu bulunur; ID yoksa adla legacy eşleşir.
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

Kimlik doğrulama, rol yönetimi, kamera/barkod çözümleme ve Hızlı Teslim modülü v1 kapsamı dışındadır; Hızlı Teslim v2 adayıdır ve navigasyonda yer almaz.

# Cihaz Kullanım Kuralları (telefon + laptop) - YENİ GÜNCELLENECEK KURALLAR:

## Temel ilke

BayiOS iki ayrı iş için kullanılır ve arayüz buna göre öncelik verir:

- **Telefon = hızlı bakma.** Ürün bul, fiyatı/stoku/özelliği oku, teklif için fiyat ver.
- **Laptop = yönetme.** Kampanya, komisyon, import/export, ayarlar, toplu işlem, A4 çıktı.

Tüm ekranlar telefonda da çalışır; ancak "hızlı bakma" ekranları telefon için optimize edilir, "yönetme" ekranları laptop için optimize edilir ve telefonda sadece kullanılabilir kalır.

## Breakpoint'ler

| Genişlik    | Navigasyon              | Ürün listesi  |
| ----------- | ----------------------- | ------------- |
| < 1024px    | Alt sekme çubuğu        | Kart görünümü |
| 1024–1279px | Sol menü, yalnız ikon   | Tablo         |
| ≥ 1280px    | Sol menü, ikon + etiket | Tablo         |

## Navigasyon

- **Telefon:** Alt sekme çubuğu, 5 öğe: Ana Sayfa, Ürünler, Teklifler, Rezervasyonlar, Daha fazla. "Daha fazla" Kampanyalar, Stok/Sayım, Komisyonlar ve Ayarlar'ı listeler.
- **Laptop:** Sol menüde 8 öğenin hepsi (Ana Sayfa, Ürünler, Kampanyalar, Teklifler, Rezervasyonlar, Stok/Sayım, Komisyonlar, Ayarlar).
- Üst çubukta arama her ekranda sabit kalır (sticky). Arama ürün aramasına gider.
- Aktif sekme/menü öğesi `aria-current="page"` taşır; yalnız renkle değil, vurgulu arka planla da gösterilir.
- Odaklı ekranlarda (teklif formu, sayım oturumu) alt sekme çubuğu gizlenir; yerine ekranın altında sticky eylem çubuğu (Vazgeç / Kaydet) gösterilir.
- Toplu işlem çubuğu ve sticky eylem çubuğu hiçbir zaman alt sekme çubuğunun altında kalmaz; sekme çubuğunun üstüne dizilir.

## Yoğunluk

- **Telefon (ferah):** Dokunma alanları en az 44px yüksekliğinde, kart aralıkları geniş, tek sütun, metin en az 14px.
- **Laptop (sıkı):** Buton yüksekliği 36px, tablo satırları kompakt, iki sütunlu yerleşim, çok kolonlu tablolar (`data-table-scroll` ile).

## Genel bileşen kuralları

- Fiyat her zaman `38.199 TL` biçiminde, tek satırda, kırılmadan gösterilir. Önemli fiyat (Oliz) ekranın en büyük metnidir.
- Stok ve durumlar renk + metinle gösterilir ("Stok: 3", "Stokta yok"). Stok 0 ise uyarı rozeti, negatifse kırmızı + "Stok düzeltmesi gerekli".
- Uzun içerik (özellikler, teknik özellikler, geçmişler, koşullar) varsayılan **kapalı** açılır-kapanır bölümlerdedir; başlıkta adet yazar ("Teknik özellikler (24)").
- Modallar telefonda ekranın altından açılan panel (bottom sheet), laptopta ortada modal olarak açılır. İkisi de ekran dışına taşmaz, uzun içerik dikey kayar.
- İki aşamalı silme her iki cihazda aynıdır; ikinci adımda açık teyit butonu olmadan silme yapılmaz.
- Tehlikeli eylemler (Sil, Arşivle) telefonda "Diğer işlemler" altında durur; birincil eylemler önde kalır.
- Hover'a bağlı hiçbir bilgi veya eylem yoktur; her şey dokunma ile erişilebilir.
- Bir ekranda en fazla bir birincil (dolu) buton bulunur.
- İç ticari bilgiler (alış maliyeti, kâr, komisyon) telefonda ilk ekranda gösterilmez; "İç bilgiler" gibi kapalı bölümde durur. Müşteri A4 çıktısında hiçbir zaman yer almaz.

## Ekranlar: telefon ve laptop davranışı

### Ana Sayfa (dashboard)

Amaç: "Bugün ne yapmam gerekiyor?" ve "Nereye gitmem lazım?" sorularına tek bakışta cevap vermek.

- **Telefon:** Üstte arama; altında "Hatırlatmalar" kartı (gecikmiş rezervasyonlar kırmızı etiketli, önümüzdeki 30 gün normal etiketli); altında 2 sütunlu modül kartları (Ürünler, Teklifler, Rezervasyonlar, Kampanyalar...). Pasif modüller "Yakında" rozetiyle soluk gösterilir.
- **Laptop:** Hatırlatmalar solda, son teklifler ve son rezervasyonlar sağda; altında modül kartları tek sırada. Sayılar (açık teklif, açık rezervasyon, gecikmiş hatırlatma) kartların üstünde özet olarak görünür.
- Hatırlatma satırına dokunmak ilgili rezervasyonu açar.

### Ürünler (liste)

- **Telefon:** Arama kutusu ve "Ara" butonu aynı satırda, üstte sabit. Her ürün bir kart: ürün adı, kategori, Oliz fiyatı (büyük), stok rozeti. Karta dokunmak ürün detayına gider. Filtreler (durum, kategori) arama altında tek satırda, dar ekranda alt satıra geçer. Telefonda toplu seçim ve toplu işlem gizlidir.
- **Laptop:** Tablo (seçim, ürün adı + ID, kategori, normal fiyat, Oliz, stok, son fiyat değişimi, işlem). İşlem kolonu sağa sabit, satır seçimi ve alt toplu işlem çubuğu çalışır. Sayfa numarasıyla doğrudan geçiş vardır.

### Ürün Detayı

Telefon ve laptopta aynı sıra, laptopta fiyat kartı iki sütun:

1. Ürün adı, kategori rozeti, arşiv rozeti.
2. **Fiyat kartı:** Oliz fiyatı en büyük metin; normal fiyat üstü çizili; stok ve açık rezervasyon rozetleri; yanında (telefonda altında) bayi nakit taban ve kart taban fiyatı ile son güncelleme tarihi.
3. Birincil eylemler: "Teklife ekle", "Rezervasyon aç". "Diğer işlemler" altında: Stok güncelle, Düzenle, Arşivle, Sil.
4. **Aktif kampanyalar:** Ad, geçerlilik, durum, "Hediye var / yok" bayi fiyat senaryosu.
5. Kapalı bölümler: Ürün özellikleri (N), Teknik özellikler (N), Fiyat geçmişi, Stok hareketleri, İç bilgiler (alış maliyeti, ürün ID, tür, kaynak, scraper tarihi).

### Teklifler

- **Telefon:** Liste kart görünümünde (teklif no, müşteri, ürünler, durum, seçili toplam). Teklif oluşturma telefonda mümkündür ve "fiyat verme" odaklıdır: ürün ara → miktar → kampanya → önerilen nakit/kart fiyatı → fiyatı gir. Taksit seçenekleri ve Senaryo Özeti kapalı bölümlerde, sepetin üstünde. Vazgeç / Kaydet sticky eylem çubuğunda.
- **Laptop:** Liste tablo olarak. Teklif formu iki sütun: solda müşteri ve ödeme alanları, sağda sepet ve canlı toplamlar. Kâr/Komisyon özeti ve taksit karşılaştırma tablosu yan yana okunur.
- Floor veya kâr referansı altı uyarı verir, kaydı engellemez (her iki cihazda).

### Kampanyalar

- **Telefon:** Sadece okuma ve hızlı kontrol için: liste kartları, detayda koşullar (kapalı bölüm) ve hediye var/yok senaryosu. Düzenleme formu açılır ama laptop önerilir; formun üstünde bilgilendirici bir not gösterilebilir.
- **Laptop:** Tam yönetim: filtreli tablo, yeni/düzenleme formu, sürüm geçmişi, global bayi indirimi, import/export, A4 çıktı.

### Rezervasyonlar

- **Telefon:** Liste kartları (no, müşteri, hatırlatma tarihi, özet durum). Detayda satır bazında teslim et / iptal et büyük butonlarla. Yeni rezervasyon hızlı form: müşteri adı, ürün arama, miktar.
- **Laptop:** Tablo + satır bazlı işlem paneli, hareket ve erteleme geçmişi, A4 depo/bayi kopyası, import/export.

### Stok/Sayım

- **Telefon:** Sayım girişi için optimize: açık oturumlar en üstte, sayılan miktar alanı büyük, "Miktarları Kaydet" sticky çubukta. Kategori seçince liste otomatik yenilenir.
- **Laptop:** Stok özet tablosu, sayfalama, sayım oturum geçmişi, A4 sayım listesi.

### Komisyonlar

- **Telefon:** Yalnız okuma önerilir: dönem, kanal sekmeleri, oran matrisi yatay kaydırılabilir kapta. Düzenleme mümkündür fakat laptop öncelikli.
- **Laptop:** Tam yönetim: dönem kopyalama, kanal sekmeleri, matris girişi, limitler paneli, kategori-grup eşlemesi, Excel import/export.

### Ayarlar

- **Telefon ve laptop:** Bankalar ve Kategoriler sekmeleri. Telefonda liste kartları, laptopta tablo; toplu ekleme ve import/export laptopta öncelikli.

### İçe/Dışa Aktarma

- **Laptop odaklıdır.** Telefonda dosya yükleme çalışır, ancak önizleme tablosu yatay kaydırılabilir kapta gösterilir ve ekranın üstünde "Bu işlem laptopta daha rahattır" notu çıkar. Önizleme onaylanmadan hiçbir veri yazılmaz.

## Görsel dil

- Açık zemin, lacivert/indigo vurgu, sakin durum renkleri.
- Kartlar ince kenarlıklı, gölgesiz; seçili öğe dolgu yerine vurgulu kenarlık alır.
- İkonlar tek tip çizgi ikon setinden gelir; ikon tek başına anlam taşımaz, yanında etiket vardır (alt çubukta bile).
- Türkçe metin, cümle düzeni; tarihler `10.11.2026` ve `10 Kasım 2026`.
- Yazdırmada üst çubuk, sol menü, alt sekme çubuğu ve sticky çubuklar gizlenir.
- Hareket azaltma tercihine saygı gösterilir.
