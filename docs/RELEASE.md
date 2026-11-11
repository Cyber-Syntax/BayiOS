# BayiOS — Release ve Doğrulama Rehberi (v0.1 MVP)

Bu belge, MVP'nin üretim Windows 11 makinesine kurulması, gerçek veriyle go-live, çalışanlarla pilot ve pilot sonrası değerlendirme adımlarını sıralar. Operasyonel komutlar için [OPERATIONS.md](./OPERATIONS.md)'ye, iş kuralları için [PRD](./prd.md)'ye bakın.

Kapsam: Milestone 0–5 (katalog+import, rezervasyon+A4, sayım, kampanya, teklif+komisyon). **Milestone 6 (Hızlı Teslim) bu release'de YOK** (navigasyonda "yakında"). Auth yok → kesinlikle LAN-only.

---

## A. Go-live öncesi doğrulama (bu depoda tamamlandı)

- [x] Tam test suite (215 test) gerçek PostgreSQL'de yeşil.
- [x] Gerçek `arcelik-06-09-2026.csv` import → 1669 ürün + 26 çift isimli satır doğru güncellendi.
- [x] Uçtan uca smoke (arama→import→rezervasyon→teslim(idempotent)→teklif→A4→kampanya→komisyon) geçti.
- [x] Restore tatbikatı (pg_dump -Fc → scratch DB → sayım eşleşmesi) geçti.
- [x] CDN/internet bağımlılığı yok; vendor asset hash'leri doğrulandı.

## B. Go-live (Windows 11 + Podman)

1. **Podman kurulum/doğrulama:** `podman --version` ve `podman info` çalışıyor olmalı (Podman Desktop veya Podman Machine).
2. **Secret:** `.env.production.example` → `.env` kopyala; `POSTGRES_PASSWORD`'ü uzun rastgele bir değerle değiştir.
3. **Build + deploy:**
   ```
   podman compose build
   podman compose up -d postgres
   podman compose run --rm app alembic upgrade head
   podman compose up -d
   ```
4. **Sağlık:** `podman compose ps` ve `/health` → `status=ok, database=ok, migrations=ok` (current=0011).
5. **Güvenlik (zorunlu):**
   - Host firewall yalnızca bayi LAN subnet'inden `BAYIOS_PORT`'a izin.
   - Modemde port forwarding YOK; public URL bind YOK.
   - Guest Wi-Fi ağından izole; guest cihazlar erişemez.
   - `podman compose config` çıktısında `postgres`'te `ports` olmadığını doğrula (DB LAN'a kapalı).
6. **İlk backup + restore tatbikatı (gerçek veri YÜKLENMEDEN önce):**
   - `bash scripts/backup.sh` → dump oluştuğunu doğrula.
   - `bash scripts/restore.sh <dump>` → scratch DB'ye yükle ve sayımı doğrula.
   - Görev Zamanlayıcı ile günlük backup tetiklemesini kur (OPERATIONS.md §5).
7. **Gerçek veri import:**
   - `/imports/products` → `arcelik-06-09-2026.csv` yükle; önizlemede sorunlu satırlar en üstte, sayaçlar doğru.
   - Kanonik `.xlsx` dosyasını teyit et (`bayios-urunler*.xlsx` / `Bayi_Stok_Fiyat_Ornek.xlsx`); gerekirse onu da import et.
   - Commit sonrası `/products` üzerinden örnek ürünlerin fiyat/stok doğruluğunu kontrol et.
8. **Başlangıç ayarları (patron kararlarıyla):**
   - Komisyonlar: `2026-11` dönemi seed edildi; POS/Ödero/Chippin oranlarını ve taksit limitlerini gir, dönemi aktifleştir.
   - Kampanyalar: aktif kampanyaları tanımla.
   - Bayi indirimi varsayılanı: `/campaigns` → "Bayi İndirimi Varsayılanı" (%10 öneri; patron yönlendirmesiyle değiştir).
   - Ürünlerde bayi nakit/kart taban fiyatları ve maliyetler gerekliyse gir.
9. **LAN smoke (gerçek cihaz):**
   - Desktop + mobil tarayıcıdan LAN IP'si ile eriş; `/health` ve temel write/read (ürün arama, bir rezervasyon, bir teklif) doğrula.
   - A4 çıktıların yazıcıdan okunabilir olduğunu doğrula.

## C. Pilot (~1 hafta)

1. Çalışanları brief et; kritik akışları (ürün arama, rezervasyon, teklif, sayım) gerçek işte kullandır.
2. Günlük backup'ın çalıştığını ve disk alanını izle; `/health`'i izle.
3. Feedback topla → GitHub Issues olarak aç (öncelik/etiket ile). Kritik/veri bütünlüğü sorunları hemen; kozmetik/UX sorunları backlog.
4. Veri bütünlüğü/kritik hata durumunda restore prosedürünü hazır tut (OPERATIONS.md §6).

## D. Pilot sonrası kapatma

1. **Go/no-go:** Çalışan feedback'i + hata/veri bütünlüğü kayıtlarına göre karar ver.
2. **Sonraki release kapsamını belirle** (önerilen sıra):
   - **Milestone 6 — Hızlı Teslim / Code 128** (şu an backlog).
   - Locust 5.000 ürün / 4 client p95 performans kapısı.
   - İnternete açılmadan ÖNCE kullanıcı hesabı + rol + kayıt sahipliği (PRD §2.2).
3. OPERATIONS.md'yi ve bu belgeyi pilot sonucuna göre güncelle; operasyon kaydına go-live/pilot tarihlerini işle.
