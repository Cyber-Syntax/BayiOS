# BayiOS — Basit Erişim Koruması (MVP Auth) Planı

**Durum:** Taslak — onay bekliyor
**Tarih:** 27 Kasım 2026
**Kapsam sürümü:** v1.1 (mevcut LAN kurulumuna ek)
**İlgili belgeler:** [prd.md](./prd.md) §2.2, §12.1, §17 · [plan.md](./plan.md) §2.5 · [ui.md](./ui.md) §10
**Revizyon:** 2 — 27 Kasım 2026: günlük kapanan sunucu, 10/5 kilit + muaf IP, harf+rakam şifre politikası, manuel .env birincil yol.

---

## 1. Özet

BayiOS bugün bayi LAN'ında kimlik doğrulaması olmadan çalışıyor. Wi-Fi şifresini bilen
herkes (komşu, bayideki tanıdık, eski çalışan) tüm ürün, maliyet, komisyon, teklif ve
müşteri ekranlarını açabilir; yazma işlemi yapabilir. Bu iş, sistemin kapısına **tek
paylaşılan şifre** koyar: bütün çalışanlar aynı şifreyi kullanır, giriş yapmadan hiçbir
ekran ve hiçbir veri açılmaz.

Amaç tam bir kimlik/yetki sistemi değil; **"az da olsa güvenlik"** katmanıdır. Kullanıcı
hesabı, rol, işlem sahipliği ve HTTPS sonraki faza bırakılır (bkz. §10).

### 1.1 Bu iş neyi korur, neyi korumaz

| Korur | Korumaz |
| --- | --- |
| Wi-Fi şifresini bilen ama uygulama şifresini bilmeyen kişiler | Şifreyi bilen herkes (tüm çalışanlar ve onlara söyledikleri) |
| Bayideki tanıdığa/komşuya verilen Wi-Fi ile kazara erişim | Aynı ağda trafik dinleyen biri (şifre HTTP üzerinden düz metin gider) |
| Paylaşılan telefonda "çıkış yap" ile oturumu kapatma | Sunucuya veya .env dosyasına erişen kişi |
| Oturum süresi dolunca sessizce erişilemeye devam etmesi | Şifreyi paylaşan çalışanın kim olduğunun tespiti (ortak şifre = ortak kimlik) |

**Kritik sonuç:** Paylaşılan şifre kaybolursa veya bir çalışan ayrılırsa yapılacak tek şey
şifreyi değiştirmektir; değişiklik bütün cihazların oturumunu kapatır (§8).

## 2. Kapsam

### 2.1 Dahil

1. Giriş ekranı (/login) ve çıkış (POST /logout).
2. Bütün sayfaların, Excel/CSV dışa aktarmalarının, A4/A5 çıktılarının ve HTMX
   parçalarının varsayılan olarak korunması (default-deny).
3. İmzalı, süreli oturum çerezi; tarayıcı kapanınca veya süre dolunca giriş isteği.
4. "Bu cihazda açık kalsın" seçeneği (varsayılan işaretsiz: 12 saat; işaretlenirse 30 gün).
5. IP başına hatalı deneme kilidi (brute-force yavaşlatma).
6. Türkçe hata/oturum mesajları, çıkış butonu, oturum süresi dolduğunda girişe yönlendirme.
7. Sunucu ayarları (.env), dağıtım ve şifre değiştirme prosedürü.
8. Testler: giriş/çıkış, yönlendirme, süre bitişi, kilit, açık yönlendirme (open redirect)
   koruması, CSRF/Origin kontrolü ve mevcut test paketinin güncellenmesi.
9. Doküman güncellemeleri (PRD, plan, UI, AGENTS.md, OPERATIONS.md, README).

### 2.2 Hariç (detaylı faz — §10)

- Kullanıcı başına hesap, kullanıcı adı, rol, izin, işlem sahipliği.
- Şifre değiştirme ekranı (bu fazda .env + yeniden başlatma).
- Oturumları listeden görme/iptal etme, cihaz onaylama, 2FA.
- HTTPS/TLS, HSTS, güvenlik duvarı/misafir ağ ayrımı.
- Parola sıfırlama, e-posta/SMS doğrulama.
- Denetim (audit) ekranı ve giriş geçmişi UI'ı.

## 3. Önerilen kararlar

> Kararlar 27 Kasım 2026 görüşmesinde netleşti. Kullanıcı seçimleri S1–S6 olarak
> işaretlidir; onaylanan maddeler uygulama sırasında değiştirilmez.

| No | Karar | Durum |
| --- | --- | --- |
| D1 | Tek paylaşılan şifre; kullanıcı adı yok. Herkes tüm sekmelere eşit erişir. | Önerilen |
| D2 | Şifre sunucudaki .env içinde düz metin (BAYIOS_ADMIN_PASSWORD); değiştirmek için .env + yeniden başlatma. | Onaylandı (S6) |
| D3 | İmzalı çerez (HMAC-SHA256), sunucu tarafında oturum tablosu yok. Oturum iptali = şifre veya oturum anahtarını değiştirmek. | Önerilen |
| D4 | "Bu cihazda açık kalsın" varsayılan işaretsiz: 12 saat; işaretli: 30 gün. Sunucu her gün kapansa da oturum çerezi silinmez; süre dolunca giriş gerekir. | Onaylandı (S1, revize) |
| D5 | Aynı IP'den 10 hatalı denemeden sonra 5 dakika kilit. Sunucunun kendi IP'si ve loopback muaf. | Onaylandı (S2, revize) |
| D6 | Varsayılan kapalı: yalnız /login, /health, /static/* şifresiz; geri kalan her şey korumalı. | Önerilen |
| D7 | CSRF: SameSite=Lax çerez + yazma isteklerinde Origin kontrolü (varsa). | Önerilen |
| D8 | HTTPS bu fazda yok; LAN içi HTTP kabul edilir, detaylı fazda ele alınır. | Onaylandı (S5) |
| D9 | Çerez: HttpOnly, SameSite=Lax, Path=/, Secure yapılandırılabilir (HTTP'de kapalı). HTML yanıtlarında Cache-Control: no-store. | Önerilen |
| D10 | Şifre en az 8 karakter; en az bir harf ve bir rakam. Özel karakter zorunlu değil; yaygın şifreler ve sıralı/tekrar eden diziler reddedilir. | Onaylandı (S4, revize) |
| D11 | Girişte isteğe bağlı "cihaz adı" alanı (boş bırakılabilir); kayıtlardaki created_by_device alanını doldurur. | Onaylandı (S3) |
| D12 | Testler gerçek giriş akışıyla çalışır; üretimde auth'u kapatan bir "test bayrağı" yoktur. | Önerilen |

## 4. Teknik tasarım

### 4.1 Sunucu ayarları

ApplicationSettings yalnız veritabanı/log ayarlarını taşımaya devam eder; auth ayarları
ayrı bir AuthSettings sınıfına konur. Böylece Alembic ve bakım komutları şifre
tanımlamadan çalışmaya devam eder, web uygulaması ise eksik ayarla **açılmaz**.

| Ortam değişkeni | Zorunlu | Varsayılan | Açıklama |
| --- | --- | --- | --- |
| BAYIOS_ADMIN_PASSWORD | Evet | — | Ortak giriş şifresi (en az 8 karakter; en az bir harf + bir rakam). |
| BAYIOS_SESSION_SECRET | Evet | — | Çerez imza anahtarı, en az 32 karakter rastgele değer. Şifreden türetilmez. |
| BAYIOS_SESSION_TTL_HOURS | Hayır | 12 | "Bu cihazda açık kalsın" işaretsiz oturum ömrü. |
| BAYIOS_REMEMBER_TTL_DAYS | Hayır | 30 | "Bu cihazda açık kalsın" oturum ömrü. |
| BAYIOS_COOKIE_SECURE | Hayır | false | HTTPS'e geçince true. |
| BAYIOS_LOGIN_MAX_ATTEMPTS | Hayır | 10 | Kilit öncesi hatalı deneme. |
| BAYIOS_LOGIN_LOCKOUT_MINUTES | Hayır | 5 | Kilit süresi. |
| BAYIOS_LOGIN_EXEMPT_IPS | Hayır | 127.0.0.1,::1 | Kilit uygulanmayan kaynak IP'ler (virgülle). Sunucunun kendi LAN IP'si eklenebilir. |

- Eksik/geçersiz ayarda uygulama açılmaz ve operatöre hangi değişkenin eksik olduğunu
  söyleyen İngilizce teknik hata verir (log). Kullanıcı arayüzüne İngilizce sızmaz.
- .env.example, .env.production.example ve compose.yaml bu değişkenleri taşır;
  production .env Git'e girmez.
- scripts/set-access-password.ps1 (Windows host) opsiyonel bir kolaylıktır: şifreyi sorar,
  BAYIOS_SESSION_SECRET üretir, .env'e yazar. Hatalı çalışırsa **manuel yol** (§8.1)
  kullanılır; manuel yol her zaman geçerlidir ve birincil kabul edilir.
- Şifre politikası startup'ta doğrulanır: en az 8 karakter; en az bir alfabetik karakter
  (Türkçe harfler dahil) ve en az bir 0-9 rakamı. Özel karakter zorunlu değildir. Yalnız
  rakam, yalnız harf, tümü aynı karakter, sıralı dizi (12345678/abcdefgh) ve yaygın
  şifreler (password, 12345678, qwerty123, bayios1 gibi), 4+ ardışık dizi (1234, abcd)
  ve 3+ aynı karakter tekrarı (aaa, 111) reddedilir. Hata, nedeniyle
  birlikte log'da operatöre söylenir; kullanıcı arayüzüne İngilizce sızmaz.
- Manuel .env kurulumu ve sorun giderme: §8.1 ve §8.4. .env.example kopyala-yapıştır
  bloğunu içerir.

### 4.2 Oturum çerezi

Çerez adı: bayios_session (host-only, Path=/).

Token biçimi (küçük ve ayrıştırması kolay):

    v1.<exp_unix>.<pw_fp>.<hmac_signature>

- pw_fp = HMAC-SHA256(session_secret, "pw|" + admin_password) ilk 16 hex karakter.
  Şifre değişince eski çerezler otomatik geçersiz olur.
- hmac_signature = HMAC-SHA256(session_secret, "v1|" + exp + "|" + pw_fp).
- Doğrulama: parça sayısı, v1, exp > now, pw_fp ve imza compare_digest ile sabit zamanlı
  karşılaştırılır. Geçersizse çerez silinir ve girişe yönlendirilir.
- Süre mutlak (sliding değil): varsayılan 12 saat; "açık kalsın" işaretliyse 30 gün.
- **Sunucu her gün kapatılıp açılsa da oturumlar kendiliğinden silinmez.** Çerez
  istemcide, imza anahtarı .env'de kalıcıdır; yeniden başlatma bir çıkış değildir.
  Sabah yeniden giriş genellikle 12 saatlik süre dolduğunda veya "açık kalsın"
  işaretsizken tarayıcı kapanınca olur. Bu MVP'de varsayılan davranış budur.
- Oturum anahtarı değişirse bütün cihazlar çıkar (acil durum kill-switch).
- Sunucu tarafında oturum tablosu yoktur; bu yüzden tek tek oturum iptali yoktur.
  Paylaşılan şifreli MVP için kabul edilen sınırlama.

### 4.3 İstek akışı (middleware)

Auth, tek bir ASGI middleware ile **varsayılan kapalı** uygulanır; yeni eklenen bir router
otomatik olarak korunur. (Sayfa sayısı 140 route; tek tek dependency eklemek hata yapmaya
açıktır.)

| İstek | Davranış |
| --- | --- |
| GET/HEAD /login, POST /login | Şifresiz. Giriş yapmış kullanıcı /'a yönlendirilir. |
| GET /health | Şifresiz (Compose healthcheck ve izleme için). |
| /static/* | Şifresiz (giriş ekranının CSS/fontları). |
| Geçerli oturum çerezi | İstek normal işlenir. |
| Oturumsuz normal GET | 303 → /login?next=<yerel yol>. |
| Oturumsuz HTMX isteği (HX-Request) | 401 + HX-Redirect: /login?next=... (sayfa yenilenmeden girişe döner). |
| Oturumsuz POST (form) | 303 → /login (form verisi kaybolur; süre dolduğunda bu beklenen davranıştır). |
| Oturumsuz dosya indirme (GET .../export.xlsx) | 303 → /login; indirme başlamaz. |
| Origin başlığı farklı host'u gösteren yazma isteği | 403 (Türkçe hata). Origin yoksa SameSite=Lax'e güvenilir. |

next parametresi yalnız tek / ile başlayan yerel yolları kabul eder; çift eğik çizgi,
ters bölü, http(s):// ve kontrol karakterleri reddedilir (open redirect koruması).

Ek yanıt başlıkları (tüm korumalı yanıtlarda): Cache-Control: no-store,
X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy: same-origin.

> Not: Cache-Control: no-store paylaşılan telefonda çıkış sonrası "geri" tuşuyla
> ekranın görünmesini engellemeyi amaçlar; tarayıcı davranışı garanti değildir.

### 4.4 Giriş ve çıkış

**GET /login** — base.html kullanmayan sade, tek kartlı ekran (üst menü yok):

- BayiOS logosu/markası, "Yerel ağ erişimi" alt başlığı.
- Şifre alanı (görünür etiket, autocomplete="current-password", göster/gizle).
- Şifre büyük/küçük harfe duyarlıdır; baş/son boşluklar yok sayılır.
- İsteğe bağlı "Cihaz adı" alanı (örn. "Kasa telefonu"; S3).
- "Bu cihazda açık kalsın" onay kutusu (varsayılan işaretsiz; işaretlenirse 30 gün).
- "Giriş yap" birincil butonu.
- Hata kutusu: "Şifre hatalı." / "Çok fazla hatalı deneme. 5 dakika sonra tekrar deneyin."
- Alt bilgi: "BayiOS · yalnızca yerel ağ" ve "Bu sistem yalnızca yetkili çalışanlar içindir."
- Klavye akışı: alan → onay kutusu → buton; Enter formu gönderir; odak halkası görünür.

**POST /login** sırası:

1. Kilit kontrolü (IP) → kilitliyse 429 + Türkçe mesaj.
2. Şifre karşılaştırması (baş/son boşluklar yok sayılır).
3. Hatalıysa sayacı artır, 401 + form yeniden render (şifre alanı boş, odak şifrede).
4. Doğruysa sayacı sıfırla, çerezi yaz, isteğe bağlı cihaz adı çerezini yaz, 303 ile
   next veya /'a git.
5. Başarılı/başarısız her deneme loglanır: IP, kullanıcı aracısı, sonuç. **Şifre loglanmaz.**

**POST /logout** — çerezi siler, 303 /login. Sol menü altına ve mobil "Diğer sayfalar"
sayfasına "Çıkış yap" butonu eklenir (form + method="post").

### 4.5 Hatalı deneme kilidi

- Bellekte {ip: {failures, first_failure_at, locked_until}}; tek uvicorn süreci olduğu
  için yeterli (Compose'da worker sayısı 1).
- Varsayılan: 15 dakikalık pencerede 10 hatalı deneme; 10. denemede 5 dakika kilit.
  Başarılı giriş sayacı sıfırlar. Kilit süresi dolunca sayaç da sıfırlanır; 5 dakika
  sonra tekrar denenebilir (aksi hâlde tek hata yeniden kilitler).
- Muaf IP'ler (varsayılan 127.0.0.1, ::1): kilit uygulanmaz, şifre yine sorulur. Sunucunun
  kendi LAN IP'si BAYIOS_LOGIN_EXEMPT_IPS ile eklenebilir. Gerekçe: sunucuya erişen biri
  zaten .env'e ulaşır; bu katman Wi-Fi'ye bağlanan dış kişilere karşıdır.
- Muafiyet yalnız kaynak IP'ye bakar; LAN'da TCP kaynak IP'si taklit edilemez. Sunucunun
  LAN IP'sini Windows'ta ipconfig ile bulup listeye ekleyebilirsin; localhost ile
  giriyorsan 127.0.0.1 zaten muaf. **Ters proxy eklenirse** varsayılan 127.0.0.1
  muafiyeti kaldırılmalı ve gerçek istemci IP'si güvenilir proxy başlığından okunmalıdır;
  yoksa tüm istekler aynı proxy IP'sinden gelir ve herkes muaf olur.
- Eski kayıtlar ara ara temizlenir (bellek şişmesin).
- Kilit yalnız o IP/cihazı etkiler; tüm mağazayı kilitlemez. Sunucu her gün kapanınca
  sayaç da sıfırlanır; gece boyunca deneme yapılamaz.
- **Doğrulama (dağıtımda bir kez):** Container port yönlendirmesi kaynak IP'yi
  gizleyebilir. Sunucu ve telefondan hatalı giriş yapıp log'daki istemci IP'lerine bakılır.
  Farklı IP'ler görünüyorsa sistem beklendiği gibi çalışır. Hepsi aynı gateway IP'sini
  gösteriyorsa: (a) Podman'da kaynak IP'yi koruyan ağ ayarı araştırılır, (b) geçici olarak
  eşik 30 deneme / 2 dakika yapılır ve muafiyet kaldırılır; aksi hâlde kilit tüm mağazayı
  etkiler ve 'sunucu muaf' özelliği güvenilir olmaz. Bu kontrol yapılmadan üretimde
  per-IP davranışı varsayılmaz.

### 4.6 Kayıt izleme (actor) ile ilişki

- get_actor ve X-Device-Name/X-Worker-Name davranışı **değişmez**; bunlar güvenlik
  değil, izleme bilgisidir.
- Girişte cihaz adı girilirse device_name çerezi (1 yıl) yazılır; mevcut kayıtlarda
  created_by_device dolar. Bu alan hâlâ istemci tarafından değiştirilebilir; gerçek
  kimlik doğrulaması sayılmaz.
- created_by_name alanı boş kalır; kullanıcı adı olmadığı için uydurulmaz.

### 4.7 Erişim matrisi

| Yol | Şifresiz erişim | Not |
| --- | --- | --- |
| /login | Evet | Giriş ekranı. |
| /health | Evet | Compose healthcheck; DB/migration/build bilgisi döner. |
| /static/* | Evet | CSS, JS, font, vendor. |
| /, /products, /campaigns, /offers, /reservations, /stock, /commissions, /settings | Hayır | Tüm liste/detay/form/print ekranları. |
| Tüm POST yazma uçları | Hayır | Ürün, stok, rezervasyon, teklif, kampanya, ayarlar, import. |
| Excel/CSV/JSON dışa aktarımlar | Hayır | Veri sızmasını önlemek için kritik. |
| /logout | Hayır | Oturumlu POST. |

## 5. Dosya değişiklikleri

| Dosya | Değişiklik |
| --- | --- |
| src/bayios/bootstrap.py | AuthSettings sınıfı; doğrulama ve varsayılanlar. |
| src/bayios/web/auth.py | **Yeni.** Token üretme/doğrulama, kilit, middleware, yardımcılar. |
| src/bayios/web/pages/auth.py | **Yeni.** GET/POST /login, POST /logout. |
| src/bayios/web/templates/auth/login.html | **Yeni.** Sade giriş ekranı. |
| src/bayios/main.py | create_app(settings, auth_settings=None), middleware ve auth router. |
| src/bayios/web/templates/base.html | Sol menü/mobil sayfada "Çıkış yap". |
| src/bayios/web/static/css/app.css | Giriş ekranı ve çıkış butonu stilleri (mevcut tokenlar). |
| compose.yaml | Auth değişkenleri (şifre, anahtar, TTL, kilit, muaf IP'ler) app servisine geçirilir. |
| .env.example, .env.production.example | Yeni değişkenler + boş bırakılırsa açılmayan manuel doldurma bloğu; kopyala-yapıştır talimatı. |
| scripts/set-access-password.ps1 | **Yeni, opsiyonel.** .env'e şifre + oturum anahtarı yazar; hata verirse manuel yol (§8.1) kullanılır. |
| scripts/dev.sh | Eksikse uyarı ve örnek değer ipucu (opsiyonel). |
| tests/support.py | **Yeni.** TEST_AUTH, login(client) yardımcıları. |
| tests/web/test_auth.py | **Yeni.** Aşağıdaki davranış testleri. |
| tests/web/*.py (10 yer) | create_app çağrılarına test auth ayarı + giriş. |
| docs/prd.md | §2.2, §3.2, §12.1, §14, §15, §16, §17 güncellemesi. |
| docs/plan.md | §2.5 güncellemesi + "Milestone 8 — Basit erişim koruması". |
| docs/ui.md | §10 kapsam dışı listesi + giriş ekranı sözleşmesi. |
| docs/OPERATIONS.md | Ortam değişkenleri, manuel .env adımları, şifre değiştirme, kilit sorunu, sorun giderme, dağıtım notu. |
| AGENTS.md | "MVP has no authentication" ifadesi ve out-of-scope listesi güncellenir. |
| README.md | Hızlı başlangıç .env adımları. |
| GLOSSARY.md | "Erişim şifresi" terimi. |

Veritabanı migration'ı **yoktur**; şema değişmez.

Not: .env.example ve .env.production.example bu plan revizyonunda güncellendi; diğer
kod ve doküman değişiklikleri uygulama sırasında yapılacak.

## 6. Test planı

### 6.1 Yeni davranış testleri (tests/web/test_auth.py)

- Şifresiz GET /products → 303 ve Location: /login?next=/products; ürün verisi HTML'de yok.
- Şifresiz GET / → giriş ekranı (follow_redirects=True ile "Giriş yap" görünür).
- GET /health ve /static/css/app.css şifresiz 200.
- Hatalı şifre → 401, "Şifre hatalı." ve çerez yok.
- Doğru şifre → 303 /, bayios_session çerezi; HttpOnly, SameSite=Lax, Path=/.
- Girişten sonra /products, /offers, /settings ve bir Excel dışa aktarımı 200.
- Şifresiz HTMX isteği → 401 + HX-Redirect başlığı.
- next=https://evil.example ve next=//evil.example → /'a yönlendirilir.
- POST /logout çerezi siler; sonraki istek girişe döner.
- Süresi geçmiş token (elle üretilmiş) reddedilir ve çerez silinir.
- Şifre değişmiş gibi farklı pw_fp taşıyan token reddedilir.
- 10 hatalı denemeden sonra doğru şifre bile 429; 11. denemede Türkçe kilit mesajı.
- Muaf IP (127.0.0.1) yanlış şifreden sonra kilitlenmez; muaf olmayan IP kilitlenir.
- Aynı oturum anahtarıyla yeniden oluşturulan uygulamada eski çerez geçerli kalır
  (sunucu restart simülasyonu).
- Startup şifre doğrulaması: 'password' (rakam yok) ve '12345678' (harf yok) reddedilir;
  'mavi-kedi-42' kabul edilir. Yaygın şifre listesi ve sıralı/tekrar desenleri test edilir.
- Giriş ekranında "Bu cihazda açık kalsın" varsayılan işaretsizdir.
- Yazma isteğinde farklı Origin → 403.
- Giriş ekranında üst menü/sekme yok; şifre alanı autocomplete="current-password".
- Login yanıtında Cache-Control: no-store; korumalı sayfalarda da no-store.

### 6.2 Mevcut paket

- 10 test dosyasındaki create_app(...) çağrılarına AuthSettings(...) eklenir ve
  client fixture'ları login(client) çağırır.
- tests/web/test_health.py giriş gerektirmez ama create_app için auth ayarı alır.
- Tam paket: uv run pytest -q (419+ test) ve uv run ruff check src tests temiz.
- PostgreSQL integration testleri auth'tan bağımsız; etkilenmez.

### 6.3 Manuel kabul (telefon + masaüstü)

1. Telefon ve masaüstünde ilk giriş; şifre yöneticisi kaydı.
2. HTMX ürün arama ve form kaydı; oturum açıkken sorunsuz.
3. Oturum süresi dolduktan sonra (test için TTL 1 dk) HTMX isteği girişe döner, sayfa
   yenilenmez.
4. A4 rezervasyon ve A5 sayım çıktısı girişliyken açılır.
5. Excel dışa aktarımı girişsizken indirilmez.
6. Çıkış → "geri" tuşu → veri görünmemeli (no-store).
7. Yanlış şifreyle 10 deneme → 5 dk kilit mesajı; 5 dk sonra giriş. Muaf sunucu
   IP'sinde kilit oluşmaz.

## 7. Uygulama sırası ve süre

| Adım | İş | Tahmin |
| --- | --- | --- |
| 1 | AuthSettings, token/kilit çekirdeği, birim testleri | 0,5 gün |
| 2 | Middleware, /login, /logout, giriş ekranı, çıkış butonu | 0,5–1 gün |
| 3 | Test fixture'ları, tam paket, lint | 0,5 gün |
| 4 | .env/compose/script/dokümanlar + manuel .env provası | 0,5 gün |
| 5 | Manuel telefon/masaüstü/print doğrulaması | 0,5 gün |

Toplam: **~2–3 gün**.

## 8. Dağıtım, şifre değiştirme ve geri dönüş

### 8.1 İlk kurulum — manuel .env (PS1 olmadan)

Sunucuya uzaktan erişim her zaman mümkün olmadığı için **birincil yol manueldir**.
scripts/set-access-password.ps1 yalnızca kolaylıktır; hata verirse kullanılmaz, aşağıdaki
adımlar her zaman geçerlidir.

1. Sunucuda proje klasöründeki .env dosyasını Notepad ile aç.
2. İki zorunlu satırı ekle:

       BAYIOS_ADMIN_PASSWORD=<en az 8 karakter, en az bir harf ve bir rakam>
       BAYIOS_SESSION_SECRET=<en az 32 karakter rastgele>

   Şifre önerisi: mavi-kedi-42 gibi akılda kalan bir ifade. Yaygın şifreler
   (password, 12345678, qwerty123) kabul edilmez. .env ayrıştırması için şifrede
   #, $, tırnak ve baş/son boşluk kullanma; harf, rakam, -, _, . yeterli.
3. Oturum anahtarını üret:

       python -c "import secrets; print(secrets.token_urlsafe(48))"

   Python PATH'te değilse proje klasöründe:

       uv run python -c "import secrets; print(secrets.token_urlsafe(48))"

4. Dosyayı kaydet. Şifreyi Git'e, sohbete veya ekran görüntüsüne koyma.
5. Uygulamayı yeniden başlat:

       podman-compose up -d

   .env değişikliği container'a yansımazsa:

       podman-compose up -d --force-recreate app

6. Doğrula:
   - http://127.0.0.1:8000/health → 200
   - http://<sunucu-ip>:8000/login → giriş ekranı
   - telefondan bir kez giriş yap.

.env.example ve .env.production.example bu blokların tamamını yorumlarıyla içerir;
kopyala-yapıştır için oradan al.

> **Kesinti riski:** Yeni sürüm auth ayarları olmadan açılmaz (fail-closed). Bu yüzden
> .env güncellemesi **imaj güncellemesinden önce** yapılmalıdır. OPERATIONS.md'deki
> güncelleme adımlarına bu sıra eklenir.

> **Sunucu her gün kapanıyor:** Mevcut restart: unless-stopped ve otomatik başlatma ile
> uygulama açılır. Oturum çerezi .env'deki anahtarla imzalı olduğu için restart oturumları
> silmez; sabah girişi genellikle 12 saatlik süre dolduğu için gerekir. Anahtar her açılışta
> değiştirilirse herkes her sabah çıkar; anahtar .env'de sabit tutulur.

### 8.2 Şifre değiştirme

1. .env'de BAYIOS_ADMIN_PASSWORD güncellenir.
2. podman-compose up -d (yeniden başlatma).
3. Bütün cihazların oturumu düşer; şifre parmak izi değiştiği için eski çerezler geçersiz
   olur. Herkes yeni şifreyle girer.
4. Çalışan ayrıldığında, şüpheli paylaşımda veya 3 ayda bir rutin olarak yapılır.
5. Yalnız oturum anahtarını (BAYIOS_SESSION_SECRET) değiştirmek de herkesi çıkarır; şifre
   değişikliği için buna gerek yoktur.

### 8.3 Geri dönüş

- Sorun çıkarsa önceki imaja dönülür; .env'deki iki değişken kalabilir (eski sürüm
  yok sayar). Oturum anahtarı değişmediyse çerezler eski sürümde de geçerlidir.
- Şifre/anahtar kaybı: .env'den yeniden üretilir; veri kaybı yoktur.
- Yedek/geri yükleme prosedürü değişmez (auth veritabanına yazmaz).

### 8.4 Sorun giderme — manuel kontrol listesi

| Belirti | Kontrol / çözüm |
| --- | --- |
| Uygulama açılmıyor; log'da BAYIOS_ADMIN_PASSWORD veya BAYIOS_SESSION_SECRET hatası | .env'de iki satır var mı, boş mu, şifre politikasına uyuyor mu? Düzelt, podman-compose up -d. |
| Giriş ekranı gelmiyor | http://127.0.0.1:8000/health 200 mü? podman-compose logs --tail 80 app. |
| Herkes bir anda çıktı | Şifre veya oturum anahtarı değişmiş olabilir; beklenen davranış. |
| Kilit mesajı | 5 dakika bekle. Sunucunun kendi IP'si muaf; başka cihazda dene. |
| .env değişikliği etki etmiyor | podman-compose up -d --force-recreate app. |
| Şifre unutuldu | .env'de yeni şifre, restart; bütün cihazlar çıkar. |
| Log'da bütün istemci IP'leri aynı | §4.5 doğrulaması; container ağ ayarı veya eşik ayarı gerekir. |
| Healthcheck hatası | Compose healthcheck /health'i 127.0.0.1 üzerinden çağırır; auth'ta /health public kalmalıdır. |

## 9. Riskler

| Risk | Etki | Azaltma |
| --- | --- | --- |
| Şifrenin çalışanlar arasında yayılması | Herkes her şeyi yapabilir | Şifre değiştirme prosedürü, kısa ömürlü oturum, ileride kullanıcı hesapları |
| HTTP üzerinden şifrenin ağda görünmesi | Aynı Wi-Fi'daki biri şifreyi yakalayabilir | Misafir ağı ayrımı, WPA2/3, ileride HTTPS |
| Basit şifre seçilmesi | Tahmin; omuz üstünden görülme | 8+ karakter, harf+rakam zorunluluğu, yaygın şifre reddi, 10/5 dk kilit, 3 ayda bir yenileme |
| Kilidin kötüye kullanımı | Bir cihaz 5 dk giriş yapamaz | Kilit IP başına; diğer cihazlar ve muaf sunucu etkilenmez |
| Container'ın kaynak IP'yi gizlemesi | Per-IP kilit ve sunucu muafiyeti çalışmaz | Dağıtımda log'dan doğrulama; gerekirse eşik/ayar değişikliği (bkz. §4.5) |
| Sunucunun her gün kapanması | Kısa erişim kesintisi; kilit sayacı sıfırlanır | Mevcut `restart: unless-stopped` ve otomatik başlatma; oturumlar .env anahtarıyla kalıcı |
| Herkesin aynı şifreyi kullanması | İşlemi kimin yaptığı bilinmez | Bilinen sınırlama; cihaz adı izleme; ileride kullanıcı bazlı hesap |
| .env'in yedek/ekran görüntüsüyle sızması | Şifre ve DB parolası açığa çıkar | .env yedeği şifreli/açık erişimden uzak; Git'e girmiyor |
| Şifre veya oturum anahtarı değişince oturumların düşmesi | Herkesin yeniden giriş yapması | Beklenen davranış; şifre değişimi güvenlik kill-switch'idir. Sunucu restart'ı tek başına oturum düşürmez. |
| /health'in LAN'a açık olması | DB/migration/build bilgisi görünür | Kabul edilen düşük risk; ileride kısıtlanabilir |

## 10. Faz 2 — detaylı auth (bu işin dışında)

1. Kullanıcı bazlı hesaplar (kullanıcı adı + şifre), rol: yönetici / satış / depo (salt okunur + print).
2. İşlem sahipliği: created_by_user_id, "kim ne yaptı" denetim ekranı.
3. Sunucu tarafı oturum tablosu: aktif cihazları görme, tek tek/tümünü çıkarma.
4. Ayarlar ekranından şifre değiştirme ve ilk girişte şifre belirleme.
5. HTTPS (Caddy veya self-signed + telefonlara sertifika), HSTS, CSP, güvenli çerez.
   Ters proxy eklenirse 127.0.0.1 muafiyeti kaldırılır ve gerçek istemci IP'si kullanılır.
6. 2FA (TOTP), cihaz onaylama, giriş bildirimi.
7. Uzaktan erişim öncesi zorunlu: VPN + HTTPS + kullanıcı bazlı yetki.

## 11. Onaylanan kararlar

| No | Konu | Karar |
| --- | --- | --- |
| S1 | Oturum süresi | Varsayılan 12 saat (işaretsiz); "açık kalsın" işaretliyse 30 gün. Sunucu restart'ı oturumu silmez; sabah girişi genellikle 12 saat dolunca gerekir. |
| S2 | Hatalı deneme | Aynı IP'den 10 denemede 5 dakika kilit; loopback ve sunucunun kendi IP'si muaf. |
| S3 | Giriş alanları | Şifre + isteğe bağlı cihaz adı; çalışan adı sorulmaz. |
| S4 | Şifre gücü | En az 8 karakter, en az bir harf + bir rakam; özel karakter zorunlu değil; yaygın şifreler reddedilir. |
| S5 | HTTPS | Bu fazda HTTP; HTTPS detaylı fazda. |
| S6 | Şifre yönetimi | Sunucudaki .env + yeniden başlatma; manuel yol birincil, PS1 opsiyonel. |

**Şifre güvenlik notu:** "password" gibi yaygın bir değer reddedilir; "mavi-kedi-42"
gibi akılda kalan ama harf+rakam içeren bir ifade kabul edilir. Özel karakter zorunluluğu
yoktur; amaç çalışanların şifreyi kağıda yazıp masaya yapıştırmasını engellemek değil,
kolay hatırlanan ama tahmin edilmesi zor bir değer seçmelerini sağlamaktır. Şifre yalnız
çalışanlarla paylaşılmalı, WhatsApp mesaj geçmişinde bırakılmamalı ve personel değişiminde
derhal yenilenmelidir. Gerçek şifre depoya, .env dışına ve sohbete yazılmaz.

Bu kararlar dışında açık soru kalmadı; planın bütünü onaylandığında kodlamaya geçilir.

## 12. Kabul kriterleri (Definition of Done)

1. Şifresiz hiçbir sayfa, dışa aktarım, print veya HTMX parçası veri döndürmüyor;
   yalnız /login, /health, /static/* açık.
2. Doğru şifreyle giriş çalışıyor; hatalı şifrede Türkçe hata, 10 denemede 5 dakika kilit.
3. Çerez HttpOnly + SameSite=Lax; tarayıcıdan elle geçersiz çerez yazılarak girilemiyor.
4. Çıkış çalışıyor; süre dolunca girişe yönlendiriyor; HTMX akışı bozulmuyor.
5. Açık yönlendirme ve CSRF/Origin kontrolleri testle doğrulanıyor.
6. uv run pytest -q ve uv run ruff check src tests temiz.
7. .env.example, .env.production.example, compose.yaml, OPERATIONS.md ve README
   güncel; eksik ayarla uygulama açılmıyor ve hata mesajı yol gösteriyor.
8. PRD/plan/UI/AGENTS.md "auth yok" ifadeleri güncellenmiş; faz 2 listesi kayıtlı.
9. Telefon + masaüstü + A4/A5 print manuel doğrulaması yapılmış.
10. 8 karakterden kısa, harf/rakam eksik veya yaygın şifre startup'ta reddediliyor.
