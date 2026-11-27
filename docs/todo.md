# todo.md

- [ ] eğer boyut küçük olursa, ürünler sekmesinde tüm kartı boş alanlara tıklayınca seçebiliyorum ama eğer window boyutu büyük olursa sadece checkbox ile seçebiliyorum. Bunu değiştir; büyük olunca da kartta boş alana tıklayınca ürün seçilsin.
- [ ] sadece seçilmiş ürünleri excel ile dışa aktar
- [ ] sadece kategorisi seçilmiş ürünleri excel ile dışa aktar.
- [x] A5 sayım listesi, kategori seçince o kategori için, tümünde kategori gruplarıyla çıksın; sadece stokta olanlar ve rezervasyonu olan ürünler ayrı filtrelenebilsin.
- [x] hızlı sayım: boş oturumda ürün arayıp yalnızca yazılan ürünleri sayma.
- [x] sayımı bazı ürünler sayılmasa bile kapatabilme; 0/boş satırların stoğunu değiştirmeme.
- [x] sayımı iptal etme ve tamamlanmış sayımı ters kayıtla geri alma.
- [x] sadece stokta olanları Excel ile dışa aktarma.
- [x] 0 = stok yok kuralı; negatif stok desteği korunarak.
- [ ] sayım geçmişi ve açık sayım oturumları yukarıda olsun ama yer kazanmak için iki tane iç sekme olarak görünsünler.
- [ ] tekliflerde aynı zamanda yukarıda toplam komisyonlu detayı göstermemiz lazım, örnek toplam kazanç, toplam komisyonlar çıkınca bayiinin hakedişler ile toplam kazancı.
- [ ] feat: teklif detayları excel ile iç/dış aktar
- [ ] feat: rezervasyon detaylarını excel ile iç/dış aktar
- [ ] feat: teklif silme
- [ ] tekliften otomatik ürün satışı yaparak stok düşme
- [ ] ürünler detayında kapalı rezervasyonlar olarak gösterebiliriz.
- [ ] feat: database backup otomatikleştirmek
- [ ] feat: hızlı tüm komisyon, ürün vb. bilgilerin hepsini tek bir kerette excel ile dışarı almak, tüm excel dosyalarını. Ayarlar backup'a eklenebilir. Buna mantıksal veri dışa/içe aktarma json veya excel. Aynı zamanda json auto backup ile wsl backup yaparız, günlük, saatlik?

- [x] feat: bankalara kart ağı (World/Bonus/Maximum/Axess/Paraf/Flexi …) etiketi; Ayarlar ekranında yönetim; kampanya ödeme koşulunda "tüm World kartlar" gibi kart ağı hedefleme. (Kısa vadede kampanya koşulunda doğrudan banka adları kullanılır.)

## teklif sorunları

- [ ] **Nakit/kart geçişinde satır fiyatları güncellenmiyor.** Teklif formunda ödeme tipi nakit ↔ kart yapıldığında satır bazlı `unit_price_cash` / `unit_price_card` değerleri eski değerde kalıyor; çünkü iki alan da dolu ve JS yalnız kampanya etiketini/fiyatını güncelliyor. Ödeme tipi, bayi indirimi, kampanya veya miktar değişince seçili ödeme tipine göre satır fiyatı yeniden hesaplanmalı; kullanıcı elle fiyat girmedikçe diğer ödeme tipinin eski değeri kullanılmamalı. Ayrıca kayıt sırasında seçili ödeme tipi dışındaki alanlar temizlenmeli veya yok sayılmalı.
- [ ] Teklifte karma ürün grubu (Klima + Diğer) komisyonu yalnız ilk satırın grubuna göre çözülüyor; sepet genelinde en kısıtlayıcı/doğru grup çözülmeli.
- [ ] Teklif kaydından sonra toplam satış, komisyon sonrası net, toplam kampanya hakedişi ve toplam Oliz hakedişi tek özet tablosunda gösterilmeli.

## in-progress

- [x] stok sayım sekmesinde kategori seçince otomatik filtre
- [x] içe/dışa aktarmada kategori kolonu da olmalı
- [x] ürünler'e kategoriler eklenmeli, örnek 10122 çamaşır vb.
- [x] stok sayım kağıdı çamaşır/kurutma şeklinde ayırmalı
- [x] teklif üzerinden otomatik rezerve açma
- [x] feat: kampanya detaylarını excel ile iç/dış aktar
- [x] refactor: tekliflerden detay butonu silinebilir, kar komisyon özeti zaten tüm satırların aynılarını gösteriyor.
- [x] style: ürün içe aktarma önizlemesi sağa doğru kaydırmalı olmuş ama küçük ekranlarda zor olur, alt tarafa sticky scroll bar lazım.

## good-to-have

- [ ] style: mobilde responsive ui araştırması yap, belki excel gibi olmak yerine başka alternatif productive vardır.
- [ ] ürün stok hareket geçmişindeden teklifi açıp görebilme özeliği eklenmeli
- [ ] ürün eklerken, seçme box'ta kategori ekleyebilme
- [ ] rezervasyonlar daha düzgün filtrelensin, şu an ilginç bir filtreleme var.
- [ ] style: excel komisyon butonları oranlar solda, limitler sağda olsun
- [ ] feat: add shell script for auto podman setup?
- [ ] Bayi os resimlerini readme.md ekle
- [ ] tüm sayfalarda en yukarıdaki sidebar button, ürün ara input box sticky olması gerekiyor, aşağı scroll ederken kesinlikle yukarıda olması lazım ki hızlıca side bar kullanılabilsin, productive olsun.
- [ ] rezervasyonlar için bildirim özelliği, en mantıklısı bildirimler sekmesi yapmak çünkü popup ile productivity bozulur, en mantıklısı yeni bir bildirimler sağ sidebar açarız, süre geçince oraya düşer.
- [ ] belki kanban todo list eklenebilir?
- [ ] sayım takviminde kasım/ekim tıklanınca ay seçme ekranı gelsin.
- [ ] Sayım takvim seçiminde pek iyi değil, daha kaliteli bir alternatif veya daha düzgün seçme olmalı.
- [ ] ürünlere tekliften tıklanınca popup ile düzenleme, detay açılabilsin?
- [ ] tekliflerde satır başı komisyon detayı gösteriyor, onları altta kısaca ghost text olarak gösterebiliriz.

## bir ara düzelt

1. "5cd2c026-165a-48dd-abda-f3b099fdb8d5?msg=error%3ABu+komisyon+oranı+bu+dönem+için+zaten+tanımlı.+Mevcut+satırı+düzenleyin." -> detay göstermek yerine, error vs. bir şey yazsa url clean olur.
