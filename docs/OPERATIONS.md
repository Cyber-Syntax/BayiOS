# BayiOS Operations Runbook

BayiOS'u kontrollü bayi LAN'ında Podman Compose ile çalıştırmak için operasyon rehberi. Hedef ortam: **Windows 11** host, Podman + PostgreSQL 17 (Compose üzerinden).

Bu runbook bir sözleşmedir: aşağıdaki sınırlar (LAN-only, DB portunun publish edilmemesi, backup) korunmadan uygulama üretimde çalıştırılmaz.

---

## 1. Ön koşullar

- Windows 11 host, Podman (Podman Desktop veya Podman Machine) kurulu ve `podman-compose` çalışıyor.
- Host üzerinde `git` ve (backup zamanlaması için) Görev Zamanlayıcı erişimi.
- Bayi LAN'ına sabit/kalıcı IP veya mDNS ile erişilebilen bir host adı.
- Repository'nin bir kopyası (`BayiOS`) host'ta.

## 1.1 Windows'ta `podman-compose` kurulumu (zorunlu)

Windows'ta `podman compose` bazen Podman'ın kendi compose provider'ı yerine Docker Desktop'ın `docker-compose.exe` dosyasını çağırır. Bu durumda build şu hatayla durur:

```text
Executing external compose provider "C:\Users\<kullanıcı>\AppData\Local\Microsoft\WindowsApps\docker-compose.exe"
Can't add file ...\.dockerignore to tar: io: read/write on closed pipe
failed to connect to the docker API at npipe:////./pipe/podman-machine-default
```

Bu, Docker Desktop compose provider'ının devrede olduğunu gösterir. **Çözüm:** uv (Astral) ile `podman-compose` aracını kurmak ve tüm compose komutlarında `podman compose` yerine `podman-compose` kullanmak.

1. uv kurulu değilse kur:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   Terminali kapatıp yeniden aç; `uv --version` çalıştığını doğrula.

2. podman-compose'u Python 3.12 ile kur:
   ```powershell
   uv tool install --python 3.12 podman-compose
   uv tool update-shell
   ```
   Yeni bir terminal aç ve doğrula:
   ```powershell
   podman-compose --version
   ```
   Komut bulunamazsa geçici olarak PATH'e ekle:
   ```powershell
   $env:Path += ";$env:USERPROFILE\.local\bin"
   ```
   Kalıcı çözüm için `%USERPROFILE%\.local\bin` dizinini kullanıcı PATH'ine ekle.

3. Podman Machine çalışıyor olmalı:
   ```powershell
   podman machine start
   podman info
   ```

4. Compose dosyasını doğrula:
   ```powershell
   podman-compose -f compose.yaml config
   ```

> Bu runbook'taki tüm komutlar `podman-compose` ile yazılmıştır. Windows'ta `podman compose` kullanma; Linux'ta native Podman compose kullanılabilir.

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
   podman-compose build
   podman-compose up -d postgres
   podman-compose run --rm app alembic upgrade head
   podman-compose up -d
   ```
3. Sağlığı doğrula:
   ```powershell
   podman-compose ps
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

Backup, uygulama request'inin içinde çalışmaz; ayrı komuttur. Windows'ta önerilen yol
`scripts/backup-bayios.ps1` betiğidir (WSL/Git Bash gerekmez):

```powershell
cd C:\BayiOS
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup-bayios.ps1
```

Varsayılan çıktı: `C:\BayiOS\backups\daily\bayios_YYYYMMDD_HHMMSS.dump`.

- `pg_dump -Fc` dump'ı container içinde `/tmp` altında üretir, `podman cp` ile host'a kopyalar, geçici dosyayı siler.
- Dump'ın geçerliliğini `pg_restore -l` ile kontrol eder; production DB'ye restore etmez.
- Günlük 14, haftalık 8, aylık 12 yedek saklar. Haftalık/aylık kopya, o hafta/ay için ilk yedekte otomatik oluşur; laptop kapalı olduğu günler sorun olmaz.
- `-ExternalBackupDir D:\BayiOS-Backups` verilirse harici/ikinci disk kopyası alır.
- Retention yalnızca eski **dump dosyalarını** siler; container, volume, veritabanı silmez.
- Başarısızlık exit code + `logs\bayios-backup-*.log` ile görünürdür; hedefte ~1 GiB boş alan kontrol eder.

Görev Zamanlayıcı (günlük, mesai bitişine yakın bir saat):
- Eylem: `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\BayiOS\scripts\backup-bayios.ps1"`
- Çalışma dizini: `C:\BayiOS`
- Tetikleyici: günlük 19:30 gibi. Kurulum için `scripts\install-bayios-tasks.ps1` kullanılabilir.

> `scripts/backup.sh` (bash) yalnızca WSL/Git Bash varsa kullanılmalıdır. Windows'ta dosya CRLF ile gelirse `set: pipefail` hatası alınır; `sed -i 's/\r$//' scripts/backup.sh` veya PowerShell betiği tercih edilir.

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

Windows'ta önerilen ve test edilmiş yol `scripts/update-bayios.ps1` betiğidir:

```powershell
cd C:\BayiOS
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\update-bayios.ps1
```

Betik sırayla şunları yapar:

1. Git çalışma ağacının temiz olduğunu kontrol eder; değilse hiçbir şey yapmadan durur.
2. `git fetch` + `git pull --ff-only` ile güncel kodu alır (sadece `-SkipPull` verilirse atlar).
3. Mevcut image'ı `localhost/bayios:previous` olarak etiketler.
4. `localhost/bayios:latest` image'ını build eder; build'e `GIT_SHA` ve `BUILD_TIME` gömülür.
5. Migration öncesi zorunlu PostgreSQL yedeğini alır (sadece `-SkipBackup` verilirse atlar).
6. `alembic upgrade head` ile ileri yönlü migration'ları uygular.
7. Sadece `app` container'ını `up -d --force-recreate --no-deps app` ile yeniler; PostgreSQL'e dokunmaz.
8. Çalışan container'ın image ID'sini yeni build ile karşılaştırır; `/health` içindeki `build.sha` farklıysa uyarır (image ID doğrulaması esastır).
9. Sağlık kontrolü başarısız olursa `localhost/bayios:previous` image'ına geri döner.

### 7.0 Neden `build` tek başına yetmez?

`podman-compose up`, mevcut container'ı yalnızca compose servis tanımının config hash'i değişince yeniden oluşturur. Image içeriği değişse bile bu hash değişmediği için eski container çalışmaya devam eder ve eski kod görünür. Bu yüzden build'den sonra mutlaka:

```powershell
podman-compose up -d --force-recreate --no-deps app
```

kullanılmalıdır. `podman-compose down` + `up` da çalışır ama gereksiz kesinti yaratır. `down -v` **asla** kullanılmaz; PostgreSQL volume'ünü siler.

### 7.0.1 Güncelleme sonrası doğrulama

```powershell
curl.exe http://localhost:8000/health
git rev-parse --short HEAD
podman inspect bayios_app_1 --format "{{.Image}}"
podman image inspect localhost/bayios:latest --format "{{.Id}}"
```

- `/health` içinde `status=ok`, `migrations.status=ok` ve `build.sha` güncel commit ile aynı olmalıdır.
- Container image ID'si yeni build image ID'siyle aynı olmalıdır.
- `build.sha` eski commit'i gösteriyorsa genellikle container yeniden oluşturulmamıştır; `--force-recreate` olmadan yapılan güncelleme budur. Yalnızca docs/scripts değiştiyse Podman katman önbelleği eski metadata'yı koruyabilir; bu durumda image ID karşılaştırması esastır.

### 7.0.2 İki farklı compose aracı kullanma

Aynı `bayios` projesi altında `podman-compose` (`bayios_app_1`) ve Docker/Podman Desktop Compose (`bayios-app-1`) farklı container isimleri üretir. İkisi aynı anda ayakta kalabilir; eski container 8000 portunu tutarsa yeni kod görünmez. Kural: **sadece `podman-compose` CLI kullan**. Şüphelenirsen `scripts/doctor-bayios.ps1` raporunda "foreign/duplicate naming" uyarısına bak.

## 7.1 Manuel güncelleme (script kullanılamıyorsa)

> Tercih edilen yol §7'deki `update-bayios.ps1` betiğidir. Bu bölüm yalnızca
> script çalıştırılamıyorsa manuel adımları gösterir. Hangi yolu seçersen seç,
> build sonrası `--force-recreate` olmadan container değişmez.

Bu bölüm, Windows 11 + Podman ile kurulmuş mevcut BayiOS kurulumunu
son sürüme çıkarmak içindir. **Mevcut kurulumda `git clone` yapılmaz;** repo
zaten varsa `git pull` kullanılır. Yeni clone yalnızca repo klasörü hiç yoksa
veya bozulduysa tercih edilir.

> Önemli: Production'daki `.env` dosyası Git'e dahil değildir. Güncelleme
> sırasında silinmez; fresh clone yaparsan eski `.env` dosyasını ayrıca kopyala.
> `podman-compose down -v` **çalıştırma**; `-v` PostgreSQL volume'unu siler.

### 1. Bakım penceresi ve mevcut durum kontrolü

PowerShell veya Podman Desktop terminalinde repo klasörüne gir:

```powershell
cd C:\BayiOS
git status --short
git branch --show-current
podman-compose ps
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
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\backup-bayios.ps1
```

Yedek dosyasının oluştuğunu ve boyutunun sıfırdan büyük olduğunu doğrula:

```powershell
Get-ChildItem .\backups\daily | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

`-ExternalBackupDir` verildiyse harici disk kopyasının da oluştuğunu kontrol et.

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
podman-compose build app
```

Podman Desktop kullanıyorsan aynı komutu Podman Desktop terminalinde çalıştırmak
en güvenilir yoldur.

### 5. Şemayı ileri yönlü migrate et

Bu sürümde Alembic head **0020**'dir. `0016` sıfır Oliz fiyatlarını normalize eder, `0017` teklif fiyat motoru v2'yi, `0018` scraper ürün detaylarını, `0019` kampanya scraper metadata'sını, `0020` teklif manuel toplamlarını ekler. Migration'lar additive'dir; mevcut ürün, kampanya, teklif ve rezervasyon verileri silinmez.

```powershell
podman-compose run --rm app alembic upgrade head
```

Migration'ın gerçekten uygulandığını kontrol et:

```powershell
podman-compose run --rm app alembic current
```

Beklenen çıktı: `0020 (head)`

### 6. Uygulamayı yeni image ile yeniden başlat

```powershell
podman-compose up -d --force-recreate app
```

PostgreSQL'e dokunma; volume korunur. Eski app container'ı yeni image ile
değiştirilir.

### 7. Sağlık ve log kontrolü

```powershell
podman-compose ps
podman-compose logs --tail=100 app
```

Health endpoint'i:

```powershell
curl.exe http://localhost:8000/health
```

Beklenen: `status=ok`, `database=ok`, `migrations.status=ok` ve current
migration `0020`. Migration `0020` görünmüyorsa 5. adımı tekrar çalıştır.

Yeni tablonun varlığını doğrula:

```powershell
podman-compose exec postgres psql -U bayios -d bayios -c "select count(*) from data_import_batches;"
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
podman-compose build app
podman-compose up -d --force-recreate app
```

- `0016`–`0020` additive migration'lardır; eski kod bu şemayla çalışmaya devam eder, migration'ı geri almak genelde gerekmez.
- Migration başarısız olduysa canlı DB üzerine doğrudan restore yapma. Önce [Restore tatbikatı](#6-restore-tatbikatı) bölümündeki scratch DB prosedürünü uygula, doğrula, sonra gerekirse kontrollü restore kararı ver.
- `podman-compose down -v` kullanma; PostgreSQL volume'u silinir.

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

Ardından eski stack'i **volume'ü silmeden** kaldır, yeni klasörde build/migrate/up yap:

```powershell
cd C:\BayiOS
podman-compose down          # -v KULLANMA; PostgreSQL volume'ü silinir
cd C:\BayiOS-new
podman-compose build app
podman-compose up -d postgres
podman-compose run --rm app alembic upgrade head
podman-compose up -d --force-recreate --no-deps app
```

> Compose proje adı `bayios` olduğu için iki klasör aynı anda çalıştırılmamalıdır.
> Fresh clone'da aynı volume kullanılacaksa eski stack'i tamamen durdur; volume'u
> silme. `.env` dosyasını asla Git'e ekleme.

## 7.3 Windows operasyon betikleri

| Betik | Amaç | Veritabanına dokunur mu? |
| --- | --- | --- |
| `scripts/start-bayios.ps1` | Açılışta mevcut image ile stack'i başlatır; yabancı/çift container'ları temizler. | Hayır (sadece container başlatır). |
| `scripts/update-bayios.ps1` | Git pull + build + yedek + migration + force-recreate + sağlık/rollback. | Migration ve yedek; asla volume silmez. |
| `scripts/backup-bayios.ps1` | `pg_dump` ile yedek alır, doğrular, retention uygular. | Sadece okur; DB'yi silmez/restore etmez. |
| `scripts/doctor-bayios.ps1` | **Salt okunur** teşhis raporu üretir. | Hayır; container/volume/DB değiştirmez. |
| `scripts/install-bayios-tasks.ps1` | "BayiOS Autostart" ve günlük "BayiOS Backup" görevlerini kurar. | Hayır. |
| `scripts/create-bayios-shortcuts.ps1` | Masaüstü kısayolları oluşturur. | Hayır. |
| `scripts/stop-bayios.ps1` | Container'ları graceful durdurur; volume/DB silmez. | Hayır (sadece container stop). |
| `scripts/shutdown-bayios.ps1` | Önce BayiOS'u durdurur, sonra Windows'u kapatır/yeniden başlatır. | Hayır. |
| `scripts/install-shutdown-task.ps1` | Kullanıcı logoff script'ini kurar (yönetici gerekir). | Hayır. |

Görev Zamanlayıcı'ya elle eklemek istersen:

- **Autostart:** Tetikleyici "Oturum açılışında", 2 dakika gecikme; Eylem:
  `powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "C:\BayiOS\scripts\start-bayios.ps1"`; çalışma dizini `C:\BayiOS`.
- **Backup:** Günlük 19:30; aynı biçimde `backup-bayios.ps1`.
- Güncelleme görevini **otomatikleştirme**; laptop her gün kapanıyor ve güncelleme manuel yapılmalı. `update-bayios.ps1` masaüstü kısayolundan çalıştırılır.
- Görevleri aynı Windows kullanıcısı altında çalıştır (rootless Podman kullanıcıya bağlıdır).
- `scripts/install-bayios-tasks.ps1` ve `scripts/create-bayios-shortcuts.ps1` bu kurulumu tek komuta indirir.

> Yeni environment değişkeni gerekmez. Build argümanları (`GIT_SHA`, `BUILD_TIME`) sadece image metadata'sı ve `/health` içindir; `.env` dosyasına eklenmez.

## 7.4 PC kapanırken BayiOS'u otomatik durdurma

Windows kapanırken container'ları graceful durdurmak için **kullanıcı logoff script'i** kullanıyoruz. Bu, Task Scheduler'ın "event 1074" görevinden daha güvenilirdir: Windows logoff script'ini kullanıcı profili açıkken çalıştırır ve bitmesini bekler. Podman rootless olduğu için script'in kullanıcı olarak çalışması şarttır; bilgisayar (SYSTEM) shutdown script'i Podman machine'i göremez.

Kurulum (yönetici PowerShell):

```powershell
cd C:\BayiOS
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-shutdown-task.ps1
```

Bu komut:

- `%SystemRoot%\System32\GroupPolicy\User\Scripts\scripts.ini` içindeki `[Logoff]` bölümüne BayiOS stop komutunu ekler.
- Önce zaman damgalı bir `.bak` yedeği alır.
- `gpupdate /force` çalıştırır.

Kaldırmak için:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-shutdown-task.ps1 -Remove
```

Test:

1. Bilgisayarı kapat veya oturumu kapat.
2. `logs\bayios-stop-YYYYMMDD_HHMMSS.log` dosyasının oluştuğunu kontrol et.
3. Log yoksa **Windows Fast Startup** açık olabilir; kapatıp tekrar dene:
   `powercfg /h off` (yönetici) veya Denetim Masası → Güç Seçenekleri → "Hızlı başlatmayı aç" seçeneğini kaldır.

Garantili alternatif: masaüstündeki **BayiOS Kapat ve PC Kapat** kısayolu. Bu kısayol önce `stop-bayios.ps1`, sonra `shutdown.exe /s /t 10` çalıştırır; sıra garanti edilir. Yeniden başlatmak için:

```powershell
.\scripts\shutdown-bayios.ps1 -Restart
```

`stop-bayios.ps1` yalnızca container'ları durdurur; `down -v`, volume silme, `dropdb` veya restore **yoktur**.

## 8. Sorun giderme

- `/health` 503 → `database`/`migrations` alanlarına bak; migration `upgrade head` çalıştığından ve postgres sağlıklı olduğundan emin ol.
- `podman-compose build` Docker Desktop'ın `docker-compose.exe`'sini çağırıp `npipe:////./pipe/podman-machine-default` veya `Can't add file ... .dockerignore` hatası veriyorsa: `podman compose` kullanmayı bırak, bölüm 1.1'deki `uv tool install --python 3.12 podman-compose` kurulumunu yap ve tüm komutları `podman-compose` ile çalıştır. Ayrıca `podman machine start` ve `podman info` ile machine'in çalıştığını doğrula.
- App başlamıyor → `podman-compose logs app`; `DATABASE_URL`'ın `postgresql+psycopg://` şemasında olduğunu doğrula.
- Sayfalar assets'siz görünüyor → `static/vendor/` dosyalarının image içinde olduğunu doğrula (bölüm 3 build'ten sonra `podman-compose exec app ls /app/src/bayios/web/static/vendor`).
- **Build alındı ama eski kod görünüyor** → container yeniden oluşturulmamıştır. `podman-compose up -d --force-recreate --no-deps app` çalıştır; `/health` içindeki `build.sha` güncel commit mi kontrol et. `podman-compose down` + `up` da düzeltir ama gereksiz kesinti yaratır.
- **İki uygulama / iki container** → aynı projede `podman-compose` ve Docker/Podman Desktop Compose karışmış olabilir (`bayios_app_1` + `bayios-app-1`). `scripts/doctor-bayios.ps1` raporunu çalıştır; "foreign/duplicate naming" uyarısı varsa `update-bayios.ps1` veya `start-bayios.ps1` yabancı container'ı durdurup kaldırır. Sadece `podman-compose` kullan.
- **Rapor/teşhis isteği** → `scripts/doctor-bayios.ps1` salt okunurdur; container durdurmaz, volume/DB silmez. Çıktı `reports/bayios-doctor-*.txt` altındadır.
- **Görev zamanlayıcı çalışmıyor** → görevi rootless Podman'i kullanan Windows kullanıcısıyla ve "oturum açılışında" çalıştır; SYSTEM hesabı Podman machine'e erişemez.

## 9. Saklama notu

MVP'de müşteri verisi için otomatik retention/anonymization yoktur. İşletme KVKK saklama politikasını belirlediğinde bu runbook ve ayrı bir migration/use-case güncellenmelidir.
