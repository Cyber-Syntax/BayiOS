# BayiOS Operations Runbook

Bu runbook, BayiOS'un kontrollü bayi LAN'ında Docker Compose veya Podman Compose ile çalıştırılması için hedef operasyon sözleşmesidir.

## Compose sınırı

- `app` ve `postgres` ayrı servislerdir.
- PostgreSQL yalnızca Compose internal network'ünde dinler; host/LAN portu publish edilmez.
- Yalnızca app HTTP portu bayi LAN IP'sine publish edilir.
- DB verisi named volume'da, backup çıktısı host bind mount ile ayrı diskte tutulur.
- Docker ve Podman runtime'ları aynı `compose.yaml` sözleşmesini kullanır; uygulama kodu runtime'a özel API çağırmaz.
- Production secret'ları image veya repository içine yazılmaz; environment/secret mekanizmasıyla verilir.

## Başlatma ve health kontrolü

İlk kurulumdan sonra:

1. Host firewall'da yalnızca bayi LAN subnet'inden app portuna izin ver.
2. Guest Wi-Fi izolasyonunu ve modem port forwarding olmadığını doğrula.
3. `compose up` ile PostgreSQL ve app servislerini başlat.
4. Migration command'ını çalıştır.
5. `/health` endpoint'inin DB ve migration durumunu doğrula.
6. Ürün arama ve bir test write/read akışını gerçek tarayıcıdan kontrol et.

PostgreSQL portu doğrudan istemcilere açılmaz. Auth/role olmadan public URL, internet bind veya port forwarding yapılmaz.

## Backup

Backup uygulama request'inin içinde çalışmaz. Ayrı backup command/container:

- `pg_dump` ile günlük veritabanı yedeği alır;
- haftalık tam ve aylık uzun saklama kopyalarını ayrı döngülerde tutar;
- host'tan bağımsız en az bir harici diske kopyalar;
- başarısızlığı exit code ve log ile görünür kılar;
- backup dizininde yeterli alan ve erişim kontrolünü doğrular.

Backup job'ı production DB volume'unu silmez veya migration çalıştırmaz. Şifreler ve yedek erişimi host secret/permission ile korunur.

## Restore tatbikatı

En az aylık:

1. Production volume'una dokunmadan temiz bir PostgreSQL instance başlat.
2. Seçilen dump'ı yeni instance'a restore et.
3. Migration/checksum ve temel product/reservation/stock sorgularını doğrula.
4. Uygulamayı geçici restore DB'ye bağlayıp health, read ve write smoke çalıştır.
5. Sonucu ve dump tarihini operasyon kaydına yaz.

Production restore gerektiğinde önce yeni DB instance/volume'a restore edilir; eski volume silinmeden doğrulama yapılır. Başarısız migration sonrası eski veritabanı üzerine körlemesine yazılmaz.

## Güncelleme

1. Yeni image ve migration öncesi backup al.
2. Compose image'ını çek/build et.
3. Migration'ları ileri yönlü çalıştır.
4. Health ve kritik smoke akışlarını doğrula.
5. Hata varsa eski DB volume'unu silmeden restore prosedürünü uygula.

MVP'de müşteri verisi için otomatik retention/anonymization yoktur. İşletme KVKK saklama politikasını belirlediğinde bu runbook ve ayrı bir migration/use-case güncellenmelidir.

