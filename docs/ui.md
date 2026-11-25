# BayiOS UI/UX Sözleşmesi

**Durum:** Tek geçerli UI/UX sözleşmesi  
**Sürüm:** 2.0  
**Tarih:** 23.11.2026  
**Kapsam:** Yalnız arayüz, görsel dil, yerleşim, bileşen davranışı ve responsive kurallar. İş kuralları [prd.md](./prd.md), mimari [plan.md](./plan.md) ve [ui-redesign-plan.md](./ui-redesign-plan.md) içindedir.

Bu belge, BayiOS arayüzünde görsel veya etkileşimle ilgili her kararın tek kaynağıdır. PRD'deki ekran anlatımları işlevsel gereksinimi tanımlar; yerleşim, bileşen, renk, tipografi, kırılım ve etkileşim için bu belge esastır. Çelişki halinde işlev için PRD, arayüz için bu belge geçerlidir.

## 1. İlkeler

- **Telefon = hızlı bakma.** Ürün bul, fiyat/stok/özellik oku, teklif için fiyat ver.
- **Laptop = yönetme.** Kampanya, komisyon, içe/dışa aktarma, toplu işlem, A4 çıktı.
- **Sakin ve profesyonel.** Satışa indirgenmemiş, ferah, operasyon odaklı bir arayüz. Gereksiz renk, gölge ve süsleme yok.
- **Tek bilgi mimarisi.** Telefon ve laptop aynı kavramları, aynı sırayla kullanır; yalnız yoğunluk ve yerleşim değişir.
- **Renk tek başına anlam taşımaz.** Her durum metinle birlikte gösterilir.
- **Hover'a bağlı bilgi yok.** Her bilgi ve eylem dokunma/klavye ile erişilebilir.
- **Bir ekranda bir birincil eylem.** Tehlike eylemleri ikincil konumda ve iki aşamalı onaylıdır.
- **Türkçe arayüz.** Tüm kullanıcı metinleri Türkçe, cümle düzeninde ve tutarlı terimlerle yazılır.
- **Desteklenmeyen özellik gösterilmez.** Python tarafında karşılığı olmayan WhatsApp paylaşımı, barkod, kamera, hızlı teslim, rol/yetki gibi öğeler için sahte buton veya “yakında” vaadi konmaz.

## 2. Görsel dil

### 2.1 Renk

| Token | Değer | Kullanım |
| --- | --- | --- |
| --bg | #f7f7f4 | Sayfa zemini |
| --surface | #ffffff | Kart, tablo, modal yüzeyi |
| --surface-2 | #fcfcfb | İkincil yüzey, tablo başlığı |
| --surface-3 | #f1f1ec | Hover, pasif dolgu |
| --ink | #1c1c19 | Ana metin |
| --ink-strong | #111110 | Başlık, fiyat |
| --muted | #6f6f63 | Yardımcı metin |
| --border | #e4e4dc | İnce kenar |
| --border-strong | #cfcfc4 | Kontrol kenarı |
| --accent | #1f2a5a | Birincil buton, aktif menü, bağlantı |
| --accent-hover | #17204a | Birincil hover |
| --accent-soft | #e9ebf5 | Seçili/aktif yumuşak zemin |
| --success | #047857 | Başarı, pozitif stok |
| --success-soft | #ecfdf5 | Başarı rozeti zemini |
| --warning | #b45309 | Uyarı, düşük stok |
| --warning-soft | #fffbeb | Uyarı rozeti zemini |
| --danger | #be123c | Tehlike, negatif stok |
| --danger-soft | #fff1f2 | Tehlike rozeti zemini |
| --info | #1d4ed8 | Bilgi, Oliz vurgusu |
| --info-soft | #eff6ff | Bilgi rozeti zemini |

- Birincil vurgu lacivert/indigo ailesindendir; parlak mavi yalnız bilgi ve Oliz fiyatı için kullanılır.
- Zemin sıcak nötrdür; soğuk gri büyük yüzeyler kullanılmaz.
- Kontrast: gövde metni en az 4.5:1, büyük başlık en az 3:1.

### 2.2 Tipografi

- **Arayüz:** Inter (self-host, latin + latin-ext).
- **Sayı/ID:** JetBrains Mono (self-host, latin + latin-ext), tabular-nums.
- **Ölçek:** h1 24px/1.2, h2 20px/1.25, h3 16px/1.3, gövde 14px/1.5, yardımcı 12px/1.4, mikro 11px/1.3.
- **Ağırlık:** 400 gövde, 500 etiket, 600 başlık, 700 fiyat/vurgu.
- **Fiyat:** Her zaman tek satırda, binlik ayraç nokta, iki ondalık ve TL son ekiyle: 38.199,00 TL. Kırılmaz.
- **Uzun metin:** Yalnız kelime sınırında sarılır; kelime karakter karakter bölünmez. ID ve fiyatlar sarılmaz.
- Telefon gövde metni 14px'in altına inmez.

### 2.3 Boşluk, yarıçap, gölge

- **Boşluk:** 4px tabanlı; 4, 8, 12, 16, 20, 24, 32, 40.
- **Yarıçap:** kontrol 10px, kart 14px, büyük kart 16px, modal 18px, rozet 999px.
- **Gölge:** kartlarda 0 1px 2px rgba(20,20,19,.04); yapışkan çubuklarda 0 -8px 24px rgba(20,20,19,.06); modalda 0 20px 50px rgba(20,20,19,.18).
- **Kenar:** 1px --border; seçili öğe kalın renkli kenar veya accent-soft zemin alır, tamamen dolu mavi kullanılmaz.

### 2.4 İkonlar

- Tek tip çizgi ikon seti; 1.8px stroke, 20px varsayılan, 16px küçük, 24px büyük.
- İkonlar base.html içindeki SVG sprite'tan gelir; ikon fontu veya CDN yoktur.
- İkon tek başına anlam taşımaz; yanında etiket bulunur. Yalnız ikon kullanılan yerde aria-label ve title zorunludur.
- Navigasyon ikonları: home, products, campaigns, offers, reservations, stock, commissions, settings.

### 2.5 Hareket

- Geçişler 150–200ms ease; modal ve alt sayfa 220ms.
- reduced-motion tercihinde geçişler kapanır, içerik anında görünür.
- Otomatik oynayan animasyon, parallax veya döngüsel hareket yoktur.

## 3. Uygulama kabuğu

### 3.1 Genel yerleşim

- Masaüstünde sol menü + üst çubuk + içerik.
- Sol menü ve üst çubuk sticky; sol menü kendi içinde kaydırılır ve viewport yüksekliğini aşmaz.
- İçerik azami 1440px genişlikte ortalanır; okuma kolonları 72ch'yi geçmez.
- Sayfa gövdesi yatay kaymaz. Yalnızca işaretli tablo kapları yatay kaydırılır.

### 3.2 Üst çubuk

- Sol: menü/marka; mobilde yalnız kompakt marka.
- Orta: global ürün arama; her ekranda görünür ve sticky. Arama /products?q= adresine gider.
- Sağ: sayfaya özgü kısayol yoksa boş; gereksiz ikon konmaz.
- Yükseklik: mobil 60px, laptop 64px. Altında 1px kenar.
- Yazdırmada gizlenir.

### 3.3 Masaüstü sol menü

- 1024–1279px: 72px genişlik, yalnız ikon; her öğe title ve aria-label taşır. Aktif öğe accent zemin.
- ≥1280px: 248px genişlik, ikon + etiket. Aktif öğe accent zemin ve aria-current="page".
- Menü öğeleri: Ana Sayfa, Ürünler, Kampanyalar, Teklifler, Rezervasyonlar, Stok/Sayım, Komisyonlar, Ayarlar.
- Menü altında bayi kimliği veya hedef/progress gibi backend'i olmayan bloklar gösterilmez.
- Menü kendi içinde kaydırılır; alt öğeler erişilebilir kalır.

### 3.4 Telefon alt sekme çubuğu

- <1024px'de görünür; 5 öğe: Ana Sayfa, Ürünler, Teklifler, Rezervasyonlar, Daha fazla.
- Yükseklik 60px + safe-area; sticky/fixed, içerik altında boşluk bırakır.
- Aktif öğe accent renk ve aria-current="page".
- “Daha fazla” alttan açılan sayfa: Kampanyalar, Stok/Sayım, Komisyonlar, Ayarlar; her öğe ikon + etiket.
- Odaklı ekranlarda (teklif formu, sayım oturumu) alt sekme gizlenir; yerine sticky eylem çubuğu gelir.
- Toplu işlem çubuğu ve sticky eylem çubuğu alt sekmenin altında kalmaz; üstüne dizilir.
- Yazdırmada gizlenir.

### 3.5 İçerik ve sayfa başlığı

- İçerik padding: mobil 16px, tablet 24px, laptop 32px.
- Sayfa başlığı: üstte küçük bağlam/eyebrow, h1, tek satır açıklama; sağda eylemler.
- Mobilde başlık ve açıklama tam genişlik; eylemler alt satıra geçer, birincil eylem önde kalır.
- Sayfa başlığı ile ilk kart arasında 16–24px boşluk.

### 3.6 Geri bildirim ve flash

- Başarı/hata/uyarı bildirimi içerik akışının en üstünde, sayfa başlığından önce görünür.
- Her bildirim ikon + başlık + açıklama taşır; yalnız renkle anlatılmaz.
- Bildirim kapatılabilir; otomatik kaybolmaz (kritik işlem sonucu kullanıcı tarafından okunmalıdır).
- HTMX sonrası odak ve aria-live bölgesi korunur.

## 4. Kırılımlar ve responsive kurallar

| Genişlik | Navigasyon | İçerik | Ürün listesi |
| --- | --- | --- | --- |
| < 600px | Alt sekme | Tek sütun, 16px | Kart |
| 600–1023px | Alt sekme | Tek/iki sütun, 20px | Kart |
| 1024–1279px | İkon rail 72px | Tablo, 24px | Tablo |
| ≥ 1280px | Tam sidebar 248px | Tablo, 32px, iki sütun | Tablo |

- Telefonda tablolar kart görünümüne dönüşür; her hücre data-label ile etiketlenir.
- Fiyat ve stok değerleri tek satırda kalır; tarih gerekirse iki satıra ayrılır.
- Dokunma hedefleri en az 44px; laptopta 36–40px kabul edilir.
- Modal ve alt sayfalar küçük ekranda taşmaz; içerik dikey kaydırılır.
- Yatay kaydırma yalnızca data-table-scroll kaplarında ve komisyon matrisi gibi zorunlu geniş tablolarda olur.

## 5. Bileşenler

### 5.1 Butonlar

- **Birincil:** accent zemin, beyaz metin; ekranın ana eylemi. Bir ekranda en fazla bir tane.
- **İkincil:** yüzey zemin, 1px kenar; yardımcı eylem.
- **Sessiz (ghost):** kenarsız, hover'da surface-3; tablo içi eylemler.
- **Tehlike:** danger; yalnız silme/iptal. Tehlike eylemi telefonda “Diğer işlemler” altında durur.
- **Boyut:** varsayılan 40px, küçük 32px, mobil 44px. Metin tek satır, ikon + etiket.
- **Devre dışı:** opacity .45, pointer-events none, aria-disabled.
- **Yükleniyor:** metin “Kaydediliyor…” olur, buton disabled; ikinci gönderim engellenir.

### 5.2 Formlar

- Her alanın görünür etiketi vardır; placeholder etiket yerine geçmez.
- Zorunlu alan * ile işaretlenir; yardım metni alanın altında 12px muted.
- Kontrol yüksekliği 40px laptop, 44px telefon; odak halkası 2px accent, offset 2px.
- Hata: alan kenarı danger, altında danger metin; hata özeti formun üstünde.
- Sayı alanlarında inputmode="decimal" veya "numeric"; para alanlarında tr_money formatı korunur.
- Select'lerde ilk seçenek “—” veya “Tümü” olarak açıkça yazılır.
- Form grupları mobilde tek sütun, laptopta en fazla iki/üç sütun.

### 5.3 Segment, sekme ve filtre çipleri

- Segment kontrol: 2–4 seçenek, eşit genişlik, seçili olan accent-soft + accent metin.
- Sekmeler: alt çizgi veya dolgu; aktif sekme aria-selected taşır.
- Filtre çipleri: yatay kaydırılabilir; seçili çip accent, diğerleri yüzey + kenar.
- Filtre uygulandığında “Temizle” eylemi görünür.

### 5.4 Rozetler

- Pill biçiminde, 11–12px, ikon + metin.
- Renkler: success, warning, danger, info, neutral.
- Stok: “Stok: 3”, “Stokta yok”, negatifse “Stok düzeltmesi gerekli”.
- Durum: “Taslak”, “Müşteriye sunuldu”, “Kabul edildi”, “Süresi geçti”, “Arşivde”.
- **Sert kural:** Serbest metin taşıyan rozetler satır kırar. Global `white-space: nowrap` kullanılmaz; tüm rozetlerde `max-width: 100%` ve `overflow-wrap: anywhere` vardır. Uzun kampanya/hediye/ürün adı yatay kaydırma üretmez.
- Teklif satırında kampanya adı rozet değildir; tek satır, ellipsis metin olarak gösterilir. Rozet yalnız kısa durum/etiket bilgisinde kullanılır.
- Flex/grid çocuklarında `min-width: 0`; uzun metin, select veya badge kartı ekran dışına taşıramaz.

### 5.5 Kartlar ve KPI

- Kart: surface, 1px border, 14–16px yarıçap, 16–20px padding, gölgesiz/çok hafif gölge.
- KPI kartı: ikon + etiket, büyük sayı (24–28px mono), altında tek satır bağlam.
- Kart başlığı 16px/600; sağ üstte tek ikincil eylem.
- Kart içinde kart kullanılmaz; bölümler ayırıcı çizgiyle ayrılır.

### 5.6 Tablolar

- 13px, satır yüksekliği 44–52px; başlık 11–12px uppercase muted.
- Başlık sticky; işlem kolonu sağa sabit; seçili satır accent kenar + hafif accent-soft.
- Sayısal kolonlar sağa hizalı, mono; metin kolonları sola.
- İlk kolon seçim checkbox'ı; checkbox 18px, satırın boş alanına tıklama seçimi değiştirir.
- Satır hover'ı yalnız masaüstünde; hover'a bağlı eylem yok.
- Boş sonuç: tablo gövdesinde tek hücre, ikon + açıklama + eylem.
- Geniş tablo kabı data-table-scroll ile işaretlenir; altında her zaman görünür scrollbar ve “Yatay kaydır” ipucu bulunur.
- **Liste tabloları (<1024px):** her satır kart görünümüne dönüşür; surface zemin, 1px kenar, 14px yarıçap ve hafif gölge kullanılır. Alanlar küçük uppercase etiketleriyle gösterilir; seçili ürün accent kenarlıkla işaretlenir.
- **Ürün detay geçmişleri:** <768px'de dikey kart satırları; 768–1023px'de gerçek tablo. Teknik özellikler mobilde grup başlıkları altında özellik/değer çiftleridir.
- Gerçekten iki boyutlu veriler (komisyon oran matrisi gibi) mobilde yatay kaydırılabilir kalır; teknik özellikler ve detay geçmişleri yatay kaydırmaz.

### 5.7 Sayfalama

- Sol: “Toplam N ürün”.
- Sağ: önceki/sonraki, sayfa numaraları, “Sayfaya git” input'u.
- Mobilde sayfa numaraları yerine kompakt “1 / 5” ve önceki/sonraki.
- Filtreler sayfa değişiminde korunur.

### 5.8 Modal ve alt sayfa

- Laptopta ortada, en fazla 560px; telefonda alttan açılan panel, üst köşe 20px.
- Başlık + kapatma, gövde, sticky footer (Vazgeç / birincil eylem).
- Mobilde alt eylemler yan yana ve eşit genişliktedir; Vazgeç solda, birincil sağda. Alt alta yığılmaz.
- Uzun içerik dikey kaydırılır; modal ekran dışına taşmaz.
- Escape kapatır; backdrop'a tıklama kapatır; odak modal içinde kalır.
- İki aşamalı silmede 1. adım uyarı, 2. adım açık teyit butonu; ikinci onay olmadan silme yok.
- Yazdırmada gizlenir.

### 5.9 Akordeon ve kapalı bölümler

- Uzun içerik (özellikler, teknik özellikler, geçmişler, koşullar, iç bilgiler) varsayılan kapalıdır.
- Başlıkta adet yazar: “Teknik özellikler (24)”.
- 48px dokunma yüksekliği, sağda chevron; açıkken chevron döner.
- İç bilgiler (maliyet, kâr, scraper) ayrı ve görsel olarak farklı bir akordeondadır; ilk ekranda açık gelmez.
- Yazdırmada kapalı bölümler basılmaz; yalnız açık bölümler.

### 5.10 Yapışkan çubuklar

- Toplu işlem çubuğu: seçim varken alt sticky; **kapalıyken yalnızca “N ürün seçildi” ve üç noktalı “Toplu işlemler”** görünür.
- Açıldığında “Tümünü seç”, “Seçimi temizle”, kategori atama, arşivleme ve iki onaylı silme aynı panelde yer alır.
- Çubuk yatay kaymaz; eylemler alt alta/iki sütun düzeninde sığar.
- Bar ekranın altına sabittir; alt sekme varsa onun üstünde durur, yoksa `env(safe-area-inset-bottom)` kadar yukarıdan boşluk bırakır.
- Bar açıldığında liste sonuna dinamik boşluk eklenir; son içerik barın arkasında kalmaz. Seçim yoksa bar tamamen gizlenir.
- Sticky eylem çubuğu: odaklı formlarda Vazgeç / Kaydet; alt sekmenin üstünde.
- Her iki çubuk da yazdırmada gizlenir.

### 5.11 Ürün seçimi

- Bağımsız ürün listesi ekranı yoktur.
- Arama kutusu yazdıkça sonuçları getirir; her sonuçta “Ekle” bulunur.
- Ekle, ürünü satır olarak forma ekler; aynı ürün tekrar eklenmez.
- Sonuç yoksa “Eşleşen ürün bulunamadı” metni ve arama temizleme eylemi gösterilir.
- Mobilde sonuçlar kompakt kart; laptopta 4 kolonlu tablo.

### 5.12 Fiyat gösterimi

- Normal fiyat ekranın en büyük metnidir (28–34px mono). Oliz/Web fiyatı ikincil satırdadır.
- Bayi nakit/kart taban fiyatları ayrı kompakt bloklarda gösterilir.
- Fiyat yoksa “—” gösterilir; sıfır fiyat “0,00 TL” olarak gösterilir.
- Kart ve nakit toplamları ayrı; manuel toplam varsa “manuel” etiketi taşır.

### 5.13 Liste ekranı başlığı ve filtre deseni

- Başlık: yalnız h1 ve altında küçük sayı (“12 ürün”, “4 teklif”, “3 rezervasyon”). Pazarlama eyebrow'ı, uzun açıklama veya “fiyat, stok ve kategori yönetimi” gibi tekrar metin yoktur.
- Mobilde birincil eylem (Yeni Ürün/Teklif/Rezervasyon/Kampanya/Sayım) başlığın sağında durur; içe/dışa aktarma ve A4 gibi ikincil eylemler üç noktalı menüye taşınır. Masaüstünde ikincil eylemler görünür kalır.
- Filtre paneli tek ve incedir: birinci satır arama + “Ara”; ikinci satır filtreler yan yana. Mobilde filtreler ikişerli satırlara sarar, alt alta büyük kontroller oluşmaz.
- Filtre çubuğu yatay kaymaz; “Temizle” aynı filtre satırında sağda kalır.
- Tablo altındaki “Toplam N …” satırı her listede korunur.
- Bu desen ürünler, teklifler, rezervasyonlar, kampanyalar, komisyonlar, stok/sayım ve ayarlar listelerinde aynıdır.

## 6. Ekranlar

### 6.1 Ana Sayfa

- Amaç: “Bugün ne yapmam gerekiyor?” ve “Nereye gitmem lazım?” sorularına tek bakışta cevap.
- Üstte yalnız günün tarihi; “Merhaba/günün özeti” başlığı ve açıklama yoktur.
- Hemen altında hızlı işlemler: Yeni Teklif, Yeni Rezervasyon, Stok Sayımı, Ürün Ekle. Başlık dışında açıklama/ghost text yoktur.
- Sonra hatırlatmalar; gecikmiş kırmızı, yaklaşan amber; satıra dokunma rezervasyonu açar.
- Hatırlatmaların altında 4 KPI: Açık Teklif, Açık Rezervasyon, Gecikmiş Hatırlatma, Aktif Kampanya.
- En sonda son teklifler ve son rezervasyonlar.
- Modül kartları yoktur; navigasyon zaten yan/alt sekmelerdedir.
- Telefon sırası: tarih → hızlı işlemler → hatırlatmalar → KPI → son teklifler → son rezervasyonlar.
- Laptop: tarih + hızlı işlemler üstte; altta solda hatırlatmalar + KPI, sağda son teklifler + son rezervasyonlar.
- Veri yoksa boş durum metni; sahte sayı gösterilmez.

### 6.2 Ürünler (liste)

- Başlık: “Ürünler” ve altında yalnız ürün sayısı; uzun açıklama yok.
- Eylemler: Yeni Ürün (birincil), İçe Aktar, Dışa Aktar (CSV/Excel).
- Arama/filtre çubuğu sticky: arama kutusu + Ara, durum filtresi, kategori filtresi, Temizle.
- Arama HTMX ile tabloyu yeniler ve URL'yi korur.
- Laptop tablosu: seçim, Ürün Adı + ID, Kategori, Normal Fiyat, Oliz, Fiziksel Stok, Son Fiyat Değişimi, İşlem.
- Telefon kartı: ürün adı + ID; kategori rozeti (etiketsiz, adın altında); normal ve Oliz fiyatı; stok rozeti; stok güncelle + detay. “Son fiyat değişimi” yalnız masaüstünde; mobilde ekstra “Kategori/Fiziksel Stok/İşlem” sütun etiketleri gösterilmez.
- Arşivdeki ürün soluk + “Arşivde” rozeti.
- Toplu seçim çubuğu yukarıdaki kurallara uyar.
- Boş sonuç ve arama eşleşmemesi ayrı metinlerle bildirilir.

### 6.3 Ürün detayı

- Sıra: geri bağlantısı, başlık + kategori/arşiv rozetleri, **katlanabilir “Fiyat ve stok”**, **katlanabilir “Aktif Kampanyalar”**, diğer kapalı bölümler.
- Başlık meta: yalnız güncel scraper ID ikincil metin olarak; kayıt numarası ve kategori grubu burada gösterilmez, “İç Bilgiler” bölümünde yer alır.
- Fiyat hero'su: **normal fiyat en büyük metin**; Oliz/Web fiyatı ikincil satırda; nakit/kart taban ayrı kompakt bloklarda; stok ve açık rezervasyon ayrı dikey bilgi listesinde. Aynı veri iki yerde tekrarlanmaz.
- Birincil eylemler: “Teklife Ekle”, “Rezervasyon Aç”. İkincil: Düzenle, Stok Güncelle, Arşivle, Sil (Diğer işlemler altında).
- Aktif kampanyalar: ad, geçerlilik, durum, indirim/hediye, hediye var/yok bayi senaryosu; mobilde tek sütun. Bölüm başlığından açılıp kapanır; kampanya yoksa kapalı başlar. Bölümde tek “Kampanyalar” bağlantısı bulunur; başlık veya buton tekrar edilmez.
- “Fiyat ve stok” bölümü varsayılan açık; aktif kampanyalar varsa açık, yoksa kapalı başlar. Tüm detay bölümleri başlıktan açılıp kapanabilir.
- “Fiyat ve stok” tek dış karttır; içinde ayrı fiyat ve stok kartları yoktur. Aktif kampanyalar açıklama/buton olmadan satır listesidir; kampanya kartları dış kart içinde ayrı kutu değildir.
- Kapalı bölümler: Ürün özellikleri (N), Teknik özellikler (N), Bayi fiyat geçmişi, Fiyat geçmişi, Stok hareketleri, İç bilgiler.
- Teknik özellikler: masaüstünde tablo; mobilde grup başlıkları altında özellik/değer çiftleri. Uzun adlar satır kırar; tüm satırlar korunur.
- Fiyat/stok geçmişi: masaüstünde tablo; mobilde (<768px) dikey kart satırları. Tüm alanlar korunur; kayıt yoksa sade boş durum.
- İç bilgiler: alış maliyeti, kâr marjı, scraper ID/tür/kaynak/tarih. İlk ekranda görünmez; uzun ID ve bağlantılar taşmaz.
- **Mobil (<768px):** “Teklife Ekle” ve “Rezervasyon Aç” alt sabit aksiyon alanındadır; diğer eylemler “Diğer işlemler” menüsünde kalır. İçerik için alt boşluk ve safe-area ayrılır.
- **Masaüstü (≥768px):** mevcut aksiyon düzeni ve iki sütunlu hero korunur.
- Modallar: düzenleme mobilde tam ekrana yakın; stok/bayi fiyatı alt sayfa. Formlar tek sütun; gövde kayar; alt eylemler yan yana ve görünür kalır. İki aşamalı silme korunur.
- Ürün düzenleme modalında kategori atama alanı yoktur; kategori yönetimi Ayarlar’dadır.
- Aktif kampanya satırında “Kampanyayı aç” eylemi indirim/hediye bilgi satırının sağındadır; mobilde “Aç” olarak kısalır.
- “Fiyat ve stok” ile kampanya satırlarının üst/alt boşlukları aynı ritimdedir; iç içe kart yoktur.

### 6.4 Kampanyalar

- Liste: arama, tip, durum ve tarih filtresi; kart/tablo; sayfalama.
- Satır/kart: ad, tip, geçerlilik, durum, indirim/hediye özeti, ürün sayısı.
- Mobil kampanya kartı: 1. satır ad + durum; 2. satır tip + geçerlilik; 3. satır indirim/hediye + ürün sayısı; altta tek eylem. Açıklama mobil listede gizlenir, ad en fazla 2 satır.
- Detay: sürüm geçmişi, ürün ilişkileri, hediye senaryosu, kaynak bilgisi, Koşullar (kapalı), içe/dışa aktarma.
- Form: ad, tip, tarihler, açıklama, fiyat tabanı, indirim türü/değeri, hediye, çalışan notu, ürün ilişkileri.
- Telefonda düzenleme uyarı notu; laptop öncelikli.

### 6.5 Teklifler

- Liste: arama, durum/tarih filtresi, tablo (laptop) / kart (telefon); Ürünler tek sütun.
- Mobil teklif kartı: 1. satır teklif no + müşteri + durum; 2. satır ürün özeti (tek satır, ellipsis); 3. satır tarih · ödeme · toplam; altta aksiyonlar. Gereksiz sütun etiketleri gösterilmez.
- Form tek akış: **Müşteri → Sepet (ürün ekleme en üstte) → Ödeme ve İndirimler → Toplamlar → Senaryo Özeti → Taksit Seçenekleri**. Masaüstünde de tek sütun, azami 1080px.
- Müşteri bölümünde yalnız ad ve not; telefon alanı gösterilmez, düzenlemede mevcut değer gizli alanla korunur. Müşteri açıklama metni yoktur.
- Ürün ekleme sepetin içindedir; arama en fazla 3 sonuç gösterir. Sonuçta kampanya rozeti yoktur; “Ekle” her zaman görünür.
- Ödeme ve indirimler ayrı kart değil, sepet içinde açılır bölümdür.
- Sepet toplamları kart değil, ince bir özet satırıdır; manuel nakit/kart toplamı alanları hemen üstündedir.
- Senaryo Özeti toplamların hemen altında, açılır-kapanır ve varsayılan açık; ürün/ödeme değişince otomatik güncellenir.
- Taksit Seçenekleri sepetin altında, kapalı başlayan açılır bölümdür. Seçim kolonu masaüstünde sağa sabittir; mobilde her seçenek kart olur, ikincil kolonlar gizlenir ve “Seç” butonu tam genişliktedir. Seçim yapıldığında bölüm otomatik kapanır.
- Sepet toplamlarında etiket ve değer “Normal Toplam: 82.998,00 TL” biçimindedir; bitişik/etiketsiz metin üretilmez.
- Uzun kampanya adları badge içinde satır kırar; mobilde sağa taşmaz.
- Tablolar kart içine gömülü değil, bölümün kendisidir; ekstra çerçeve/gölge yoktur.
- Satır: ürün, miktar, kampanya, hediye, normal/Oliz/kampanya fiyatı, maliyet, nakit/kart birim fiyatı.
- Sticky eylem çubuğu: Vazgeç / Kaydet.
- Detay: toplamlar, kâr/komisyon kartı, durum geçmişi, A4, rezervasyon/teslim eylemleri, silme (iki onay). Mobilde kâr/komisyon ve teklif satırları tablo değil karttır; yatay kaydırma yoktur.
- Telefonda “fiyat verme” odaklı akış; iç kâr/komisyon ilk ekranda değil, kapalı “İç bilgiler” bölümünde.

### 6.6 Rezervasyonlar

- Liste: müşteri araması, durum filtresi, sayfalama; masaüstü tablo, telefon kart.
- Kart/satır: no, müşteri, tarih, hatırlatma, özet durum, açık/toplam miktar, ürünler.
- Mobil rezervasyon kartı: 1. satır no + müşteri + durum; 2. satır ürün özeti; 3. satır tarih + hatırlatma + açık/toplam; altta eylem.
- Yeni: müşteri adı (zorunlu), tarih, not; ardından **“Rezerve Ürünler”** bölümü. Ürün arama bu bölümün içindedir, en fazla 3 sonuç gösterir; sepet/ödeme/indirim alanı yoktur.
- Detay: 5 metrik özet (durum, toplam, teslim, iptal, açık), dikey ürün satırı kartları, teslim/iptal/miktar/satır ekleme, hareket ve erteleme geçmişi (kapalı).
- Telefonda teslim/iptal büyük butonlar; laptopta tablo + satır işlem paneli.
- A4 depo/bayi kopyası.

### 6.7 Komisyonlar

- Liste: dönemler, durum, tarih aralığı; yeni dönem kopyalama; içe/dışa aktarma.
- Detay: kanal sekmeleri (POS, Ödero, Chippin), oran matrisi, kategori limitleri, banka bazlı limit tablosu, kategori-grup eşlemesi, geçmiş, A4.
- Oran matrisi: satır banka/kanal, sütun taksit; hücrede oran. Laptopta tablo, telefonda yatay kaydırılabilir veya gruplu kart.
- Limitler: kategori limitleri (bankadan bağımsız) ve banka/kanal/kart tipi limitleri ayrı bölümlerde; etkin üst sınır canlı önizlenir.
- Telefonda okuma öncelikli; düzenleme mümkün ama laptop önerilir.

### 6.8 Stok / Sayım

- Üstte açık oturumlar ve sayım geçmişi iki iç sekme; açık oturumlar en üstte.
- Kategori filtresi ve arama otomatik; “Ara” gerekmez.
- Stok özeti: ürün, kategori, fiziksel stok, açık rezervasyon, fark.
- Sayım oturumu: satır bazında sistem stoku, sayılan miktar (büyük input), fark; sticky “Miktarları Kaydet”.
- Telefonda sayım girişi büyük dokunma hedefleriyle; laptopta tablo.
- A4 sayım listesi kategori bazlı.

### 6.9 Ayarlar

- Bankalar ve Kategoriler sekmeleri.
- Bankalar: ad, aktif/pasif, kullanım sayıları; tekli/toplu ekleme, yeniden adlandırma, pasifleştirme, birleştirme, iki onaylı silme, Excel içe/dışa.
- Kategoriler: ad, komisyon grubu, kullanım sayıları; tekli/toplu ekleme, yeniden adlandırma, grup değiştirme, birleştirme, kullanılmayanı silme, Excel içe/dışa.
- Telefonda kart, laptopta tablo; toplu ekleme önizlemesi.
- Backend'i olmayan bayi profili/maliyet toggle'ı/bildirim toggle'ı yoktur.

### 6.10 İçe/dışa aktarma

- Akış: dosya seç → önizleme → satır/toplu karar → tek transaction.
- Önizleme: yeni/güncellenecek/hatalı sayaçları, hatalı satırlar en üstte.
- Mobilde “Bu işlem laptopta daha rahattır” notu; tablo data-table-scroll.
- Onay olmadan veri yazılmaz; sonuç Türkçe özet bandıyla gösterilir.

### 6.11 A4 ve yazdırma

- Üst çubuk, sol menü, alt sekme, sticky çubuklar ve modal backdrop basılmaz.
- Müşteri çıktısında maliyet, iç kâr ve komisyon detayı yoktur.
- Sayfa A4, 15mm kenar; başlık, tarih, sayfa numarası.
- Kapalı akordeonlar basılmaz.
- Faz 4'e kadar ekran UI'ı yenilenir, A4 içeriği değişmez.

## 7. İçerik ve dil

- Tüm kullanıcı metinleri Türkçe; cümle düzeni, tutarlı terimler.
- Tarih: 10.11.2026; uzun: 10 Kasım 2026; saat dilimi Europe/Istanbul.
- Para: 38.199,00 TL; yüzde: %10.
- Kısaltma kullanılmaz: “Rez.” yerine “Rezervasyon”, “Tek.” yerine “Teklif”.
- Hata mesajı ne oldu ve ne yapmalı sorusunu yanıtlar; teknik İngilizce metin görünmez.
- Buton metni eylem fiili: “Kaydet”, “Sil”, “Arşivle”, “Rezervasyon Aç”.

## 8. Erişilebilirlik

- Tüm etkileşimli öğeler klavye ile erişilebilir; görünür odak halkası.
- Menü durumu aria-expanded/aria-controls; aktif sayfa aria-current="page".
- Modal açıldığında odak modal içine taşınır; Escape kapatır; kapanınca odak tetikleyiciye döner.
- Form hataları aria-describedby ile alana bağlanır.
- Renk kontrastı WCAG AA; renk tek başına anlam taşımaz.
- Tablo başlıkları th ile; checkbox'larda aria-label.
- reduced-motion desteklenir.
- Dokunma hedefleri en az 44px.

## 9. Performans ve varlıklar

- CDN yok; çalışma zamanı internet bağımlılığı yok.
- Fontlar, HTMX, Alpine, Flatpickr ve ikon sprite'ı yerel vendor klasöründedir; VERSIONS.txt hash'leri güncel tutulur.
- Görsel asset yoksa CSS ile çözülür; büyük arka plan görselleri kullanılmaz.
- İlk yüklemede kritik CSS tek dosyada; JS defer.
- HTMX yalnız kısmi güncelleme, Alpine yalnız yerel durum için.
- Tablolar 5.000 ürünle akıcı kalmalı; gereksiz DOM ve inline stil azaltılır.

## 10. Kapsam dışı

- Kimlik doğrulama, rol/yetki ekranları.
- WhatsApp/SMS paylaşımı, barkod/kamera, hızlı teslim.
- PWA kurulumu, çevrimdışı mod.
- Koyu tema (ayrı faz).
- Backend'i olmayan bildirim merkezi, profil, hedef/progress kartları.
- CDN, Tailwind, Node/CSS build adımı.

## 11. Uygulama ve kabul

Bu sözleşme [ui-redesign-plan.md](./ui-redesign-plan.md) ile fazlara ayrılmıştır. Her fazın kabulü:

- 320/390/768/1024/1280/1440px'de yatay kaydırma yok (zorunlu tablo istisnası hariç).
- Telefonda alt sekme, laptopta rail/sidebar doğru.
- Birincil eylem tek, tehlike eylemleri iki onaylı.
- Tüm fiyatlar tek satırda ve doğru biçimde.
- Klavye ile menü, modal ve form akışı çalışır.
- uv run ruff check src tests ve uv run pytest -q temiz.
- ui.md ile çelişen yeni bir UI kararı eklenmez; değişiklik önce bu dosyaya yazılır.
