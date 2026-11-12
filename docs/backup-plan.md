### B. Mantıksal veri dışa/içe aktarma (JSON/Excel)

- Ürünler, kampanyalar, teklifler, rezervasyonlar gibi tablo/tablo grupları.
- İnsan tarafından okunabilir, versiyonlanabilir, kısmi aktarım yapılabilir.
- Çakışma/merge kuralları gerekir.
- Mevcut Excel import/export altyapısı bunun büyük kısmını zaten çözüyor.

**Ayarlar’a konulacak şey bence B olmalı; A için sadece “son yedek durumu” ve belki admin indirme linki olmalı.**

---

## 2. Ne kadar sürer?

| İş                                             |     Zorluk | Gerçekçi süre | Not                                   |
| ---------------------------------------------- | ---------: | ------------: | ------------------------------------- |
| Mevcut `backup.sh`’i zamanlamak                |      Kolay |      1–2 saat | Script zaten var                      |
| Backup durum sayfası (son yedek, boyut, tarih) | Kolay/Orta |     0.5–1 gün | Auth yoksa dikkat                     |
| UI’dan backup indirme                          |       Orta |       2–4 gün | Uzun süren işlem, geçici dosya, yetki |
| UI’dan restore yükleme                         |        Zor |     1–2 hafta | Önerilmez; test matrisi büyük         |
| Modül bazlı JSON export/import                 |       Orta |       2–4 gün | Excel altyapısı var                   |
| Auth + rol + audit                             |        Zor |     1–2 hafta | Production için asıl eksik            |
| Monitoring/alerting                            |       Orta |       2–3 gün | Backup yaşlandı uyarısı dahil         |

Yani “hızlıca yapsan ne kadar sürer?” sorusunun cevabı:

- **Sadece backup alma + durum gösterme:** 1–2 gün.
- **UI’dan güvenli backup indirme:** 3–5 gün.
- **UI’dan restore:** 1–2 hafta ve bence gereksiz risk.

---

## 3. Otomatik backup yapılabilir mi?

**Evet, zaten altyapısı var.** [backup.sh](scripts/backup.sh):

- `pg_dump -Fc` ile günlük yedek alıyor.
- Haftalık/aylık saklama kopyaları var.
- `BACKUP_EXTERNAL_DIR` ile ikinci diske kopyalama var.
- Eski yedekleri temizliyor.
- Disk alanı kontrolü yapıyor.
- [restore.sh](scripts/restore.sh) scratch DB’ye restore edip sayım doğruluyor.

Windows’ta en sağlam yol **Görev Zamanlayıcı**; uygulama içinde `background task` ile backup almak bence yanlış:

- Uygulama kapalıyken backup çalışmaz.
- Uzun süren `pg_dump` web worker’ını bloklar.
- Container içinde `pg_dump`/credential yönetimi gerekir.
- Hata görünürlüğü zayıf olur.

Doğru yapı:

1. Host’ta günlük `backup.sh` çalışsın.
2. Yedek harici diske de kopyalansın.
3. Ayarlar’da sadece “son yedek ne zaman alındı, başarılı mı, boyutu ne, son restore testi ne zaman” görünsün.
4. Backup 24 saatten eskiyse uyarı versin.
5. Ayda bir restore tatbikatı yapılsın.

**Restore testi yapılmayan yedek, yedek değildir.** Mevcut runbook bunu doğru şekilde tarif ediyor.

---

## 4. Uygulama alpha; database stability ne kadar?

İki ayrı stability var:

### Kod/veri bütünlüğü

Bu proje fena değil:

- Transactional `UnitOfWork` var.
- DB constraint’leri var.
- Idempotency var.
- 252 test geçiyor.
- Migration disiplini var.
- Stok/rezervasyon/teklif snapshot mantığı düşünülmüş.

Tek kullanıcılı, LAN içi, düşük eşzamanlı bir bayi için **veri bütünlüğü tarafı makul seviyede**.

### Operasyonel stability

Alpha için hâlâ zayıf noktalar:

- Tek host, tek PostgreSQL instance; HA yok.
- Auth/rol yok; LAN’a güveniyorsun.
- Otomatik backup henüz kurulmamış olabilir.
- Monitoring/alerting yok.
- Restore tatbikatı düzenli değilse risk büyük.
- Disk arızası / yanlış migration / yanlış restore = veri kaybı.
- Uygulama hataları olabilir; pilot şart.

Yani:

- **Kontrollü pilot için:** evet, kullanılabilir.
- **7/24 kritik, tek başına güvenilir production için:** henüz değil.
- **İnternete açık production için:** auth/rol/HTTPS olmadan kesinlikle hayır.

---

## 5. Production’da ne zaman kullanmaya başlayabilirsin?

Benim önerim 3 aşama:

### Aşama 1 — Kontrollü pilot (şimdi başlayabilir)

Şunlar sağlanırsa:

- LAN-only, port forwarding yok.
- Firewall sadece bayi subnet’ine izin veriyor.
- Günlük backup çalışıyor.
- Harici disk kopyası var.
- Bir restore tatbikatı başarıyla yapılmış.
- Gerçek veriyle 1 hafta pilot.

Bu aşamada “production” değil, **pilot production** dersin.

### Aşama 2 — Güvenli production (2–4 hafta)

Pilot sonrası:

- Kritik hatalar kapatılır.
- Backup otomasyonu + yaş uyarısı.
- Aylık restore testi.
- Monitoring/alerting.
- Migration öncesi zorunlu backup prosedürü.
- Auth/rol eklenir (en azından yönetici/çalışan ayrımı).
- HTTPS/reverse proxy (LAN içinde de olsa iyi olur).

### Aşama 3 — İnternete açma

Bunu önermiyorum. Açılacaksa:

- Auth + rol + kayıt sahipliği
- HTTPS
- Rate limiting
- Audit log
- Yedekleme/restore otomasyonu
- Güvenlik gözden geçirmesi

şart.

---

## 6. Net önerim

1. **Ayarlar’a raw DB restore koyma.** Bu alpha’da tehlikeli.
2. **Ayarlar’a backup durumu koy:** son yedek, boyut, yaş, son restore testi.
3. **Backup’ı host/Görev Zamanlayıcı ile otomatikleştir.** Uygulama içine gömme.
4. **Harici disk + aylık restore tatbikatı** standart olsun.
5. **Production kararını “auth + backup + restore testi + monitoring” tamamlanınca ver.**
6. **Şu an LAN-only pilot için hazır sayılabilir; geniş production için 2–4 hafta daha hardening gerekir.**

Özetle: **backup almak kolay, restore’u güvenli yapmak zor.** Bu yüzden backup’ı UI’a değil operasyona, restore’u da CLI’a koymak en sağlıklısı.
