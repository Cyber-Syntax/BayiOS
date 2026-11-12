# todo.md

- [x] ürünler'e kategoriler eklenmeli, örnek 10122 çamaşır vb.
- [x] stok sayım kağıdı çamaşır/kurutma şeklinde ayırmalı
- [ ] içe/dışa aktarmada kategori kolonu (import opsiyonel, export zorunlu)
- [ ] stok sayım sekmesinde kategori seçince otomatik filtre
- [ ] eğer boyut küçük olursa, ürünler sekmesinde tüm kartı boş alanlara tıklayınca seçebiliyorum ama eğer window boyutu büyük olursa sadece checkbox ile seçebiliyorum. Bunu değiştir; büyük olunca da kartta boş alana tıklayınca ürün seçilsin.
- [ ] sadece seçilmiş ürünleri excel ile dışa aktar
- [ ] sadece kategorisi seçilmiş ürünleri excel ile dışa aktar.
- [ ] a4 sayım listesi, kategori seçince, o kategori için çıkartsın, tüm kategoride tüm kategori için a4 sayım listesi çıkartsın.
- [ ] sayım geçmişi ve açık sayım oturumları yukarıda olsun ama yer kazanmak için iki tane iç sekme olarak görünsünler.
- [ ] tekliflerde aynı zamanda yukarıda toplam komisyonlu detayı göstermemiz lazım, örnek toplam kazanç, toplam komisyonlar çıkınca bayiinin hakedişler ile toplam kazancı.
- [ ] feat: ürünler boş satıra tıklayınca seçilsin, küçük ekranda bu özelik var ama ekran büyük olunca yok?
- [x] feat: kampanya detaylarını excel ile iç/dış aktar
- [ ] feat: teklif detayları excel ile iç/dış aktar
- [ ] feat: rezervasyon detaylarını excel ile iç/dış aktar
- [ ] teklif üzerinden otomatik rezerve açma
- [ ] tekliften otomatik ürün satışı yaparak stok düşme
- [ ] ürünler detayında kapalı rezervasyonlar olarak gösterebiliriz.

## in-progress

- [x] refactor: tekliflerden detay butonu silinebilir, kar komisyon özeti zaten tüm satırların aynılarını gösteriyor.
- [x] style: ürün içe aktarma önizlemesi sağa doğru kaydırmalı olmuş ama küçük ekranlarda zor olur, alt tarafa sticky scroll bar lazım.

## good-to-have

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
