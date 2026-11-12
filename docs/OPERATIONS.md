# BayiOS Operations Runbook

BayiOS'u kontrollü bayi LAN'ında Podman Compose ile çalıştırmak için operasyon rehberi. Hedef ortam: **Windows 11** host, Podman + PostgreSQL 17 (Compose üzerinden).

Bu runbook bir sözleşmedir: aşağıdaki sınırlar (LAN-only, DB portunun publish edilmemesi, backup) korunmadan uygulama üretimde çalıştırılmaz.

---

## 1. Ön koşullar

- Windows 11 host, Podman (Podman Desktop veya Podman Machine) kurulu ve `podman compose` çalışıyor.
- Host üzerinde `git` ve (backup zamanlaması için) Görev Zamanlayıcı erişimi.
- Bayi LAN'ına sabit/kalıcı IP veya mDNS ile erişilebilen bir host adı.
- Repository'nin bir kopyası (`BayiOS`) host'ta.

## 2. Compose sınırı

- `app` ve `postgres` ayrı servislerdir (`compose.yaml`).
- **PostgreSQL yalnızca Compose internal network'ünde dinler; host/LAN portu publish edilmez.**
- Yalnızca `app` HTTP portu (`BAYIOS_PORT`, varsayılan 8000) LAN'a publish edilir.
- DB verisi named volume'da (`bayios_pgdata`); backup çıktısı host dizininde ayrı diskte tutulur.
- Production secret'ları image veya repository içine girmez; `.env` dosyasından gelir.

## 3. İlk kurulum

1. Secret'ları hazırla:
   ```powershell
   copy .env.production.example .env
   # .env içinde POSTGRES_PASSWORD değerini uzun ve rastgele bir değerle değiştir.
   ```
2. Image'ı build et ve servisleri başlat:
   ```powershell
   podman compose build
   podman compose up -d postgres
   podman compose run --rm app alembic upgrade head
   podman compose up -d
   ```
3. Sağlığı doğrula:
   ```powershell
   podman compose ps
   curl http://localhost:8000/health
   # => "status": "ok", "database": "ok", "migrations": {"status": "ok"}
   ```

## 4. Ağ ve güvenlik (zorunlu — auth yok)

MVP'de kullanıcı girişi/rol yoktur (bkz. PRD §2.2). Bu yüzden uygulama **internete açılmamalıdır**:

- Host firewall'da yalnızca bayi LAN subnet'inden `BAYIOS_PORT`'a izin ver.
- Modemde **port forwarding yapılmamalı**; uygulama public URL'e bind edilmemelidir.
- Misafir (guest) Wi-Fi ağından ayrılmalı; misafir ağ cihazları uygulamaya erişememelidir.
- PostgreSQL portu doğrudan istemcilere açılmaz (compose'da publish yok).
- Uzaktan erişim/VPN istenirse önce kullanıcı hesabı + rol + kayıt sahipliği eklenmelidir (PRD §2.2).

## 5. Backup

Backup, uygulama request'inin içinde çalışmaz; ayrı komuttur (`scripts/backup.sh`):

- `pg_dump -Fc` ile günlük veritabanı yedeği alır.
- Haftalık (Pazar) ve aylık (ayın 1'i) uzun saklama kopyaları ayrı dizinlerde tutulur.
- `BACKUP_EXTERNAL_DIR` tanımlıysa host'tan bağımsız harici diske kopya alır.
- Başarısızlık exit code ve log ile görünürdür; hedef dizinde yeterli alan kontrol eder.
- Backup job'ı production DB volume'unu silmez ve migration çalıştırmaz.

Windows'ta günlük tetikleme (Görev Zamanlayıcı → Yeni Görev):
- Eylem: `wsl bash -lc "/path/to/BayiOS/scripts/backup.sh"` (WSL varsa) veya Git Bash tam yolu.
- Tetikleyici: günlük, mesai bitişine yakın bir saat.
- Görevi kullanıcı günlükte çalıştır; `BACKUP_DIR` / `BACKUP_EXTERNAL_DIR`'ı görev ortamında veya script öncesi export ederek ayarla.

## 6. Restore tatbikatı

En az aylık (ve her migration öncesi):

1. Production volume'una dokunmadan mevcut dump'ı scratch DB'ye geri yükle:
   ```powershell
   bash scripts/restore.sh /var/lib/bayios-backups/daily/bayios_YYYYMMDD_HHMMSS.dump
   ```
   Bu, dump'ı `bayios_restore_check` adlı ayrı DB'ye yükler ve `products` sayımını basar.
2. Temel product/reservation/stock sorgularını doğrula.
3. Uygulamayı geçici restore DB'ye bağlayıp health/read/write smoke çalıştır (istenirse ayrı stack ile).
4. Sonucu ve dump tarihini operasyon kaydına yaz.

Production restore gerektiğinde önce yeni DB instance/volume'a restore edilir; eski volume silinmeden doğrulama yapılır. Başarısız migration sonrası eski veritabanı üzerine körlemesine yazılmaz.

## 7. Güncelleme

1. Yeni image ve migration öncesi backup al.
2. `podman compose build` ile image'ı yeniden build et.
3. `podman compose run --rm app alembic upgrade head` ile migration'ları ileri yönlü çalıştır.
4. `/health` ve kritik smoke akışlarını doğrula.
5. Hata varsa eski DB volume'unu silmeden restore prosedürünü (bölüm 6) uygula.

## 7.1 Mevcut production kurulumunu Git ile güncelleme

Bu bölüm, Windows 11 + Podman Desktop ile kurulmuş mevcut BayiOS kurulumunu
son sürüme çıkarmak içindir. **Mevcut kurulumda `git clone` yapılmaz;** repo
zaten varsa `git pull` kullanılır. Yeni clone yalnızca repo klasörü hiç yoksa
veya bozulduysa tercih edilir.

> Önemli: Production'daki `.env` dosyası Git'e dahil değildir. Güncelleme
> sırasında silinmez; fresh clone yaparsan eski `.env` dosyasını ayrıca kopyala.
> `podman compose down -v` **çalıştırma**; `-v` PostgreSQL volume'unu siler.

### 1. Bakım penceresi ve mevcut durum kontrolü

PowerShell veya Podman Desktop terminalinde repo klasörüne gir:

```powershell
cd C:\BayiOS
git status --short
git branch --show-current
podman compose ps
```

- Çalışma ağacında takip edilmeyen kritik dosya varsa önce yedekle.
- Production'ın hangi branch'i takip ettiğini not et. Bu repoda son geliştirmeler
  `feat` branch'indedir; production `main` kullanıyorsa aşağıdaki iki yoldan
  biri seçilmelidir:
  - Geçici olarak `feat` branch'ini deploy et: `git checkout feat`
  - Kalıcı düzen: `feat` branch'ini `main`e merge edip production'ı `main`e al.

### 2. Güncelleme öncesi zorunlu yedek

Migration'dan önce mutlaka yedek al:

```powershell
wsl bash -lc "cd /mnt/c/BayiOS && bash scripts/backup.sh"
```

WSL yoksa Git Bash ile:

```powershell
& "C:\Program Files\Git\bin\bash.exe" -lc "cd /c/BayiOS && bash scripts/backup.sh"
```

Yedek dosyasının oluştuğunu ve boyutunun sıfırdan büyük olduğunu doğrula:

```powershell
wsl bash -lc "ls -lh /var/lib/bayios-backups/daily | tail -5"
```

`BACKUP_EXTERNAL_DIR` tanımlıysa harici disk kopyasının da oluştuğunu kontrol et.

### 3. Kodu güncelle

Mevcut repo klasöründe:

```powershell
git fetch origin
git pull --ff-only
```

`git status --short` çıktısı temiz değilse önce yerel değişikliği `git stash` ile
kenara al veya bilinçli olarak commit et. Production'da körlemesine
`git reset --hard` kullanma.

Production `feat` branch'ini kullanacaksa:

```powershell
git checkout feat
git pull --ff-only origin feat
```

Son commit'i doğrula:

```powershell
git log --oneline -5
```

### 4. Yeni image'ı build et

Kod, template, static JS/CSS ve migration dosyaları image içine girer; bu yüzden
sadece container restart etmek yetmez:

```powershell
podman compose build app
```

Podman Desktop kullanıyorsan aynı komutu Podman Desktop terminalinde çalıştırmak
en güvenilir yoldur.

### 5. Şemayı ileri yönlü migrate et

Bu sürümde Alembic head **0012**'dir ve `data_import_batches` tablosu eklenir.
Migration additive'dir; mevcut ürün, kampanya, teklif ve rezervasyon verileri
silinmez.

```powershell
podman compose run --rm app alembic upgrade head
```

Migration'ın gerçekten uygulandığını kontrol et:

```powershell
podman compose run --rm app alembic current
```

Beklenen çıktı: `0012 (head)`

### 6. Uygulamayı yeni image ile yeniden başlat

```powershell
podman compose up -d --force-recreate app
```

PostgreSQL'e dokunma; volume korunur. Eski app container'ı yeni image ile
değiştirilir.

### 7. Sağlık ve log kontrolü

```powershell
podman compose ps
podman compose logs --tail=100 app
```

Health endpoint'i:

```powershell
curl.exe http://localhost:8000/health
```

Beklenen: `status=ok`, `database=ok`, `migrations.status=ok` ve current
migration `0012`. Migration `0012` görünmüyorsa 5. adımı tekrar çalıştır.

Yeni tablonun varlığını doğrula:

```powershell
podman compose exec postgres psql -U bayios -d bayios -c "select count(*) from data_import_batches;"
```

### 8. Bu sürümün production smoke testi

Güncelleme sonrası sırayla kontrol et:

1. `/products` → Excel Dışa Aktar; yeni kolonlar (Alış Fiyatı, Kart/Nakit Taban, Aktif Kampanya) geliyor mu?
2. `/imports/products` → Şablon İndir; önizleme tablosunda yatay kaydırma çubuğu görünüyor mu?
3. `/campaigns` → bir kampanya detayı → Excel Dışa Aktar; `Kampanya Ürünleri` sayfası ürün ilişkileriyle geliyor mu?
4. Aynı kampanya detayında Excel İçe Aktar; ürün ilişkisi satırları yüklenebiliyor mu?
5. `/offers` → bir teklif detayı → **Rezervasyon Aç** ve **Teslim Et (Hızlı Sat)** butonları görünüyor mu?
6. `/commissions` → Komisyon Oranları / Taksit Limitleri dışa aktarma ve içe aktarma çalışıyor mu?
7. `/reservations` → Excel Dışa Aktar; rezervasyon ve satır sayfaları geliyor mu?
8. Tarayıcıda eski JS/CSS önbelleği kalırsa `Ctrl+F5` ile sert yenileme yap.

### 9. Sorun çıkarsa geri dönüş

Kod geri dönüşü:

```powershell
git log --oneline -10
git checkout <önceki-commit>
podman compose build app
podman compose up -d --force-recreate app
```

- `0012` yalnızca yeni tablo eklediği için eski kod bu şemayla çalışmaya devam eder; migration'ı geri almak genelde gerekmez.
- Migration başarısız olduysa canlı DB üzerine doğrudan restore yapma. Önce [Restore tatbikatı](#6-restore-tatbikatı) bölümündeki scratch DB prosedürünü uygula, doğrula, sonra gerekirse kontrollü restore kararı ver.
- `podman compose down -v` kullanma; PostgreSQL volume'u silinir.

## 7.2 Repo klasörü yoksa / bozulduysa: fresh clone ile güncelleme

Mevcut repo klasörü sağlamsa bu yolu kullanma; normal güncelleme `git pull`'dur.
Fresh clone gerekiyorsa:

```powershell
cd C:\
git clone https://github.com/Cyber-Syntax/BayiOS.git BayiOS-new
cd C:\BayiOS-new
git checkout feat
copy C:\BayiOS\.env .env
```

Ardından eski stack'i durdur, yeni klasörde build/migrate/up yap:

```powershell
cd C:\BayiOS
podman compose stop
cd C:\BayiOS-new
podman compose build app
podman compose up -d postgres
podman compose run --rm app alembic upgrade head
podman compose up -d
```

> Compose proje adı `bayios` olduğu için iki klasör aynı anda çalıştırılmamalıdır.
> Fresh clone'da aynı volume kullanılacaksa eski stack'i tamamen durdur; volume'u
> silme. `.env` dosyasını asla Git'e ekleme.

## 7.3 Bu sürümde değişenler

- Ürün, kampanya, teklif, komisyon ve rezervasyon Excel içe/dışa aktarma.
- Ürün Excel'inde alış fiyatı, nakit/kart taban fiyatı ve aktif kampanya kolonları.
- Kampanya detayında ürün ilişkileri odaklı Excel dışa/içe aktarma.
- Teklif detayında hızlı rezervasyon ve hızlı satış/teslim.
- Yatay kaydırmalı tablolar için yapışkan scrollbar.
- Alembic `0012_data_import_batches` migration'ı.
- Yeni environment değişkeni veya yeni Python bağımlılığı yok.

## 8. Sorun giderme

- `/health` 503 → `database`/`migrations` alanlarına bak; migration `upgrade head` çalıştığından ve postgres sağlıklı olduğundan emin ol.
- App başlamıyor → `podman compose logs app`; `DATABASE_URL`'ın `postgresql+psycopg://` şemasında olduğunu doğrula.
- Sayfalar assets'siz görünüyor → `static/vendor/` dosyalarının image içinde olduğunu doğrula (bölüm 3 build'ten sonra `podman compose exec app ls /app/src/bayios/web/static/vendor`).

## 9. Saklama notu

MVP'de müşteri verisi için otomatik retention/anonymization yoktur. İşletme KVKK saklama politikasını belirlediğinde bu runbook ve ayrı bir migration/use-case güncellenmelidir.
