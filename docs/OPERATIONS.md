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

## 8. Sorun giderme

- `/health` 503 → `database`/`migrations` alanlarına bak; migration `upgrade head` çalıştığından ve postgres sağlıklı olduğundan emin ol.
- App başlamıyor → `podman compose logs app`; `DATABASE_URL`'ın `postgresql+psycopg://` şemasında olduğunu doğrula.
- Sayfalar assets'siz görünüyor → `static/vendor/` dosyalarının image içinde olduğunu doğrula (bölüm 3 build'ten sonra `podman compose exec app ls /app/src/bayios/web/static/vendor`).

## 9. Saklama notu

MVP'de müşteri verisi için otomatik retention/anonymization yoktur. İşletme KVKK saklama politikasını belirlediğinde bu runbook ve ayrı bir migration/use-case güncellenmelidir.
