# BayiOS — Product Requirements Document (PRD)

**Belge sürümü:** 1.0  
**Durum:** MVP geliştirmeye hazır ürün gereksinimleri  
**Tarih:** 4 Kasım 2026  
**Ürün:** BayiOS  
**Hedef ortam:** Windows 11 üzerinde yerel sunucu, bayi LAN/Wi-Fi ağı, mobil ve masaüstü tarayıcılar  
**Hedef eşzamanlı kullanıcı:** İlk aşamada 3–4 kişi  

---

## 1. Ürün özeti

BayiOS, bir beyaz eşya/elektronik bayiinin günlük satış, ürün, kampanya, bayi fiyatı, stok, rezervasyon, teklif ve mağazadan doğrudan teslim operasyonlarını tek bir yerel ağ uygulamasında birleştiren, mobil öncelikli bir iç operasyon sistemidir.

Uygulamanın temel amacı çalışanların bilgiyi WhatsApp fotoğrafları, dağınık Excel dosyaları, el yazısı teklifler ve ayrı not tabloları arasında aramak zorunda kalmasını azaltmaktır. Çalışan ürünün güncel normal ve şirket indirimli fiyatını, kampanya koşullarını, bayi tarafından belirlenen satış fiyatı sınırlarını ve kart komisyonu referanslarını tek ekranda görebilmelidir. Teklif ve rezervasyon kayıtları kaybolmamalı; depo ve satış çalışanları gerektiğinde A4 çıktı kullanabilmelidir.

BayiOS bir ERP/WMS/POS ikamesi değildir. Mevcut WMS veya Dynamics 365 sistemine bağlanmayacak; bu sistemlere otomatik kayıt göndermeyecektir. POS kampanya hesaplama algoritması da ilk sürümde çözülmeyecek, son milestone olarak ele alınacaktır.

### 1.1 Ürün ilkeleri

1. **Hızlı kullanım:** Çalışanın kayıt açması mevcut iş akışından daha zahmetli olmamalıdır. Zorunlu alanlar minimumda tutulur.
2. **Tek bilgi noktası:** Ürün, fiyat, kampanya, bayi fiyatı, teklif ve rezervasyon bilgileri tek uygulamada tutulur.
3. **Geçmiş kaybolmaz:** Fiyat, stok, rezervasyon ve kampanya değişiklikleri gerektiğinde geriye dönük incelenebilir.
4. **Mobil öncelik, masaüstü desteği:** Satış çalışanı telefondan kullanabilir; çıktı, toplu veri girişi ve barkod görseli içe aktarma masaüstünde de rahat çalışır.
5. **A4 ile uyum:** Depocu ve uygulama kullanmayan çalışanlar için temel operasyonlar basılabilir olmalıdır.
6. **Yerel ve bağımsız çalışma:** Uygulamanın temel işlevleri internet bağlantısı olmadan, bayi yerel ağı içinde çalışmalıdır.
7. **Açıkça tanımlı stok hareketi:** Rezervasyon oluşturulması veya servis atanması fiziksel stoktan düşmez. Stok, teslimat/kurulum tamamlandı olarak işaretlendiğinde düşer.
8. **Scraper yok:** Uygulama hiçbir web sitesini taramaz; fiyat toplamaz ve bu amaçla arka plan görevi çalıştırmaz.

### 1.2 Başarı ölçütleri

MVP'nin başarılı sayılması için:

- Çalışan bir ürünü adıyla hızlıca bulup normal fiyatı, Oliz fiyatını ve geçerli kampanya bilgisini görebilmelidir.
- Ürün kataloğu CSV/Excel dosyasından güvenli biçimde güncellenebilmelidir.
- Fiziksel stok, açık rezervasyon ve satılabilir miktar aynı ürün ekranında görülebilmelidir.
- Rezervasyon açma, müşteri teslimat istediğinde depo sürecini izleme ve tamamlandığında stoktan düşme tek kayıt üzerinden yapılmalıdır.
- Teklifler kaydedilmeli, daha sonra tekrar açılabilmeli ve A4 basılabilmelidir.
- Rezervasyon, stok sayım listesi ve teklif çıktıları uygulama dışındaki çalışanlarca kullanılabilmelidir.
- WhatsApp veya başka bir masaüstü penceresinden alınan barkod ekran görüntüsü BayiOS'a pano yapıştırma, ekran yakalama veya dosya yükleme ile aktarılabilmeli; Code 128 metni çözülebilmelidir.
- POS hesaplayıcısı, scraper veya WMS entegrasyonu olmadan MVP tamamlanabilmelidir.

---

## 2. Hedef kullanıcılar ve kullanım bağlamı

### 2.1 Kullanıcı profilleri

**Satış çalışanı**
- Ürün, fiyat, kampanya ve bayi indirimi bilgisine ulaşır.
- Teklif ve rezervasyon kaydı oluşturur.
- Müşteri teslimat istediğinde rezervasyon sürecini başlatır ve depocuyla iletişim kurar.
- Depo onayı, servis ataması ve teslimat durumlarını uygulamada günceller.
- Hızlı teslim ekranıyla müşteri adı ve barkod kaydı oluşturur.

**Depo çalışanı**
- MVP'de uygulamaya doğrudan giriş yapması beklenmez.
- Fiziksel stok sayımını mevcut çalışma şekliyle yapar.
- Rezervasyon ve sayım listelerini A4 çıktı olarak kullanabilir.
- Ürün çıkış izni ve ürün temini gibi bilgileri satış çalışanına iletir; çalışan uygulamaya işler.

**Patron / mağaza yöneticisi**
- Kampanya ve bayi fiyatı kararlarını çalışanlara iletir.
- Çalışanlar bu kararları uygulamaya manuel kaydeder.
- Ürün maliyeti, aylık banka komisyonları ve minimum kâr hedefleri izlenebilir.
- MVP'de ayrı yönetici rolü veya özel yetki sistemi bulunmaz.

**Ürünü geliştiren kişi / sistem sorumlusu**
- Ürün dosyalarının ve uygulama verilerinin bakımını yapar.
- Yedekleri ve uygulama güncellemelerini yönetir.
- İlk aşamada destek, veri aktarımı ve hata düzeltme işlerini üstlenir.

### 2.2 Kullanıcı hesabı ve yetkilendirme — MVP kararı

MVP'de kullanıcı girişi, parola, rol ve yetkilendirme sistemi **yoktur**. Uygulama bayi yerel ağına açık, iç kullanım amaçlı bir alpha sistemidir.

- İşlem formlarında “İşlemi yapan” veya “Çalışan” alanı bulunabilir; bu alan isteğe bağlıdır.
- Çalışan adı doğrulanmış kimlik değildir; yalnızca kayda eklenen açıklayıcı bilgidir.
- Uygulamaya erişebilen yerel ağ kullanıcıları MVP'de aynı işlevlere erişebilir.
- Bu nedenle sunucu internete açılmamalı, modem üzerinde port yönlendirme yapılmamalı ve tercihen misafir Wi-Fi ağından ayrılmalıdır.
- Uygulama patron tarafından beğenilip uzaktan erişime veya daha geniş kullanıma açılacaksa kimlik doğrulama, rol ve kayıt sahipliği eklenmeden internete açılmamalıdır.

---

## 3. Kapsam

### 3.1 MVP kapsamına dahil

1. Ürün kataloğu ve ürün arama.
2. CSV/Excel ürün içe aktarma ve tüm ürünleri dışa aktarma.
3. Ürün fiyat geçmişi ve CSV aktarım geçmişi.
4. Fiziksel stok, açık rezervasyon miktarı, satılabilir stok ve stok hareketleri.
5. Kategori bazlı stok sayım oturumları ve A4 sayım listeleri.
6. Rezervasyon kayıtları, çoklu ürün, durum akışı, ek PDF ve hatırlatma/erteleme.
7. Şirket kampanyaları ve bayi özel fiyat/indirim rehberi.
8. Banka ve taksit bazlı POS komisyon tablosu; minimum satış fiyatı referans hesabı.
9. Çok ürünlü teklif oluşturma, kaydetme, teklif geçmişi ve A4 çıktı.
10. Hızlı teslim kaydı: müşteri adı-soyadı, bir veya daha fazla Code 128 metni.
11. Hızlı teslim barkod resmi içe aktarma: dosya yükleme, panodan yapıştırma ve masaüstünde izinli ekran yakalama.
12. Temel ana ekran, arama ve bildirim/hatırlatma alanı.
13. Yerel ağda mobil ve masaüstü tarayıcıdan kullanım.
14. Veritabanı ve ek dosya yedekleme.

### 3.2 MVP dışında (sonraki sürüm / good-to-have)

- CSV/Excel'den gelen ürünlere göre otomatik fiyat toplama veya scraper.
- GitHub Actions scriptiyle otomatik dosya aktarımı veya API entegrasyonu. İlk sürümde dosya manuel yüklenir.
- WMS veya Dynamics 365 entegrasyonu.
- POS kampanya/indirim dağıtım hesaplayıcısı ve karma sepet algoritması.
- Birden fazla bankayı veya taksit seçeneğini tek teklifte yan yana karşılaştırma.
- E-fatura PDF/UBL-TR XML otomatik okuma, satırları ürünlere bağlama.
- Rezervasyon devretme ve işlem sorumluluğu yönetimi.
- İç bilgi tabanı/şirket wiki'si (ürün bilgisi, süreç, sık sorulan sorular ve eğitim notları). MVP'de mevcut Trilium kullanımı devam edebilir; BayiOS içinde özel wiki modülü geliştirilmez.
- Rol, kullanıcı hesabı, parola ve ayrıntılı izin sistemi.
- Uzaktan/VPN/internet üzerinden erişim.
- Çok mağaza/çok depo yönetimi.
- Filtrelenmiş ürün listesini dışa aktarma.
- Otomatik ürün arşivleme veya CSV'de bulunmayan ürünleri pasife alma.
- Otomatik müşteri SMS/WhatsApp bildirimi.
- Gelişmiş servis/randevu planlama veya servis sistemine entegrasyon.
- Barkoddan ürün kartı arama; katalogda barkod zorunlu değildir.

### 3.3 Kesinlikle yapılmayacaklar

- BayiOS içinde web scraping, fiyat botu veya web sitesi taraması.
- IP döndürme, proxy kullanma veya scraper engelini aşma davranışı.
- WMS/Dynamics sistemine otomatik stok çıkışı gönderme.
- Kullanıcının onayı olmadan başka bir masaüstü uygulamasını gizlice görüntüleme veya ekran kaydı yapma.
- Rezervasyon süresi dolduğunda rezervasyonu otomatik iptal etme.

---

## 4. Temel kavramlar ve iş kuralları

### 4.1 Ürün kimliği

- Görünen ürün adı, mevcut işleyişte çalışanların ürünü tanıması için ana arama anahtarıdır. Ürün isimleri `07325 A`, `MD 20 ...` gibi biçimlerde olabilir.
- Her ürün veritabanında değişmeyen dahili bir `product_id` alır.
- CSV'deki ürün adı metin olarak saklanır; baştaki sıfırlar korunur.
- Ürün adının değişmesi aynı ürünü otomatik olarak yeni ürün yapmamalıdır. MVP eşleştirmesinde ürün adı temel alınır; eşleşme belirsizse ön izleme ekranı kullanıcıdan karar ister.
- Ürün kataloğunda Code 128 veya EAN barkod alanı zorunlu değildir.

### 4.2 Fiyat türleri

Bir ürün için ayrı alanlar:

- **Normal fiyat:** `regular_price`.
- **Şirket/Oliz indirimli fiyatı:** `website_discounted_price`; olmayabilir.
- **Alış maliyeti:** `cost_price`; bayi tarafından bilinen, KDV dahil ve mevcut iş modelindeki 60 gün vade etkisini içeren toptan alış maliyeti olarak ele alınır.
- **Bayi nakit minimum satış fiyatı:** Patronun ürüne özel belirlediği alt sınır/referans.
- **Bayi kart minimum satış fiyatı:** Patronun ürüne özel belirlediği alt sınır/referans.
- **Hesaplanan nakit/kart referans fiyatı:** Maliyet, minimum kâr ve POS komisyonu üzerinden uygulamanın hesapladığı değer.

Bayi nakit/kart fiyatları, hesaplanan komisyon fiyatından ayrı saklanır. Çalışan patronun söylediği fiyatı hızlıca not edebilir; uygulama komisyon hesabını ayrıca gösterebilir.

### 4.3 Ürün fiyat geçmişi

- İlk kez içe aktarılan ürün için başlangıç fiyat geçmişi kaydı açılır.
- Normal veya Oliz fiyatı değiştiğinde yeni bir fiyat geçmişi kaydı oluşturulur.
- Fiyat değişmediyse her aktarımda yinelenen fiyat geçmişi kaydı oluşturulmaz.
- Ürünün son başarılı aktarımda görülme zamanı ayrıca güncellenir.
- Fiyat geçmişi; önceki ve yeni değer, aktarım/işlem türü, tarih-saat ve varsa işlemi yapan bilgisi içerir.
- Ürün CSV aktarımında dosyada olmayan ürünler silinmez veya otomatik pasife alınmaz.

### 4.4 Stok kavramları

BayiOS stok ekranında birbirinden farklı üç kavramı gösterir:

1. **Fiziksel stok:** Son fiziksel sayım, CSV aktarımı veya stok hareketlerinden sonra sistemin bildiği eldeki miktar.
2. **Açık rezervasyon:** Müşteriye satılmış, teslimatı/kurulumu henüz tamamlanmamış ürün miktarı. Bu miktar raporlanır ve fiziksel stoktan ayrı gösterilir.
3. **Satılabilir stok:** Fiziksel stoktan açık rezervasyon yükümlülükleri düşüldükten sonra kalan teorik miktar.

Varsayılan hesap:

`satilabilir_stok = max(fiziksel_stok - acik_rezervasyon_miktari, 0)`

`temin_ihtiyaci = max(acik_rezervasyon_miktari - fiziksel_stok, 0)`

Satılabilir stok sıfırsa bu ürün için yeni satış/rezervasyon teknik olarak engellenmez; ekranda temin ihtiyacı/uyarı gösterilir. Bayi ürünü başka bayiden veya başka bir kanaldan temin edebilir.

**Fiziksel stoktan düşüm zamanı:**
- Rezervasyon oluşturulunca fiziksel stok düşmez.
- Müşterinin teslimat istemesi fiziksel stok düşürmez.
- Depocunun ürün çıkışına izin vermesi fiziksel stok düşürmez.
- Servis atanması fiziksel stok düşürmez.
- Rezervasyon kalemi “Teslim edildi” (teslimat/kurulum tamamlandı) olarak işaretlendiğinde fiziksel stok düşer.
- Ürün başka bayiden temin edildiyse kaynak/temin notu rezervasyonda tutulur. Gerekirse fiziksel stoğa giriş, teslimattan önce ayrı stok hareketi olarak kaydedilir.

Açık rezervasyon miktarı, ürünün fiziksel olarak rafta ayrıldığı anlamına gelmez. Ürünler için depo tarafından fiziksel tahsis/rezervasyon yönetimi MVP'de yapılmaz.

### 4.5 Rezervasyon iş kuralı

- Rezervasyon yalnızca gerçekleşmiş ürün satışı için açılır.
- Kapora, senet veya açık hesapla rezervasyon MVP kapsamında değildir.
- Rezervasyon bir veya birden fazla ürün satırı içerir.
- Her satırda ürün ve miktar zorunludur.
- Müşteri adı-soyadı zorunludur; telefon numarası MVP'de zorunlu değildir ve ilk sürümde alınmayacaktır.
- Rezervasyon oluşturulması stoktan düşüm yapmaz.
- Rezervasyon süresi varsayılan olarak 13 ay (1 yıl 1 ay) üzerinden izlenir.
- 13 ay dolduğunda tüm çalışanların ana ekranında uyarı görünür.
- Uyarı otomatik iptal oluşturmaz.
- Çalışan müşteriyle görüştükten sonra hatırlatmayı erteleyebilir. Varsayılan erteleme 1 aydır; tarih değiştirilebilir.
- İptal edilirse açık rezervasyon miktarı azalır ve satılabilir stok hesabı yeniden yapılır; fiziksel stoktan çıkış yapılmaz.
- Bir rezervasyonda birden fazla ürün olabileceğinden teslimat/kurulum durumu satır bazında izlenir. Kısmi teslimat desteklenir.

### 4.6 Rezervasyon durumları

Rezervasyon kalemi seviyesinde durumlar:

1. `RESERVED` — Rezerveli.
2. `DELIVERY_REQUESTED` — Müşteri teslimat istedi; çalışan depocuyla iletişime geçecek/geçti.
3. `DEPOT_READY` — Depocu ürünün çıkışına izin verdi; ürün çıkış için hazır.
4. `SERVICE_ASSIGNED` — Servis ataması yapıldı; ürün henüz teslim edilmiş/kurulmuş sayılmaz.
5. `DELIVERED` — Teslimat/kurulum tamamlandı; fiziksel stoktan düşüm yapılır.
6. `CANCELLED` — Rezervasyon satırı iptal edildi; fiziksel stoktan düşüm yapılmaz.

- Servis tarihi isteğe bağlıdır.
- Başka bayiden temin notu serbest metindir.
- Durum değişiklikleri tarihçeye yazılır.
- Rezervasyon üst kaydının durumu, satırların durumlarına göre özetlenir; karma durumlarda “Kısmi süreçte” gibi bir özet gösterilir.
- `DELIVERED` durumuna geçen miktar için bir kez stok çıkış hareketi oluşturulur. Aynı satır tekrar kaydedilirse ikinci kez stok düşülmemelidir.
- Teslim edildi olarak işaretleme miktar bazında olmalıdır; örneğin 2 adetten 1'i teslim edildiyse kalan 1 adet açık kalmalıdır.

### 4.7 Kampanya ve bayi indirimi kuralları

MVP, kampanya rehberi ve fiyat senaryosu gösterir; tam sepet/POS kampanya algoritması değildir.

Kampanya tipleri:
- Ürün veya seçili ürün grubu indirimi.
- Bir ürün alana ikinci üründe yüzde/sabit tutar indirim.
- Bir ürün yanında hediye ürün.
- Birden fazla ürün birlikte alındığında kampanya.
- Genel kampanya veya dışarıdan gelen indirim kodu/açıklaması.
- Ürüne özel bayi indirimi veya bayi tarafından belirlenmiş özel fiyat.

Kampanya kaydı aşağıdaki alanları destekler:
- Kampanya adı ve açıklaması.
- Başlangıç/bitiş tarihi.
- Genel kampanya mı, ürün/ürün grubu kampanyası mı?
- Şart olan ürün/ürünler.
- İndirimin veya hediyenin uygulandığı ürün.
- İndirim türü: yüzde, sabit tutar, özel fiyat, hediye veya açıklama.
- Fiyat tabanı: normal fiyat veya şirket/Oliz indirimli fiyatı.
- Hediye seçeneği ve hediye istemeyen müşteri için alternatif fiyat davranışı.
- Çalışanın göreceği kısa açıklama/not.

**Hediye örneği — zorunlu davranış:**
- Normal fiyat: 25.999 TL.
- Oliz fiyatı: 23.999 TL.
- Ürün yanında hediye veriliyorsa bayi indirimi normal fiyat üzerinden hesaplanır.
- Müşteri hediyeyi istemezse bayi indirimi Oliz fiyatı üzerinden hesaplanır.
- Varsayılan bayi indirimi %10 gösterilir; çalışan gerekli durumda oranı değiştirebilir.
- Bu örnekte hediye ile senaryo: 25.999 × 0,90 = 23.399,10 TL.
- Hediye olmadan senaryo: 23.999 × 0,90 = 21.599,10 TL.

Genel bayi indirimi sabit bir oran değildir. Uygulama %10'u varsayılan öneri olarak gösterebilir; çalışan patronun yönlendirmesiyle oranı değiştirebilir. MVP'de rol olmadığı için oranı %10 ile teknik olarak sınırlamayız.

Özel ürünlerde yüzde yerine doğrudan bayi minimum nakit ve kart satış fiyatı girilir. Bu değerler aylık veya ihtiyaç oldukça değişebilir ve tarihçeli tutulur.

### 4.8 Komisyon ve minimum fiyat hesabı

- Birden fazla banka desteklenir.
- Her bankada taksit seçeneği başına komisyon yüzdesi tutulur.
- Komisyon oranları elle girilir ve dönem/başlangıç tarihi ile güncellenebilir.
- MVP'de çalışan teklif için tek banka ve tek taksit seçeneği belirler.
- Birden fazla banka/taksit alternatifini aynı anda kıyaslama sonraki sürümdür.
- Minimum kâr hem tutar (TL) hem oran (%) biçiminde tanımlanabilir.
- Varsayılan minimum kâr değeri önceden varsayılmaz; ürün veya teklif için ayarlanmadıysa sistem “minimum kâr hedefi tanımlı değil” uyarısı verir.

Basitleştirilmiş hesap:

`hedef_tutar = maliyet + hedef_kar_tutari`

`kart_basa_bas_fiyat = hedef_tutar / (1 - komisyon_orani)`

Hedef kâr oranı seçildiyse:

`hedef_kar_tutari = maliyet × hedef_kar_orani`

Bu hesap, POS komisyonu kesintisi sonrasında maliyet + seçilen hedef kârı karşılamaya yönelik referans niteliğindedir. Vergi, genel gider, kampanya istisnası ve muhasebe etkilerinin tamamını kapsayan resmi muhasebe hesabı olduğu iddia edilmez.

- Komisyon oranı yüzde olarak saklanır; hesaplamada ondalık değere çevrilir.
- Para hesaplarında binary floating point kullanılmaz; `Decimal`/sabit hassasiyetli decimal veri tipi kullanılır.
- Yuvarlama yöntemi ekranda/çıktıda tutarlı olmalıdır; kuruş hassasiyeti saklanır, TL sunumu iki ondalık basamak gösterebilir.
- Hesaplanan fiyat ile patronun girdiği bayi minimum fiyatı ayrı gösterilir. MVP'de otomatik fiyat engeli uygulanmaz; uyarı ve karşılaştırma gösterilir.
- Nakit fiyatında POS komisyonu yoktur; bayi nakit alt sınırı ayrıca saklanır.

---

## 5. Fonksiyonel gereksinimler

Öncelik tanımları:
- **P0:** MVP için zorunlu.
- **P1:** MVP içinde mümkünse; çekirdek akışın önüne geçmez.
- **P2:** Sonraki sürüm.

### 5.1 Ana ekran ve navigasyon

**FR-HOME-01 (P0):** Ana ekranda hızlı erişim kartları bulunmalıdır: Ürünler, Kampanyalar, Teklifler, Rezervasyonlar, Stok/Sayım, Hızlı Teslim, Komisyonlar.

**FR-HOME-02 (P0):** Yaklaşan/gecikmiş rezervasyon hatırlatmaları tüm kullanıcılara gösterilmelidir.

**FR-HOME-03 (P0):** Ürün arama alanı mobil ekranda kolay erişilebilir olmalıdır.

**FR-HOME-04 (P1):** Son açılan teklifler, son rezervasyonlar ve son ürün güncellemeleri ana ekranda gösterilebilir.

**FR-HOME-05 (P0):** Uygulama küçük ekranlarda yatay kaydırma gerektirmeden temel iş akışlarını sunmalıdır.

### 5.2 Ürün kataloğu

**FR-PROD-01 (P0):** Ürün listesi ürün adına göre aranabilmelidir; arama baştaki sıfırları korumalıdır.

**FR-PROD-02 (P0):** Ürün detayında normal fiyat, Oliz fiyatı, alış maliyeti, fiziksel stok, açık rezervasyon, satılabilir stok ve temin ihtiyacı gösterilmelidir.

**FR-PROD-03 (P0):** Ürün detayında aktif kampanyalar ve bayi özel fiyatları gösterilmelidir.

**FR-PROD-04 (P0):** Ürün oluşturma/güncelleme manuel olarak yapılabilmelidir.

**FR-PROD-05 (P0):** CSV ve Excel dosyasıyla toplu ürün aktarımı desteklenmelidir.

**FR-PROD-06 (P0):** Aktarım öncesinde dosya ön izlemesi gösterilmeli; sütun eşleştirme veya otomatik tanıma sunulmalıdır.

**FR-PROD-07 (P0):** Aktarım ön izlemesinde yeni ürün, güncellenecek ürün, değişecek fiyat, stok farkı ve hatalı satırlar ayrıştırılmalıdır.

**FR-PROD-08 (P0):** Kullanıcı onayı olmadan aktarım veritabanına uygulanmamalıdır.

**FR-PROD-09 (P0):** Eşleştirme öncelikle ürün adına dayanmalıdır. Belirsiz eşleşmeler otomatik birleştirilmemeli, kullanıcıya gösterilmelidir.

**FR-PROD-10 (P0):** CSV/Excel aktarımında bulunmayan ürünler silinmemeli veya otomatik arşivlenmemelidir.

**FR-PROD-11 (P0):** Boş `quantity` hücresi mevcut fiziksel stok değerini değiştirmemelidir; `0` değeri fiziksel stoğu sıfırlamalıdır.

**FR-PROD-12 (P0):** `quantity` değeri fiziksel stok olarak yorumlanmalıdır. Her değişiklik stok hareketi geçmişine kaydedilmelidir.

**FR-PROD-13 (P0):** CSV dışa aktarım ve Excel dışa aktarım tüm ürünleri kapsamalıdır.

**FR-PROD-14 (P1):** Filtrelenmiş ürün sonuçlarını dışa aktarma eklenebilir.

**FR-PROD-15 (P0):** Son başarılı içe aktarma tarihi ürün/aktarımı görünümünde gösterilmelidir.

**FR-PROD-16 (P0):** Son fiyat değişikliği tarihi ve son görülme/aktarılma tarihi birbirinden ayrı gösterilmelidir.

**FR-PROD-17 (P0):** Bir ürünün fiyatı değişmediğinde yinelenen fiyat geçmişi kaydı oluşturulmamalıdır.

**FR-PROD-18 (P0):** İlk kez aktarılan ürün için başlangıç fiyat ve stok geçmişi oluşturulmalıdır.

**FR-PROD-19 (P0):** Ürün fiyat ve maliyet değerleri TL para biriminde tutulmalıdır; ileride çoklu para birimi gereksinimi yoktur.

**Önerilen örnek CSV şeması:**

```csv
product_name,regular_price,website_discounted_price,quantity
07325 A,38099,33099,5
09325 A,42199,37199,
09470 HP,52899,47899,0
09570 HP,59499,49499,2
09605,38399,33399,1
1002 KMP HA,55599,,1
```

- `product_name`: metin.
- `regular_price`: TL cinsinden sayı.
- `website_discounted_price`: boş olabilir; boş değer mevcut Oliz fiyatını koruma mı yoksa temizleme mi davranışı aktarım ekranında açıkça seçilmelidir. MVP varsayılanı: boş hücre mevcut değeri korur; fiyatı kaldırmak için ayrı “indirimli fiyatı temizle” seçeneği gerekir.
- `quantity`: fiziksel stok; boşsa değiştirme, 0 ise sıfırla.
- Dosya başlıkları farklıysa sütun eşleştirme ekranı kullanılır.
- Ondalık/ayraç ve binlik ayraç formatları aktarım ön izlemesinde doğrulanmalıdır.

### 5.3 Fiyat ve bayi fiyatı geçmişi

**FR-PRICE-01 (P0):** Normal ve Oliz fiyatları her ürün için ayrı saklanmalıdır.

**FR-PRICE-02 (P0):** Alış maliyeti ürün detayında saklanmalı ve çalışanlara görünmelidir.

**FR-PRICE-03 (P0):** Nakit ve kart bayi minimum satış fiyatları birbirinden ayrı saklanmalıdır.

**FR-PRICE-04 (P0):** Bayi fiyatı değişikliklerinde eski değer, yeni değer, tarih-saat ve isteğe bağlı çalışan adı kaydedilmelidir.

**FR-PRICE-05 (P0):** Ürün detayında son fiyat güncellemesi ve fiyat geçmişi görüntülenmelidir.

**FR-PRICE-06 (P0):** Bayi minimum satış fiyatı ile komisyon hesabından çıkan fiyat farklı alanlarda gösterilmelidir.

### 5.4 Kampanya rehberi

**FR-CAMP-01 (P0):** Kampanya oluşturma, düzenleme ve arşivleme ekranı olmalıdır.

**FR-CAMP-02 (P0):** Kampanyalar genel kampanya veya ürün/ürün grubu kampanyası olarak sınıflandırılmalıdır.

**FR-CAMP-03 (P0):** Kampanyaya başlangıç ve bitiş tarihi girilebilmelidir.

**FR-CAMP-04 (P0):** Kampanya, şart olan ürün(ler) ve fayda/indirim uygulanan ürün(ler) ile ilişkilendirilebilmelidir.

**FR-CAMP-05 (P0):** Hediye ürün kampanyası tanımlanabilmelidir.

**FR-CAMP-06 (P0):** Kampanya ekranı hediye var/yok senaryolarını açıklamalı ve ilgili fiyat tabanını belirtmelidir.

**FR-CAMP-07 (P0):** Hediye varsa bayi indirimi normal fiyat üzerinden; hediye yoksa ve Oliz fiyatı varsa Oliz fiyatı üzerinden örneklenmelidir.

**FR-CAMP-08 (P0):** Genel bayi indirimi varsayılan %10 olarak gösterilmeli; çalışan bu oranı değiştirebilmelidir.

**FR-CAMP-09 (P0):** Uygulama bayi indirimi oranını sabit %10 ile sınırlandırmamalıdır; patronun yönlendirmesiyle %15 vb. girilebilmelidir.

**FR-CAMP-10 (P0):** Ürüne özel bayi nakit minimum fiyatı ve kart minimum fiyatı girilebilmelidir.

**FR-CAMP-11 (P0):** Kampanya listesi genel/ürün bazlı, aktif/geçmiş ve tarih aralığına göre filtrelenebilmelidir.

**FR-CAMP-12 (P0):** Kampanya düzenlemeleri tarihçeli tutulmalıdır; eski kampanya şartları geçmiş teklifleri değiştirmemelidir.

**FR-CAMP-13 (P0):** Çalışan ürün detayına geldiğinde ürünle ilişkili aktif kampanyaları görmelidir.

**FR-CAMP-14 (P1):** Kampanya rehberi A4 çıktısı alınabilmelidir.

**FR-CAMP-15 (P2):** Çok ürünlü sepet için kampanyaların otomatik uygulanması ve indirim dağıtımı POS milestone'unda ele alınmalıdır.

### 5.5 Banka komisyonları ve fiyat referansı

**FR-FIN-01 (P0):** Banka tanımlanabilmelidir.

**FR-FIN-02 (P0):** Her banka için taksit sayısı ve komisyon oranı girilebilmelidir.

**FR-FIN-03 (P0):** Komisyon oranları değiştiğinde eski dönem bilgisi korunmalıdır; yeni oranlar yürürlük tarihiyle kaydedilmelidir.

**FR-FIN-04 (P0):** Bir teklif/hesap ekranında tek banka ve tek taksit seçilebilmelidir.

**FR-FIN-05 (P0):** Ürün maliyeti üzerinden hedef kâr TL veya yüzde olarak belirlenebilmelidir.

**FR-FIN-06 (P0):** Hedef kâr ayarı tanımlı değilse sistem bunu açıkça belirtmeli; sıfır kâr hedefiyle hesap yapıldığı izlenimi oluşturmamalıdır.

**FR-FIN-07 (P0):** Kart komisyonu sonrası hedef maliyet+kârı karşılayan referans satış fiyatı hesaplanmalıdır.

**FR-FIN-08 (P0):** Nakit ve kart referans fiyatları ayrı gösterilmelidir.

**FR-FIN-09 (P0):** Manuel girilmiş bayi minimum fiyatı ile hesaplanan fiyat karşılaştırılmalıdır.

**FR-FIN-10 (P0):** Komisyon hesabı fiyatı otomatik değiştirmemeli; yalnızca bilgi ve uyarı sağlamalıdır.

**FR-FIN-11 (P1):** Banka komisyonlarının A4 listesi alınabilmelidir.

**FR-FIN-12 (P2):** Birden fazla banka/taksit seçeneğini yan yana karşılaştırma eklenebilir.

### 5.6 Teklifler

**FR-OFFER-01 (P0):** Bir teklife birden fazla ürün ve miktar eklenebilmelidir.

**FR-OFFER-02 (P0):** Teklifte ürün, miktar, normal fiyat, varsa Oliz fiyatı ve teklif için seçilen birim fiyat saklanmalıdır.

**FR-OFFER-03 (P0):** Teklifte nakit satış fiyatı ve kart satış fiyatı ayrı girilebilmelidir.

**FR-OFFER-04 (P0):** Kart fiyatı için banka ve taksit sayısı seçilebilmelidir.

**FR-OFFER-05 (P0):** Seçilen banka/taksit komisyonu ve hesaplanan referans minimum fiyat teklif ekranında gösterilmelidir.

**FR-OFFER-06 (P0):** Teklif oluşturulduğu andaki ürün fiyatı, bayi fiyatı, kampanya açıklaması, komisyon oranı ve teklif satırları snapshot olarak saklanmalıdır. Sonradan ürün fiyatı değişince eski teklif değişmemelidir.

**FR-OFFER-07 (P0):** Teklif kaydedilmeli ve teklif listesinde daha sonra tekrar bulunabilmelidir.

**FR-OFFER-08 (P0):** Teklifte müşteri adı ve açıklama/not alanı bulunmalıdır; MVP'de telefon zorunlu değildir.

**FR-OFFER-09 (P0):** Teklif durumu izlenebilmelidir: Taslak, Müşteriye sunuldu, Kabul edildi, Kaybedildi/Geçersiz.

**FR-OFFER-10 (P0):** Teklifin A4 çıktısı alınabilmelidir.

**FR-OFFER-11 (P1):** Kabul edilmiş tekliften rezervasyon oluşturma kolay yolu eklenmelidir; tekrar ürün girişi gerektirmemelidir.

**FR-OFFER-12 (P1):** Teklif için takip tarihi/notu eklenebilmelidir.

### 5.7 Rezervasyonlar

**FR-RES-01 (P0):** Rezervasyon oluşturmak için müşteri adı-soyadı zorunlu olmalıdır.

**FR-RES-02 (P0):** Rezervasyona bir veya birden fazla ürün ve miktar eklenebilmelidir.

**FR-RES-03 (P0):** Rezervasyon tarihi otomatik atanmalıdır; kullanıcı gerekirse düzeltebilmelidir.

**FR-RES-04 (P0):** Çalışan adı isteğe bağlı olmalıdır.

**FR-RES-05 (P0):** Rezervasyona not ve PDF eklenebilmelidir.

**FR-RES-06 (P0):** Rezervasyon oluşturulurken kapora, senet veya açık hesap akışı sunulmamalıdır.

**FR-RES-07 (P0):** Rezervasyonun 13 aylık takip tarihi otomatik hesaplanmalıdır.

**FR-RES-08 (P0):** Gecikmiş rezervasyon tüm çalışanların ana ekranında görünmelidir.

**FR-RES-09 (P0):** Hatırlatma tarihi çalışan tarafından ertelenebilmelidir; varsayılan yeni tarih bir ay sonrası olmalıdır.

**FR-RES-10 (P0):** Erteleme notu ve önceki hatırlatma tarihleri geçmişte tutulmalıdır.

**FR-RES-11 (P0):** Rezervasyon otomatik iptal edilmemelidir.

**FR-RES-12 (P0):** Müşteri teslimat istediğinde ilgili rezervasyon satırı `DELIVERY_REQUESTED` durumuna alınabilmelidir.

**FR-RES-13 (P0):** Depocu ürün çıkışına izin verdiğinde satır `DEPOT_READY` olarak işaretlenebilmelidir.

**FR-RES-14 (P0):** Servis ataması yapılınca satır `SERVICE_ASSIGNED` durumuna alınabilmelidir.

**FR-RES-15 (P0):** Servis tarihi isteğe bağlı olmalıdır.

**FR-RES-16 (P0):** Teslimat/kurulum tamamlandığında satır `DELIVERED` olarak işaretlenmelidir.

**FR-RES-17 (P0):** Fiziksel stok çıkışı yalnızca teslim edilen miktar kadar ve `DELIVERED` geçişinde yapılmalıdır.

**FR-RES-18 (P0):** Aynı teslimat geçişi tekrarlanırsa çift stok düşümü engellenmelidir.

**FR-RES-19 (P0):** Bir rezervasyonda kısmi teslimat desteklenmelidir.

**FR-RES-20 (P0):** Rezervasyona bağlı başka bayiden temin bilgisi serbest metin olarak girilebilmelidir.

**FR-RES-21 (P0):** İptal edilen miktar açık rezervasyon toplamından çıkarılmalı; fiziksel stoktan çıkış yapılmamalıdır.

**FR-RES-22 (P0):** Rezervasyon durum değişiklikleri tarihçeye kaydedilmelidir.

**FR-RES-23 (P0):** Rezervasyon detayı ve rezervasyon listesi A4 basılabilmelidir.

**FR-RES-24 (P0):** Rezervasyon çıktısında depo ve bayi için iki ayrı kopya seçeneği bulunmalıdır; logo zorunlu değildir.

**FR-RES-25 (P0):** Rezervasyon ekindeki PDF tarayıcı içinde görüntülenebilmelidir.

**FR-RES-26 (P1):** Rezervasyon başka bir çalışana devredilebilmelidir; rol/hesap sistemi gerektirmez.

**FR-RES-27 (P2):** PDF veya e-fatura dosyasından otomatik alan/ürün satırı çıkarma eklenebilir.

### 5.8 Stok sayımı ve stok hareketleri

**FR-STOCK-01 (P0):** Ürün stok özeti fiziksel stok, açık rezervasyon, satılabilir stok ve temin ihtiyacını göstermelidir.

**FR-STOCK-02 (P0):** Açık rezervasyon fiziksel stoktan hemen düşmemelidir.

**FR-STOCK-03 (P0):** Teslim edildi olarak işaretlenen miktar fiziksel stoktan düşmelidir.

**FR-STOCK-04 (P0):** CSV içe aktarımındaki dolu quantity değeri fiziksel stok miktarını güncellemelidir.

**FR-STOCK-05 (P0):** CSV quantity boşsa stok değişmemelidir; sıfırsa stok sıfırlanmalıdır.

**FR-STOCK-06 (P0):** CSV stok değişikliği bir stok hareketi olarak geçmişe kaydedilmelidir.

**FR-STOCK-07 (P0):** Kategori seçerek stok sayım oturumu açılabilmelidir.

**FR-STOCK-08 (P0):** Sayım listesi ürün adı, sistemdeki fiziksel stok, sayılan miktar ve fark alanlarını içermelidir.

**FR-STOCK-09 (P0):** Sayım tamamlandığında farklar kullanıcıya gösterilmeli ve onayla stok düzeltmesi hareketi olarak kaydedilmelidir.

**FR-STOCK-10 (P0):** Sayım oturumunun açılış zamanı, sayım zamanı, tamamlayan çalışan adı (isteğe bağlı) ve satır değişiklikleri tutulmalıdır.

**FR-STOCK-11 (P0):** A4 sayım listesi kategori bazlı basılabilmelidir.

**FR-STOCK-12 (P0):** Ürün hareket geçmişinde CSV güncellemesi, sayım düzeltmesi ve rezervasyon teslim çıkışı ayırt edilebilmelidir.

**FR-STOCK-13 (P0):** Stok hareketleri doğrudan silinmemeli; yanlış hareket düzeltme/ters hareket ile giderilmelidir.

**FR-STOCK-14 (P1):** Sayım oturumu kaydedildikten sonra farklı çalışan tarafından sonuç girilebilmesi kolaylaştırılabilir.

### 5.9 Hızlı teslim ve Code 128

**FR-QUICK-01 (P0):** Hızlı Teslim ekranında müşteri adı-soyadı zorunlu olmalıdır.

**FR-QUICK-02 (P0):** Bir teslim kaydına bir veya birden fazla barkod metni eklenebilmelidir.

**FR-QUICK-03 (P0):** Barkod görüntüsünden Code 128 metni otomatik çözümlenmelidir.

**FR-QUICK-04 (P0):** Çözülen barkod tam ve değiştirilmeden saklanmalıdır; baş/son haneler atılmamalıdır.

**FR-QUICK-05 (P0):** Her barkod metni tek tek kopyalanabilmelidir.

**FR-QUICK-06 (P0):** Hızlı teslim kaydı ve barkod çözüm zamanı geçmişte saklanmalıdır.

**FR-QUICK-07 (P0):** Masaüstünde resim dosyası yükleme desteklenmelidir.

**FR-QUICK-08 (P0):** Masaüstünde panodan ekran görüntüsü yapıştırma (`Ctrl+V`) desteklenmelidir.

**FR-QUICK-09 (P0):** Masaüstünde “Ekran görüntüsü al” akışı bulunmalıdır. Kullanıcı işletim sistemi/tarayıcı ekran paylaşım penceresinden ekranı, pencereyi veya tarayıcı sekmesini açıkça seçer; uygulama yalnızca kullanıcı onayıyla tek görüntü karesi yakalar ve paylaşım akışını hemen durdurur.

**FR-QUICK-10 (P0):** Ekran yakalama çalışmazsa dosya yükleme ve pano yapıştırma alternatifleri kullanılabilmelidir.

**FR-QUICK-11 (P0):** Mobil cihazlarda kamera veya fotoğraf galerisi üzerinden görüntü seçimi desteklenmelidir.

**FR-QUICK-12 (P0):** Decoder tek barkod bulamazsa kullanıcıya hata/yeniden deneme sunmalı; hatalı veya belirsiz sonucu sessizce kaydetmemelidir.

**FR-QUICK-13 (P0):** Kullanıcı çözülen metni doğrulayıp kaydetmelidir.

**FR-QUICK-14 (P0):** Hızlı teslim kaydı, WMS'de işlem yapıldığı anlamına gelmemelidir. Ekranda “WMS çıkışı bu uygulamada yapılmaz” açıklaması bulunmalıdır.

**Ekran görüntüsü güvenlik/uygulama notu:** Tarayıcı, WhatsApp penceresini kullanıcı izni olmadan veya gizlice okuyamaz. Ekran yakalama düğmesi tarayıcının izin penceresini açar; kullanıcı yakalanacak pencere/sekme/ekranı seçer. Alternatif hızlı akış Windows `Win + Shift + S` ile ekran alıntısı → BayiOS'a dönüp `Ctrl + V` yapıştırmadır. Uygulama sürekli ekran kaydı tutmaz.

### 5.10 A4 ve PDF çıktıları

**FR-PRINT-01 (P0):** Rezervasyon listesi ve detayları A4 çıktısı verebilmelidir.

**FR-PRINT-02 (P0):** Rezervasyon çıktısı depo kopyası ve bayi kopyası olarak iki biçimde alınabilmelidir.

**FR-PRINT-03 (P0):** Kategori bazlı stok sayım/ürün listesi A4 çıktısı verebilmelidir.

**FR-PRINT-04 (P0):** Teklif A4 çıktısı verebilmelidir.

**FR-PRINT-05 (P0):** Çıktılar sade, siyah-beyaz yazıcıda okunabilir ve logo gerektirmeyen biçimde tasarlanmalıdır.

**FR-PRINT-06 (P0):** Çıktılarda tarih, ürün adı, miktar ve gerekli müşteri/teklif bilgileri bulunmalıdır.

**FR-PRINT-07 (P0):** Çıktı şablonlarında gereksiz navigasyon, buton, arka plan rengi ve ekran kartları basılmamalıdır.

**FR-PRINT-08 (P0):** Tarayıcının yazdırma ekranından PDF'ye kaydetme desteklenmelidir.

### 5.11 PDF ekleri

**FR-FILE-01 (P0):** Rezervasyona PDF dosyası eklenebilmelidir.

**FR-FILE-02 (P0):** Eklenen PDF rezervasyon detayında tarayıcı içinde görüntülenebilmelidir.

**FR-FILE-03 (P0):** Dosya boyutu ve dosya türü için konfigüre edilebilir sınır olmalıdır.

**FR-FILE-04 (P0):** Dosya adı, boyut, eklenme zamanı ve bağlı olduğu kayıt veritabanında tutulmalıdır.

**FR-FILE-05 (P0):** Dosyalar uygulama veritabanı dışında kontrollü bir dosya dizininde saklanmalı ve yedeklemeye dahil edilmelidir.

**FR-FILE-06 (P2):** PDF/UBL-TR XML içeriğinden otomatik müşteri/ürün/fatura alanı çıkarma sonraki sürümde ele alınmalıdır.

---

## 6. Ekran haritası ve ana kullanıcı akışları

### 6.1 Önerilen navigasyon

Mobil alt navigasyon veya sade yan menü:

1. Ana Sayfa
2. Ürünler
3. Kampanyalar
4. Teklifler
5. Rezervasyonlar
6. Stok / Sayım
7. Hızlı Teslim
8. Komisyonlar / Ayarlar

Ekranların adları kısa ve çalışanların alışık olduğu terimlerle yazılmalıdır.

### 6.2 Ürün bulma akışı

1. Çalışan ana ekrandaki arama alanına ürün adını yazar.
2. Arama sonucu ürün kartını gösterir.
3. Ürün kartında normal fiyat, varsa Oliz fiyatı, maliyet, fiziksel stok ve açık rezervasyon özeti görünür.
4. Ürün detayında kampanyalar, bayi nakit/kart minimum fiyatı, komisyon referansı ve fiyat geçmişi görülebilir.
5. Çalışan ürün ekranından yeni teklif veya rezervasyon başlatabilir.

### 6.3 CSV/Excel ürün güncelleme akışı

1. Çalışan dosyayı seçer.
2. Sistem başlıkları tanır veya sütun eşleştirme ekranını açar.
3. Sistem yeni ürünleri, güncellenecek kayıtları, fiyat değişikliklerini, stok farklarını ve hatalı satırları gösterir.
4. Boş quantity alanları mevcut stoğu korur; 0 sıfır stok anlamına gelir.
5. Çalışan aktarımı onaylar.
6. Sistem aktarım partisi oluşturur; fiyat ve stok geçmişini gerekli olduğunda kaydeder.
7. Aktarım özeti gösterilir ve hata satırları indirilebilir/görüntülenebilir.

### 6.4 Kampanya kaydetme akışı

1. Çalışan Kampanyalar ekranından yeni kampanya açar.
2. Genel veya ürün bazlı tip seçer.
3. Kampanya adı, açıklama ve geçerlilik tarihlerini girer.
4. İlgili ürünleri, şartları, hediye/indirim türünü tanımlar.
5. Fiyat tabanını (normal/Oliz) ve hediye var/yok davranışını seçer.
6. Kaydeder.
7. İlgili ürün sayfasında kampanya görünür.

### 6.5 Teklif hazırlama akışı

1. Yeni teklif açılır; müşteri adı isteğe bağlı girilir.
2. Bir veya daha fazla ürün ve miktar eklenir.
3. Her kalemde teklif fiyatı ve varsa kampanya açıklaması gösterilir.
4. Teklif nakit veya kart olarak fiyatlandırılır.
5. Kart seçildiyse tek banka ve taksit seçilir; komisyon ve minimum referans fiyat görünür.
6. Çalışan gerçek teklif fiyatını kaydeder.
7. Teklif durumu “Müşteriye sunuldu” yapılabilir.
8. Teklif kaydedilir ve A4 yazdırılır.
9. Teklif kabul edilirse (P1) rezervasyona dönüştürülür.

### 6.6 Rezervasyon oluşturma akışı

1. Müşteri adı-soyadı girilir.
2. Bir veya daha fazla ürün/miktar eklenir.
3. Rezervasyon tarihi otomatik gelir.
4. İsteğe bağlı çalışan adı, not ve PDF eklenir.
5. Kaydet denir.
6. Açık rezervasyon miktarı güncellenir; fiziksel stok değişmez.
7. Varsayılan 13 aylık hatırlatma tarihi hesaplanır.
8. Rezervasyon detay ve liste A4 basılabilir.

### 6.7 Rezervasyon teslimat/kurulum akışı

1. Müşteri arar ve ürünlerini istediğini belirtir.
2. Çalışan ilgili kalemleri `DELIVERY_REQUESTED` yapar ve depocuyla iletişime geçer.
3. Depocu ürün çıkışına izin verirse çalışan `DEPOT_READY` yapar. Ürün kendi depoda yoksa başka bayiden temin notu eklenebilir.
4. Servis atandığında `SERVICE_ASSIGNED` yapılır; servis tarihi isteğe bağlıdır.
5. Servis/teslimat/kurulum tamamlandığında çalışan ilgili miktarı `DELIVERED` yapar.
6. BayiOS o miktar kadar fiziksel stok çıkış hareketi oluşturur.
7. Açık rezervasyon miktarı azalır ve satılabilir stok yeniden hesaplanır.
8. Tüm satırlar tamamlandığında rezervasyon “Teslim edildi” olarak özetlenir.

### 6.8 Stok sayımı akışı

1. Çalışan kategori seçer ve sayım oturumu açar.
2. Sistem o kategorideki ürünlerin mevcut fiziksel stoklarını listeler.
3. A4 sayım listesi alınabilir.
4. Depocu/çalışan sayılan miktarları kâğıttan veya doğrudan telefondan/bilgisayardan girer.
5. Sistem farkları hesaplar.
6. Çalışan farkları kontrol edip onaylar.
7. Stok düzeltmeleri hareket olarak uygulanır.
8. Sayım oturumu kapanır; önceki değerler korunur.

### 6.9 Hızlı Teslim barkod akışı

**Masaüstü – pano:**
1. WhatsApp Web veya masaüstü uygulamasında barkod fotoğrafı açılır.
2. Windows ekran alıntısı (`Win + Shift + S`) ile barkod bölgesi panoya alınır.
3. Çalışan BayiOS Hızlı Teslim ekranına geçer.
4. Görsel alanına `Ctrl + V` yapıştırır.
5. Code 128 çözülür ve tam barkod numarası gösterilir.
6. Çalışan sonucu doğrular, müşteri adını girer ve kaydeder.

**Masaüstü – ekran yakalama:**
1. Çalışan “Ekran görüntüsü al” düğmesine basar.
2. Tarayıcı ekran paylaşım penceresinden WhatsApp sekmesini/penceresini veya ekranı seçer.
3. BayiOS tek kare yakalar, aktarımı durdurur ve barkodu çözer.
4. Çalışan sonucu doğrular ve kaydeder.

**Mobil:**
1. Fotoğraf çek veya galeriden seç.
2. Tek Code 128 barkod çöz.
3. Tam metni doğrula.
4. Müşteri adı ve kayıt bilgisiyle sakla.

---

## 7. Veri modeli (önerilen)

Aşağıdaki model ilişkisel PostgreSQL yapısı için başlangıç önerisidir. Alan isimleri geliştirme sırasında standartlaştırılabilir; iş kuralları korunmalıdır.

### 7.1 Ortak tablolar

**products**
- `id` (UUID/BigInt, PK)
- `product_name` (TEXT, gerekli; arama indeksi)
- `regular_price` (NUMERIC)
- `website_discounted_price` (NUMERIC, nullable)
- `cost_price` (NUMERIC, nullable)
- `physical_stock` (NUMERIC/INTEGER, default 0)
- `category_id` (nullable)
- `is_archived` (boolean, default false; MVP'de otomatik değiştirilmez)
- `created_at`, `updated_at`, `last_seen_at`
- `last_price_changed_at`

**product_categories**
- `id`, `name`, `created_at`, `updated_at`

**product_price_history**
- `id`, `product_id`
- `field_name` (`regular_price`, `website_discounted_price`, `cost_price`)
- `old_value`, `new_value` (NUMERIC nullable)
- `source` (`csv_import`, `manual`, `other`)
- `changed_at`
- `changed_by_name` (nullable)
- `import_batch_id` (nullable)

**product_import_batches**
- `id`, `file_name`, `file_type`, `started_at`, `completed_at`
- `status`, `row_count`, `created_count`, `updated_count`, `error_count`
- `summary_json` / import metadata

**stock_movements**
- `id`, `product_id`
- `movement_type` (`csv_update`, `stock_count_adjustment`, `delivery_out`, `manual_adjustment`, `return_in`, `reversal`)
- `quantity_delta` (signed)
- `quantity_before`, `quantity_after`
- `reference_type`, `reference_id` (nullable)
- `note`, `created_at`, `created_by_name` (nullable)
- `idempotency_key` (for preventing duplicate delivery movements)

### 7.2 Kampanya ve bayi fiyatları

**campaigns**
- `id`, `name`, `description`
- `campaign_type` (`general`, `product_discount`, `bundle`, `gift`, `coupon`, `special`)
- `starts_at`, `ends_at`
- `base_price_type` (`regular`, `website_discounted`, `manual`)
- `discount_type` (`percent`, `fixed_amount`, `special_price`, `gift`, `info_only`)
- `discount_value` (nullable)
- `gift_description` (nullable)
- `gift_optional` (boolean)
- `gift_yes_base_price_type` (`regular`, `website_discounted`, `manual`, nullable)
- `gift_no_base_price_type` (`regular`, `website_discounted`, `manual`, nullable)
- `employee_note`
- `status`, `created_at`, `updated_at`, `created_by_name` (nullable)

**campaign_products**
- `id`, `campaign_id`, `product_id`
- `relation_type` (`qualifying`, `benefit`, `gift`, `related`)
- `quantity_required` (nullable)

**campaign_history**
- `id`, `campaign_id`, `snapshot_json`, `changed_at`, `changed_by_name` (nullable)

**dealer_pricing**
- `id`, `product_id`
- `cash_floor_price` (NUMERIC nullable)
- `card_floor_price` (NUMERIC nullable)
- `valid_from`, `valid_until` (nullable)
- `note`, `created_at`, `updated_at`, `created_by_name` (nullable)

**dealer_pricing_history**
- `id`, `product_id`, `old_cash_floor`, `new_cash_floor`
- `old_card_floor`, `new_card_floor`
- `changed_at`, `changed_by_name`, `note`

**dealer_discount_settings**
- `id`, `default_percent` (default 10.00)
- `valid_from`, `valid_until`, `updated_at`, `updated_by_name` (nullable)

### 7.3 Banka komisyonu ve minimum kâr

**banks**
- `id`, `name`, `is_active`, `created_at`, `updated_at`

**bank_installment_commissions**
- `id`, `bank_id`, `installment_count`
- `commission_percent`
- `valid_from`, `valid_until` (nullable)
- `created_at`, `updated_at`, `updated_by_name` (nullable)

**profit_targets**
- `id`, `scope_type` (`global`, `product`), `scope_id` (nullable)
- `target_type` (`percent`, `fixed_amount`)
- `target_value`
- `valid_from`, `valid_until` (nullable)
- `created_at`, `updated_at`, `updated_by_name` (nullable)

### 7.4 Teklifler

**offers**
- `id`, `offer_number` (unique readable sequence)
- `customer_name` (nullable)
- `status` (`draft`, `presented`, `accepted`, `lost`, `expired`)
- `payment_type` (`cash`, `card`, `mixed`)
- `bank_id`, `installment_count`, `commission_snapshot_percent` (nullable)
- `cash_total`, `card_total`, `selected_total`
- `note`, `follow_up_at` (nullable)
- `created_at`, `updated_at`, `created_by_name` (nullable)

**offer_items**
- `id`, `offer_id`, `product_id` (nullable if product later archived/deleted; product should normally be retained)
- `product_name_snapshot`
- `quantity`
- `regular_price_snapshot`, `website_price_snapshot`, `cost_snapshot` (nullable)
- `unit_price_cash`, `unit_price_card`
- `campaign_snapshot_json` (nullable)
- `line_total_cash`, `line_total_card`

**offer_history**
- `id`, `offer_id`, `old_status`, `new_status`, `note`, `changed_at`, `changed_by_name`

### 7.5 Rezervasyonlar

**reservations**
- `id`, `reservation_number` (unique readable sequence)
- `customer_name` (required)
- `reservation_date`
- `reminder_due_at` (default reservation_date + 13 months)
- `reminder_status` (`pending`, `snoozed`, `resolved`)
- `note`
- `created_at`, `updated_at`, `created_by_name` (nullable)

**reservation_items**
- `id`, `reservation_id`, `product_id`
- `product_name_snapshot`
- `quantity`, `delivered_quantity` (default 0), `cancelled_quantity` (default 0)
- `status`
- `service_date` (nullable)
- `other_dealer_note` (nullable)
- `note`
- `created_at`, `updated_at`

**reservation_item_events**
- `id`, `reservation_item_id`
- `old_status`, `new_status`
- `quantity_delta` (nullable)
- `note`, `event_at`, `created_by_name` (nullable)

**reservation_reminders**
- `id`, `reservation_id`
- `previous_due_at`, `new_due_at`
- `note`, `created_at`, `created_by_name` (nullable)

**attachments**
- `id`, `owner_type`, `owner_id`
- `original_file_name`, `stored_file_name`, `mime_type`, `size_bytes`
- `storage_path`, `uploaded_at`

### 7.6 Stok sayımı

**stock_count_sessions**
- `id`, `category_id`, `status` (`open`, `review`, `completed`, `cancelled`)
- `started_at`, `completed_at`, `created_by_name`, `completed_by_name`
- `note`

**stock_count_items**
- `id`, `session_id`, `product_id`
- `system_quantity`, `counted_quantity` (nullable)
- `difference` (nullable)
- `applied_at` (nullable)

### 7.7 Hızlı teslim

**quick_deliveries**
- `id`, `customer_name` (required)
- `status` (`open`, `completed`, `cancelled`)
- `created_at`, `created_by_name` (nullable)
- `note` (nullable)

**quick_delivery_barcodes**
- `id`, `quick_delivery_id`
- `barcode_value` (exact decoded Code 128 string)
- `source_type` (`upload`, `clipboard`, `screen_capture`, `camera`)
- `decoded_at`, `verified_at` (nullable)
- `image_attachment_id` (nullable)

### 7.8 Veri bütünlüğü notları

- Para alanları `NUMERIC/DECIMAL` olmalıdır; `float`/`double` kullanılmamalıdır.
- Ürün, teklif, rezervasyon ve stok hareketlerinde geçmiş kayıtları korumak için ürünler fiziksel olarak silinmemelidir; arşivleme tercih edilmelidir.
- Rezervasyon teslim stok hareketleri işlem/transaction içinde atomik oluşturulmalıdır.
- Teslimat için idempotency kontrolü olmalıdır; aynı kalem için aynı teslim miktarı iki kez stoktan düşmemelidir.
- Rezervasyon satırında `delivered_quantity + cancelled_quantity <= quantity` kuralı korunmalıdır.
- Sayım onayı sırasında eşzamanlı stok hareketi gerçekleşmişse sistem sessizce eski değeri ezmemeli; farkı yeniden hesaplamalı veya kullanıcıdan inceleme istemelidir.

---

## 8. Raporlar ve aramalar

### 8.1 MVP raporları

- Ürün listesi.
- Ürün fiyat ve stok detayı.
- Fiziksel stok / açık rezervasyon / satılabilir / temin ihtiyacı listesi.
- Kategori bazlı stok sayım listesi.
- Açık rezervasyonlar.
- Gecikmiş rezervasyon hatırlatmaları.
- Teslimat bekleyen rezervasyon satırları.
- Tamamlanan rezervasyonlar.
- Kampanya rehberi.
- Teklif listesi ve durumları.
- Hızlı teslim kayıtları.
- Ürün stok hareket geçmişi.

### 8.2 Arama ve filtreler

- Ürün adıyla anlık arama.
- Kategori filtresi.
- Aktif/pasif/arşivlenmiş ürün filtresi (arşivleme MVP'de manuel olabilir).
- Kampanya genel/ürün filtresi ve aktif/geçmiş filtresi.
- Rezervasyon durumu ve hatırlatma tarihi filtresi.
- Teklif durumu ve tarih filtresi.
- Stok sayım oturumu durumu filtresi.

Filtrelenmiş ürün sonuçlarını dışa aktarma MVP dışında tutulur; tüm ürünleri dışa aktarma zorunludur.

---

## 9. A4 ve yazdırma gereksinimleri

### 9.1 Rezervasyon çıktısı

- Müşteri adı-soyadı.
- Rezervasyon numarası ve tarihi.
- Ürün adı, miktarı ve varsa not.
- Rezervasyonun mevcut durumu.
- Depo kopyası / bayi kopyası ayrımı.
- Gerekirse müşteri/çalışan için imza veya el yazısı not alanı bırakılabilir; ilk sürümde zorunlu değildir.
- Ekli PDF yazdırma formuna otomatik gömülmek zorunda değildir; PDF ayrı açılabilir.

### 9.2 Stok sayım çıktısı

- Kategori adı ve sayım tarihi.
- Ürün adı.
- Mevcut sistem fiziksel stok miktarı.
- Elle yazılabilir sayılan miktar alanı.
- Fark/not alanı.
- Sayım yapan/teslim alan alanı isteğe bağlı.

### 9.3 Teklif çıktısı

- Teklif numarası ve tarihi.
- Müşteri adı (varsa).
- Ürün adı, miktar ve birim/toplam fiyat.
- Nakit veya kart ödeme biçimi.
- Kartsa banka ve taksit sayısı.
- Toplam fiyat.
- Kampanya/hediye açıklaması (varsa).
- Alış maliyeti ve iç kâr hesapları müşteriye verilen çıktıda gösterilmemelidir. İç kullanım için ayrı teklif özeti olabilir.

### 9.4 Teknik yazdırma

- `@media print` CSS ile yazdırma görünümü hazırlanmalıdır.
- A4 portre varsayılan olmalıdır; geniş stok tablosunda gerekirse yatay kullanılabilir.
- Siyah-beyaz yazıcıda okunabilir kontrast ve çizgiler kullanılmalıdır.
- Gereksiz renkli dolgu ve arka plan görsellerinden kaçınılmalıdır.
- Sayfa sonlarında kayıt satırı bölünmesi azaltılmalıdır.

---

## 10. Teknik mimari önerisi

### 10.1 Genel yaklaşım

İlk sürüm tek uygulama/tek veritabanı prensibiyle bir **modüler monolit** olarak geliştirilmelidir. Mikroservis, Redis, Celery veya ayrı servis kümeleri MVP için gerekli değildir.

**Önerilen teknoloji yığını:**
- Backend: Python + FastAPI.
- Veri tabanı: PostgreSQL.
- ORM/migration: SQLAlchemy + Alembic.
- Veri doğrulama: Pydantic.
- Frontend: React + TypeScript.
- UI: Tailwind CSS ve erişilebilir bileşenler.
- Mobil kullanım: responsive PWA yaklaşımı.
- PDF ekleri: Windows sunucuda kontrollü dosya dizini.
- Barkod çözme: tarayıcıda veya yerel API üzerinden Code 128 decoder; mevcut Python decoder scripti değerlendirildikten sonra entegrasyon yöntemi seçilir.
- Zamanlanmış hatırlatma: ilk aşamada uygulama içi günlük görev veya sorgu; ayrı mesajlaşma servisi gerekmez.

### 10.2 Dağıtım

- İlk host Windows 11 bilgisayar olacaktır.
- 3–4 eşzamanlı istemci için tek API ve PostgreSQL örneği yeterli hedef olarak kabul edilir; gerçek donanım yük testiyle doğrulanır.
- Uygulama bayi LAN/Wi-Fi ağındaki sabit IP veya yerel DNS adı üzerinden erişilir.
- İstemciler PostgreSQL'e doğrudan bağlanmaz; yalnızca API'ye erişir.
- PostgreSQL portu LAN istemcilerine açılmaz; mümkün olduğunca yalnızca localhost/uygulama ağına bağlanır.
- Sunucunun uykuya geçmesi engellenir; mümkünse Ethernet ve UPS kullanılır.
- Windows yeniden başlatıldığında API ve veritabanı otomatik başlamalıdır.
- İlk sürümde Docker zorunlu değildir. Windows üzerinde yerel servis kurulumu tercih edilebilir; dağıtım yöntemi Docker lisansı/işletme koşulları değerlendirilmeden Docker'a bağlanmamalıdır.

### 10.3 Ağ ve erişim

- Uygulama yalnızca bayi yerel ağı için tasarlanır.
- İnternete açık port, public URL veya modem port yönlendirme MVP'de yapılmaz.
- Misafir Wi-Fi ağından erişim mümkünse engellenir.
- PWA kurulumu ve kamera/clipboard gibi tarayıcı yetenekleri güvenli bağlam (HTTPS/localhost) gereksinimleri açısından test edilmelidir. Yerel IP ile HTTP kullanımında bazı tarayıcı özellikleri kısıtlanabilir; iç ağ HTTPS çözümü dağıtım planında ele alınmalıdır.
- Ekran yakalama, clipboard ve kamera erişimi tarayıcı izinlerine bağlıdır; dosya yükleme yedek yöntem olarak kalmalıdır.

### 10.4 Dosya saklama

- PDF ve görseller PostgreSQL blob alanlarında değil, sunucuda kontrollü bir dosya dizininde saklanır.
- Veritabanında dosya metadata ve ilişki bilgisi tutulur.
- Dosya yüklemelerinde MIME türü, uzantı ve boyut kontrol edilir.
- Rastgele/benzersiz saklama adı kullanılır; kullanıcıdan gelen dosya adı doğrudan dosya yolu olarak kullanılmaz.
- Veritabanı ve dosya dizini aynı yedekleme planına dahil edilir.

### 10.5 Önerilen proje yapısı

```text
bayios/
  backend/
    app/
      main.py
      core/
        config.py
        database.py
        logging.py
      api/
        v1/
          products.py
          imports.py
          campaigns.py
          commissions.py
          offers.py
          reservations.py
          inventory.py
          quick_deliveries.py
          attachments.py
      models/
      schemas/
      services/
      repositories/
      jobs/
    migrations/
    tests/
    requirements.txt
  frontend/
    src/
      app/
      components/
      pages/
      features/
        products/
        campaigns/
        commissions/
        offers/
        reservations/
        inventory/
        quick-deliveries/
      services/
      hooks/
      types/
    public/
  storage/
    attachments/       # runtime data; excluded from source control
  deployment/
    windows/
    backup/
  docs/
    PRD.md
    DATA_IMPORT.md
    OPERATIONS.md
  README.md
```

### 10.6 API taslak uçları

Örnek REST uçları (nihai sözleşme geliştirme aşamasında OpenAPI üzerinden sabitlenir):

```text
GET/POST       /api/v1/products
GET/PATCH      /api/v1/products/{id}
GET            /api/v1/products/{id}/history
POST           /api/v1/imports/products/preview
POST           /api/v1/imports/products/commit
GET            /api/v1/imports
GET/POST       /api/v1/campaigns
GET/PATCH      /api/v1/campaigns/{id}
GET/POST       /api/v1/banks
GET/POST       /api/v1/commissions
GET/POST       /api/v1/offers
GET/PATCH      /api/v1/offers/{id}
GET/POST       /api/v1/reservations
GET/PATCH      /api/v1/reservations/{id}
POST           /api/v1/reservations/{id}/items/{item_id}/events
POST           /api/v1/reservations/{id}/items/{item_id}/deliver
GET/POST       /api/v1/stock-counts
POST           /api/v1/stock-counts/{id}/complete
GET            /api/v1/products/{id}/stock-movements
GET/POST       /api/v1/quick-deliveries
POST           /api/v1/quick-deliveries/{id}/barcodes/decode
POST           /api/v1/attachments
GET            /api/v1/attachments/{id}
```

### 10.7 Zamanlanmış işler

- Günlük rezervasyon hatırlatma kontrolü.
- Yedekleme görevi (Windows Task Scheduler veya servis).
- MVP'de scraper, fiyat çekme, otomatik kampanya toplama veya internet erişimli arka plan görevi yoktur.

---

## 11. Kullanılabilirlik ve performans

### 11.1 Kullanılabilirlik

- En sık işlemler 2–4 ana etkileşimde tamamlanabilmelidir.
- Mobilde form alanları büyük ve dokunması kolay olmalıdır.
- Ürün arama sayfası ana navigasyondan bir adımda açılmalıdır.
- Uzun formlar bölümlere ayrılmalı; gerekli olmayan alanlar gizlenebilir/opsiyonel olmalıdır.
- Çalışan adı, not, servis tarihi ve ek dosya gibi alanlar zorunlu olmamalıdır.
- Durum adları teknik terimler yerine operasyon dilinde gösterilmelidir.
- Kaydetme sonrası açık başarı/hata mesajı gösterilmelidir.
- Hatalı veri sessizce kaydedilmemelidir.

### 11.2 Performans hedefleri

3–4 eşzamanlı LAN kullanıcısı için hedefler:
- Ürün arama sonucu normal katalog boyutunda 1 saniye civarında görünmelidir.
- Ürün detay sayfası 1 saniye civarında açılmalıdır.
- Basit kayıt ve durum güncellemeleri 1 saniye civarında tamamlanmalıdır.
- CSV/Excel aktarımı uzun sürerse ilerleme ve özet gösterilmelidir.
- Büyük PDF/görsel eklerinde yükleme durumu gösterilmeli ve makul boyut sınırı uygulanmalıdır.
- Uygulama internet bağlantısı olmadığında LAN erişimi sürdüğü sürece çalışmalıdır.

Performans hedefleri başlangıç kabul kriteridir; gerçek ürün adedi, dosya büyüklüğü ve donanım üzerinde test edilerek ayarlanır.

### 11.3 Hata toleransı

- API veya bilgisayar yeniden başladığında kayıtlar kaybolmamalıdır.
- Veritabanı yazma işlemleri transaction kullanmalıdır.
- CSV aktarımı tamamlanmadan yarıda kesilirse kısmi ve tutarsız kayıt bırakmamalıdır; aktarım partisi atomik veya kontrollü batch mantığıyla yürütülmelidir.
- Dosya ekleme başarısız olursa rezervasyon kaydı dosyasız da saklanabilmeli veya kullanıcıya açık hata verilmelidir.
- Barkod çözülemezse kullanıcı kodu manuel girebilmelidir (P0 için güvenli yedek yöntem).

---

## 12. Güvenlik, gizlilik ve yedekleme

### 12.1 MVP güvenlik sınırları

- Kimlik doğrulama ve rol sistemi yoktur; bu açık bir MVP sınırlamasıdır.
- Uygulama yalnızca kontrollü yerel ağda kullanılmalıdır.
- İnternete açılma, port yönlendirme ve dışarıdan erişim etkinleştirilmemelidir.
- İstemci tarafı gizli veri koruması/rol filtresi varmış gibi tasarlanmamalıdır; MVP'de tüm kullanıcıların aynı veri erişimine sahip olduğu kabul edilir.
- Dosya yüklemeleri doğrulanmalı ve güvenli dizine yazılmalıdır.
- Hatalar kullanıcıya anlaşılır biçimde gösterilmeli, hassas teknik ayrıntılar istemciye döndürülmemelidir.

### 12.2 Kişisel veri

Müşteri adı-soyadı kişisel veridir. MVP'de telefon gibi ek kişisel veriler toplanmaz. Buna rağmen işletme, müşteri bilgilerini hangi amaçla tuttuğunu, kimlerin eriştiğini, ne kadar sakladığını ve silme/anonimleştirme ihtiyacını kendi KVKK yükümlülükleri çerçevesinde değerlendirmelidir. Bu PRD hukuki uygunluk garantisi değildir.

### 12.3 Yedekleme

- Her gün veritabanı yedeği alınmalıdır.
- Ek PDF ve görsel dosyaları da yedeklenmelidir.
- En az bir yedek sunucunun diskinden bağımsız harici diskte tutulmalıdır.
- Haftalık tam yedek ve aylık geri yükleme testi önerilir.
- Yedek dosyalar erişim kontrollü saklanmalıdır.
- Yedekleme başarısızsa uygulama yöneticisine görünür uyarı sağlanmalıdır (MVP'de log/yerel bildirim olabilir).
- Yedekleme geri yükleme adımları `OPERATIONS.md` içinde yazılı olmalıdır.

---

## 13. Test ve kabul kriterleri

### 13.1 Ürün aktarımı testleri

1. `07325 A` olarak gelen ürün adı baştaki sıfırları korur.
2. Aynı ürün tekrar aktarıldığında yeni ürün yaratılmaz; mevcut ürün güncellenir.
3. Normal veya Oliz fiyatı değişmişse fiyat geçmişi oluşur.
4. Fiyat değişmemişse gereksiz tarihçe kaydı oluşmaz; son görülme zamanı güncellenir.
5. `quantity` boşsa fiziksel stok korunur.
6. `quantity=0` ise fiziksel stok sıfırlanır ve stok hareketi kaydı oluşur.
7. CSV'de bulunmayan ürün silinmez/pasife alınmaz.
8. Hatalı satır diğer geçerli satırların sessizce bozulmasına yol açmaz; aktarım özeti gösterilir.

### 13.2 Stok ve rezervasyon testleri

Başlangıç: Fiziksel stok 5, açık rezervasyon 0.

1. 2 adet rezervasyon açılır: fiziksel stok 5 kalır, açık rezervasyon 2 olur, satılabilir stok 3 olur.
2. Müşteri teslimat ister: fiziksel stok değişmez.
3. Depocu çıkışa izin verir: fiziksel stok değişmez.
4. Servis atanır: fiziksel stok değişmez.
5. 1 adet teslim edildi işaretlenir: fiziksel stok 4, açık rezervasyon 1, satılabilir stok 3 olur.
6. Kalan 1 adet daha sonra teslim edilirse fiziksel stok 3, açık rezervasyon 0, satılabilir stok 3 olur.
7. Teslim edildi işlemi aynı kalem için tekrar gönderilirse ikinci stok çıkışı oluşmaz.
8. Rezervasyon iptal edilirse fiziksel stok değişmez, açık rezervasyon azalır.
9. Fiziksel stok açık rezervasyon miktarından azsa satılabilir 0 ve temin ihtiyacı pozitif gösterilir.
10. 13 ay geçmiş rezervasyon uyarı verir ancak otomatik iptal olmaz.
11. Erteleme varsayılan olarak 1 ay sonrasına yapılır ve tarihçe tutulur.
12. Çok ürünlü rezervasyonda bir ürün teslim edildiğinde diğer ürün satırları açık kalabilir.

### 13.3 Kampanya testleri

1. Normal fiyat 25.999 TL, Oliz fiyatı 23.999 TL, hediye var ve bayi indirimi %10 ise rehber 23.399,10 TL senaryosunu gösterir.
2. Aynı üründe hediye yoksa ve Oliz fiyatı varsa 21.599,10 TL senaryosu gösterilir.
3. Oliz fiyatı olmayan üründe bayi indirimi normal fiyat üzerinden örneklenir.
4. Genel bayi indirimi varsayılan %10 görünür; çalışan %15 girebilir.
5. Ürüne özel bayi nakit/kart fiyatları genel ayardan ayrı görünür.
6. Tarihi geçmiş kampanya aktif kampanya olarak gösterilmez; geçmiş filtrede bulunabilir.
7. Kampanya değişince eski teklif snapshot bilgisi değişmez.

### 13.4 Komisyon/teklif testleri

1. Maliyet 30.000 TL, hedef kâr 1.500 TL, komisyon %5 ise fiyat `(30.000+1.500)/0,95 = 33.157,89 TL` olarak hesaplanır.
2. Komisyon %0 ise sonuç maliyet + hedef kâr olur.
3. Hedef kâr ayarlanmamışsa uygulama uyarı gösterir.
4. Komisyon dönem değişimi eski teklifin komisyon snapshot değerini değiştirmez.
5. Teklif çok ürünlü olabilir ve her kalemin fiyat snapshot'ı saklanır.
6. Teklif A4 yazdırılır; alış maliyeti veya iç kâr bilgisi müşteri kopyasında görünmez.

### 13.5 Hızlı teslim testleri

1. Geçerli Code 128 ekran görüntüsü pano ile yapıştırılır ve metin çözülür.
2. Aynı görüntü dosya olarak yüklenirse aynı barkod metni çözülür.
3. Ekran yakalama izni reddedilirse uygulama dosya/pano yöntemine geri dönebilir.
4. Çözülemeyen barkod hatalı başarı olarak kaydedilmez.
5. Kodun başı ve sonu aynen korunur.
6. Bir müşteri kaydına birden fazla barkod eklenebilir.
7. WMS'ye herhangi bir otomatik istek gönderilmez.

### 13.6 Yazdırma testleri

1. Rezervasyon çıktısı A4'e okunaklı biçimde sığar.
2. Depo ve bayi kopyaları ayrı başlıkla alınabilir.
3. Kategori stok sayım listesi A4 basılabilir.
4. Çok satırlı teklif birden fazla sayfaya bölündüğünde başlık ve toplamlar anlaşılır kalır.
5. Siyah-beyaz yazıcı çıktısında metin ve tablo sınırları okunur.

---

## 14. Riskler ve azaltma yöntemleri

| Risk | Etki | Azaltma |
|---|---|---|
| Çalışanların yeni uygulamayı kullanmaması | Veriler güncel kalmaz | Az alanlı formlar, hızlı arama, mevcut iş akışını kısaltma, önce gönüllü/pilot kullanıcıyla deneme |
| CSV ürün adlarının tutarsız olması | Yanlış ürün eşleştirme/duplikasyon | Ön izleme, belirsiz eşleşme onayı, dahili ürün ID'si |
| CSV stok değerinin fiziksel sayımla uyuşmaması | Yanlış stok | Import ön izlemesi, stok hareketi geçmişi, kategori sayımı ve fark onayı |
| Rezervasyon teslimatının işaretlenmemesi | Fiziksel stok fazla görünür | Teslimat ekranında açık bekleyen işler, ana ekran uyarıları, tek adımda tamamla |
| Teslimatın iki kez işlenmesi | Çift stok düşümü | Idempotency key ve atomik transaction |
| Kampanya şartının yanlış girilmesi | Hatalı müşteri fiyatı | Zorunlu kampanya açıklaması, tarih, fiyat tabanı ve hediye var/yok senaryosu ön izlemesi |
| Komisyon oranlarının eski kalması | Yanlış minimum fiyat | Geçerlilik tarihi, aylık güncelleme hatırlatması, teklif snapshot'ı |
| Hesap/rol olmaması | LAN'daki herkes veri düzenleyebilir | MVP yalnızca kontrollü LAN; uzaktan erişimden önce auth/role zorunlu |
| Sunucu bilgisayarın kapanması | Uygulamaya erişilemez | Otomatik başlatma, uyku kapatma, yedek ve mümkünse UPS |
| Barkod fotoğraf kalitesi | Decoder başarısız | Pano/dosya/kamera alternatifleri, ön izleme, manuel metin girişi |
| PDF ve müşteri bilgilerinin kaybolması | Operasyon kaybı | Veritabanı + dosya yedeklemesi ve geri yükleme testi |

---

## 15. Geliştirme milestone'ları

POS hesaplayıcısı en son milestone olarak kalır. Sıralama, çalışanlara en hızlı faydayı verecek temel akışlardan başlar.

### Milestone 0 — Proje altyapısı

- Repo ve modüler proje iskeleti.
- FastAPI, PostgreSQL ve React/TypeScript kurulumu.
- LAN erişimi.
- Temel responsive layout ve ana navigasyon.
- Veritabanı migration altyapısı.
- Yedekleme/geri yükleme ilk sürümü.

**Çıkış kriteri:** Windows host üzerinden en az bir masaüstü ve bir mobil istemci uygulamaya erişebilir; veri kalıcıdır.

### Milestone 1 — Ürün kataloğu ve CSV/Excel

- Ürün listesi ve arama.
- Ürün detay kartı.
- CSV/Excel ön izleme ve içe aktarma.
- Normal/Oliz fiyatı ve fiziksel stok eşleme.
- Fiyat/stok geçmişi.
- Tüm ürünleri CSV/Excel dışa aktarma.

**Çıkış kriteri:** Mevcut örnek dosya veri kaybı/duplikasyon olmadan aktarılır; boş quantity ve 0 quantity davranışı test edilir.

### Milestone 2 — Rezervasyon ve A4

- Rezervasyon oluşturma, çoklu ürün.
- Rezervasyon tarihçesi ve 13 aylık uyarı.
- Erteleme.
- Teslimat isteği, depo onayı, servis ataması, servis tarihi ve teslim edildi akışı.
- Teslim edildi durumunda fiziksel stoktan düşüm.
- PDF ekleme/görüntüleme.
- Rezervasyon listesi/detay A4 ve iki kopya.

**Çıkış kriteri:** Rezervasyon uçtan uca takip edilir; çift stok düşümü olmaz; depo ve bayi çıktıları alınır.

### Milestone 3 — Stok sayımı ve stok özeti

- Fiziksel/açık rezervasyon/satılabilir/temin ihtiyacı görünümü.
- Kategori bazlı sayım oturumu.
- Sayım farkı ve onay.
- Stok hareket geçmişi.
- A4 sayım listesi.

**Çıkış kriteri:** Kategori sayımı uygulamaya işlenir ve stok hareketi olarak geriye dönük görülebilir.

### Milestone 4 — Kampanya ve bayi fiyat rehberi

- Genel ve ürün bazlı kampanyalar.
- Hediye, ürün kombinasyonu ve indirim tabanı.
- Hediye var/yok fiyat senaryosu.
- Genel bayi indirim oranı varsayılanı (%10) ve değiştirilebilir oran.
- Ürüne özel nakit/kart minimum fiyatları.
- Kampanya ve bayi fiyatı tarihçesi.

**Çıkış kriteri:** Verilen hediye/Oliz örneği ve özel ürün fiyatları çalışan ekranında açıkça anlaşılır.

### Milestone 5 — Teklif ve banka komisyonları

- Banka/taksit komisyon tablosu.
- Minimum kâr TL/% ayarı.
- Komisyona göre referans fiyat.
- Çok ürünlü teklif.
- Nakit/kart fiyatı, tek banka/taksit seçimi.
- Teklif geçmişi ve A4.
- Tekliften rezervasyona dönüşüm (P1).

**Çıkış kriteri:** Örnek maliyet/komisyon testleri geçer; eski teklifler sonraki fiyat/komisyon güncellemelerinden etkilenmez.

### Milestone 6 — Hızlı Teslim / Code 128

- Müşteri adı-soyadı.
- Fotoğraf yükleme.
- Clipboard paste.
- Masaüstü ekran yakalama izin akışı.
- Mobil kamera/galeri.
- Code 128 çözme, doğrulama ve kopyalama.
- Bir kayda birden fazla barkod.

**Çıkış kriteri:** WhatsApp görüntüsünden barkod metni WMS'ye elle yapıştırılabilecek biçimde doğru alınır; WMS'ye otomatik erişim yapılmaz.

### Milestone 7 — Kabul, sağlamlaştırma ve POS araştırması

- Kullanıcı kabul testleri.
- A4 çıktı düzenleri ve mobil kullanılabilirlik düzeltmeleri.
- Yedek geri yükleme testi.
- Gerçek kampanya örnekleriyle rehber doğrulaması.
- POS kampanya davranışını kontrollü testlerle modelleme ve ayrı PRD/teknik tasarım.

**Çıkış kriteri:** MVP operasyonel olarak kullanılabilir; POS hesaplama sistemi için doğrulanmış iş kuralları toplanmıştır.

---

## 16. MVP dışı sonraki geliştirmeler

Öncelik sırasına göre değerlendirilebilecek geliştirmeler:

1. Kullanıcı hesapları, roller ve işlem sahipliği.
2. Uzaktan erişim/VPN veya güvenli dış bağlantı.
3. PDF/UBL-TR e-fatura okuma ve ürün satırı çıkarma.
4. Filtrelenmiş ürün dışa aktarma.
5. Rezervasyon devri ve daha gelişmiş görev yönetimi.
6. Teklif takip hatırlatmaları ve raporları.
7. Çoklu banka/taksit kıyaslama.
8. Kampanya sepet algoritması ve POS indirim dağıtımı.
9. İç bilgi tabanı/şirket wiki'si; mevcut Trilium notlarının bağlantılanması veya ileride BookStack benzeri ayrı bir çözümün değerlendirilmesi.
10. İade ve ters stok hareketi iş akışı.
11. Depocu için sınırlı mobil sayım arayüzü.
12. WMS/Dynamics entegrasyonu (ancak resmi/izinli ve teknik olarak mümkün bir arayüz varsa ayrı kapsam olarak).

---

## 17. Varsayımlar ve karar kaydı

Bu PRD aşağıdaki kullanıcı kararlarını temel alır:

- İlk kullanım 3–4 kişi, yerel ağ ve Windows 11 host üzerindedir.
- Host için önce mevcut eski Windows bilgisayar denenebilir; yetersiz kalırsa daha güçlü laptop/PC kullanılabilir.
- MVP'de hesap, parola, rol veya izin sistemi yoktur.
- Çalışan adı isteğe bağlı kaydedilir; gerçek kimlik doğrulaması sayılmaz.
- Ürün kataloğu CSV/Excel ile manuel güncellenir.
- Scraper uygulamaya dahil değildir. Harici Python/GitHub Actions işi ayrı kalır; MVP'de otomatik veri bağlantısı yoktur.
- CSV `quantity` fiziksel stok alanıdır. Boş quantity mevcut değeri korur; 0 fiziksel stoğu sıfırlar.
- CSV'de bulunmayan ürünler silinmez/pasife alınmaz.
- Ürün adı çalışan için ana tanımlayıcıdır; dahili değişmez ürün ID'si ayrıca bulunur.
- Ürün kataloğunda barkod zorunlu değildir.
- Code 128 yalnızca Hızlı Teslim akışında fotoğraftan çözülür; tam kod korunur.
- Hızlı Teslim müşteri adı-soyadı ve barkod(lar) tutar; WMS çıkışı kullanıcı tarafından ayrı yapılır.
- Rezervasyon ürün satışından sonra açılır; kapora/senet/açık hesap rezervasyonu yoktur.
- Rezervasyonlar ürün bazında çoklu satır destekler.
- Rezervasyonun 13 aylık takip hatırlatması vardır; otomatik iptal yoktur; erteleme varsayılan 1 aydır.
- Müşteri teslimat istediğinde çalışan depocuyla iletişime geçer. Depo çıkış onayı ve servis ataması fiziksel stok düşürmez.
- Fiziksel stok yalnızca ilgili rezervasyon satırı “Teslim edildi” (teslimat/kurulum tamamlandı) olarak işaretlendiğinde düşer.
- Kampanya rehberi MVP'de bilgilendirme ve tekil ürün senaryosu gösterir; POS sepet algoritması değildir.
- Genel bayi indirimi %10 varsayılan gösterilir; çalışan patronun yönlendirmesiyle değiştirebilir, uygulamada sabit %10 tavanı yoktur.
- Ürüne özel nakit/kart minimum satış fiyatı doğrudan TL olarak girilir.
- Banka komisyonları banka ve taksit bazında elle güncellenir.
- Teklifte birden fazla ürün olabilir; MVP'de tek banka/taksit seçimi yapılır.
- A4 çıktıları rezervasyon, stok sayımı/ürün listesi ve teklif için zorunludur.
- PDF ekleme/görüntüleme MVP'de; otomatik PDF okuma sonraki sürümdedir.
- POS hesaplayıcısı son milestone'dur.

---

## 18. Açık uygulama notları (koda başlamadan önce teyit edilmesi gereken teknik ayrıntılar)

Bu maddeler ürün kapsamını değiştirmez; geliştirme sırasında örnek dosya ve gerçek kullanım üzerinde doğrulanmalıdır:

1. Excel dosyalarında hangi uzantıların (`.xlsx`, eski `.xls`) destekleneceği; CSV ayraç ve encoding seçenekleri.
2. Ürün adı değiştiğinde mevcut ürünle eşleştirme için manuel eşleştirme ekranının ayrıntısı.
3. Boş `website_discounted_price` alanının varsayılan olarak mevcut fiyatı koruması; indirimli fiyatı kaldırmak için açık temizleme seçeneği.
4. Kategori verisinin mevcut CSV'de bulunup bulunmadığı; bulunmuyorsa uygulamada manuel kategori ataması.
5. Komisyon oranlarının hangi taksit sayıları için girileceği ve aylık değişikliklerin yürürlük tarihi.
6. Minimum kâr ayarının global mi, ürün bazlı mı, yoksa her ikisi mi kullanılacağı. Öneri: ikisini de desteklemek; ürün değeri global ayarı geçersiz kılsın.
7. Code 128 decoder için mevcut Python scriptinin değerlendirilmesi ve tarayıcı/Backend çözümünün seçilmesi.
8. Windows LAN PWA kullanımı için HTTPS/yerel sertifika yaklaşımı.
9. Gerçek ürün kataloğu büyüklüğü ve eski host donanımıyla performans testi.
10. Stok sayım sırasında eşzamanlı teslimat/CSV aktarımı olursa farkın nasıl çözüleceği; MVP'de sayım sonu farkı yeniden hesaplama ve onay önerilir.

Bu maddeler MVP'nin işlevlerini engelleyen ürün kararları değildir; uygulamaya başlamadan önce örnek verilerle doğrulanacak teknik ayrıntılardır.

---

## 19. Sözlük

| Terim | Anlam |
|---|---|
| Normal fiyat | Ürünün normal/indirimsiz satış fiyatı |
| Oliz fiyatı | Şirket/web kampanyası sonrası ürün için bildirilen indirimli fiyat |
| Bayi indirimi | Bayinin şirket fiyatına veya kampanya kuralına eklediği indirim |
| Bayi minimum satış fiyatı | Patronun çalışanlara belirttiği, altına inilmemesi gereken nakit/kart fiyat referansı |
| Fiziksel stok | Depocunun fiilen saydığı veya son stok hareketleriyle hesaplanan eldeki miktar |
| Açık rezervasyon | Satılmış ancak teslimat/kurulumu tamamlanmamış ürün miktarı |
| Satılabilir stok | Fiziksel stoktan açık rezervasyon miktarı düşüldükten sonra kalan teorik miktar |
| Temin ihtiyacı | Açık rezervasyon miktarının fiziksel stoku aşan kısmı |
| Depo hazır | Depocunun ilgili ürünün çıkışına izin verdiği durum |
| Servis atandı | Servis süreci planlandı; henüz teslim/kurulum tamamlanmadı |
| Teslim edildi | Ürün müşteriye ulaştı/kurulum tamamlandı; fiziksel stoktan düşüm tetiklenir |
| Hızlı Teslim | Müşteri adı ve Code 128 metninin WMS öncesi operasyon takibi için kaydedildiği modül |
| POS milestone | Kart/indirim/karma sepet hesaplama algoritmasının ayrı ve sonraki geliştirme aşaması |

---

**Belge sonu — BayiOS PRD v1.0**
