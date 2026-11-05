# BayiOS UI/UX Prototip Sözleşmesi

Bu belge, BayiOS MVP'sinin rol-bağımsız UI/UX yönünü ve `prototype/index.html` içindeki doğrulama prototipinin sınırlarını tanımlar. Üretim backend'i veya kimlik doğrulama davranışı değildir.

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

Ana Sayfa varsayılan ekrandır. Üst arama tüm ekranlardan ürün aramaya götürür.

## Görsel yön

- Ferah, minimal ve satışa indirgenmemiş operasyon arayüzü.
- Açık zemin, lacivert/indigo vurgu, sakin durum renkleri ve net tipografi.
- Ürünlerde kartlar; operasyon listelerinde tablo, filtre ve durum rozetleri.
- Renk tek başına anlam taşımaz; durumlar metinle birlikte gösterilir.
- Masaüstü sunum önceliklidir; 390px genişlikte temel işlemler yatay kaydırma olmadan çalışır.

## Ekran kapsamı

Ana sayfa ürün araması, operasyon kuyruğu ve KPI özetini gösterir. Ürünler → teklif → rezervasyon, rezervasyon → teslimat ve stok/sayım akışları derin etkileşim içerir. Kampanyalar, Hızlı Teslim ve Ayarlar gezilebilir, ancak prototipte daha hafif ekranlardır.

## Davranış sözleşmesi

- Mock state oturum süresince korunur; yenileme sonrası kalıcılık yoktur.
- Teklifler çok ürünlüdür ve iç ekranda maliyet/kâr görülebilir.
- Müşteri yazdırma görünümünde maliyet/kâr gizlenir.
- Rezervasyon oluşturmak fiziksel stoğu düşürmez.
- Fiziksel stok 5 ve açık rezervasyon 2 ise satılabilir stok 3'tür. Bir teslimat sonrası fiziksel stok 4 olur.
- Başarı, hata ve boş durumları görünür metinle bildirir.
- CSV, kamera, gerçek barkod çözümleme, backend ve auth prototip kapsamı dışındadır; Hızlı Teslim yalnızca akış hissini mock'lar.

## Prototip sınırı

`prototype/index.html` gömülü CSS ve JavaScript ile doğrudan tarayıcıda açılabilir. Üretim bileşen kütüphanesi, API sözleşmesi ve kalıcı veri modeli bu prototipin konusu değildir.
