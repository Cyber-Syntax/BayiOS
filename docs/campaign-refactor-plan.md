# Kampanya Sistemi ve Teklif Fiyatlama Refactor Planı

Durum: **Çekirdek + kart ağı + hediye + dışlama grubu uygulandı** (26 Kasım 2026); %100 bedava ürün benefit türü sonraki adım · Hazırlayan: lead · Tarih: 23 Kasım 2026
Kapsam: kampanya veri modeli + sepet çözümleme motoru + teklif toplamları + ödeme tipi UX + yeni kampanya türleri.

Bu belge, bayios'taki kampanyaların tekliflerle birlikte kullanıldığında "tam anlaşılmama" sorununu
çözmek için hedef mimariyi ve iş kırılımını tanımlar. Kaynak gerçeği koddur; alıntılar satır referansıdır.

---

## 0. Mevcut durum teşhisi (sorunun kökleri)

### 0.1 Kampanya ilişkisi semantiği kayboluyor

- `adapters/db/repositories/campaigns.py:189-212` — `active_for_product`, `campaign_version_products`
  tablosunu **yalnızca** `product_id` üzerinden birleştirir; `relation_type` hiç filtrelemez.
  Sonuç: bir ürün kampanyada yalnızca `qualifying` (şart ürünü) olarak listelense bile, teklifte o ürüne
  de "kampanya adayı" çıkar. "Şart ürünü" ile "fayda ürünü" arasında fiilen fark yok.
- `application/offers/__init__.py:1949-2007` (`_campaign_price`) — tek ürün için kampanya fiyatını,
  o ürünün **kendi** taban fiyatını `campaign_scenarios(...)` ile indirgeyerek bulur. Sepetteki diğer
  satırların şart olup olmadığına bakmaz. Yani "A alana B indirimli" türü paket/bundle kampanyalar
  gerçekte tek satır indirimi gibi işlenir.
- `application/offers/__init__.py:1717-1727` (`select_company_price`) — "auto" modu her satır için
  bağımsız olarak "en yüksek indirim" seçer; çapraz satır şart/bundle/kampanya dışlama kurallarını bilmez.
  Bu, 5. ve 6. maddelerdeki "otomatik seç yanlış kampanya seçiyor" ve "iki kampanya birbirini desteklemez"
  sorunlarının ana nedenidir.

### 0.2 "Birleştirilemez" kuralı modelde yok

`domain/campaigns/__init__.py` içindeki `CampaignContract`ta "bu kampanya diğer kampanyalarla
birleştirilemez" (mutual exclusion) için alan yok. `select_company_price` yalnızca satır başına tek
en iyi aday döndürür; sepet genelinde birbirini dışlayan iki kampanya arasında karar verilmez.

### 0.3 "Şirket İndirimi 27.850" opak

- `application/offers/__init__.py:2146-2166` (`_offer_totals`) — `company_discount_total`,
  seçilen şirket fiyatı ile normal fiyat farkının (`company.discount_amount`) adetle çarpılıp
  toplanmasıdır. Hangi indirimin (kampanya mı, Oliz mi) hangi satırda kaç TL kattığını göstermez.
- `offers/detail.html:82` ve `offers/_basket_totals.html:8` bunu tek "Şirket İndirimi" sayısı olarak
  basar. Kullanıcı "27.850'nin içinde ne var?" sorusunun cevabını göremez.

### 0.4 Kayıt sonrası toplamlar eksik

- `application/offers/__init__.py:build_offer_profit_summary` yalnızca `total_revenue`,
  `total_cost`, `total_profit`, `margin_percent` üretir; satış fiyatı toplamı, komisyon sonrası
  toplamı, toplam kampanya hakedişi ve toplam Oliz hakedişi **yok**.
- `offers/detail.html:139-148` tfoot yalnızca 4 sütun basar.
- `offers/detail.html:154-178` "Teklif Satırları" tablosunda "Satır Toplamı" sütunu var ama satır
  altında toplam (adet, normal, oliz, taban, nakit, kart) yok.

### 0.5 Ödeme tipi geçişi ve kart detayı artığı

- `offers/form.html:111-112` — satır başı `unit_price_cash`/`unit_price_card` input'ları
  `x-model` ile bağlı ama ödeme tipi, bayi indirimi veya kampanya değişince **yeniden hesaplanmıyor**
  (`campaignChanged` yalnızca etiket/fiyat alanlarını günceller, birim fiyat kutularını değil).
  Kaydedilen eski değerler edit'te dolu gelir; nakit→kart geçince kart kutusu boş/eski kalır.
- Nakit→kart geçişinde `channel`/`installment_count`/`card_type` `x-show` ile gizlidir; kullanıcı
  doldurmadan kaydederse `application/offers/__init__.py:1149-1156` "kanal, taksit ve kart tipi zorunludur"
  hatası verir.
- `offers/detail.html:70` — `{% if offer.channel %}` ödeme tipinden bağımsızdır; karta geçip tekrar
  nakite dönülmüş kayıtta "Nakit" başlığının altında "Chippin · 2 taksit · Bireysel" kalır.
- `offers/detail.html:71-72` — kart/nakit indirimi üstte büyük kutu olarak yer kaplar; kullanıcı bunu
  satır içinde kompakt görmek ister.

### 0.6 Otomatik kampanya seçimi

- `_prepare_items` içindeki `auto_campaign` dalı (`application/offers/__init__.py:1694-1716`)
  her satır için tüm aktif kampanyaları aday yapar, `select_company_price` en büyük indirimi seçer.
  "270475 EA + BYM 5111 I" örneğinde buz makinesi indirimi yerine 17.850'yi seçmesi ve "BYM bedava"
  senaryosunun kurulamaması bu yüzden: bundle/şart semantiği yok, seçim satır-bazlı ve agresif.

---

## 1. Hedef kampanya mimarisi

Mevcut değişmez sürüm (`campaign_versions` + `campaign_version_products`) korunur; sadece **kural**
yapısı netleştirilir ve teklif tarafına tek bir saf çözümleme motoru eklenir.

### 1.1 Kampanya = Tetikleyici (trigger) + Fayda (benefit) + Birleşme (composition)

`CampaignContract` içinde aşağıdaki net ayrım yapılır:

**Trigger (aktivasyon / şart)** — kampanya ne zaman geçerli:
- `trigger_type`: `none` (her sepet) | `basket_total_min` (sepet eşiği) | `product` (şart ürünleri) | `category` (şart kategorisi).
- `min_basket_total`: `Decimal | None` (125.000 TL gibi).
- `trigger_products[]`: şart ürünleri (mevcut `qualifying` ilişkilerinden gelir).
- `trigger_categories[]`: şart kategorileri (yeni).
- `min_quantity`: şart adedi (opsiyonel).
- `payment_condition`: `bank_id`/ `channel`/ `card_type` (nullable → tüm ödemelerde geçerli; "World/Chippin" için).

**Benefit (fayda)** — kampanya ne veriyor (bir kampanyada birden çok benefit kuralı olabilir):
- `benefit_type`: `line_discount` (satır indirimi, adet başına) | `basket_flat` (sepete tek seferlik sabit
  indirim, "1 kez yararlanılabilir") | `gift` (hediye) | `free_product` (%100 / bedava ürün).
- `benefit_rules[]`: her kural = hedef + kendi indirim tanımı. Aynı kampanyada kurutma→17.850, klima→19.200 gibi
  farklı hedeflere farklı indirim verilebilmesi için gereklidir.
  - `target_type`: `product` | `category`.
  - `target_products[]` / `target_categories[]`: faydanın uygulanacağı ürün/kategori.
  - `discount_type`: `percent` | `fixed_amount` | `special_price` | `free` (yeni, `benefit_type=free_product` ile).
  - `discount_value`: değer.
  - `price_basis`: `regular` | `website_discounted` | `manual`.
  - `applies_per_unit`: `bool` (varsayılan `true`). `false` + `fixed_amount` → "iki kurutma da alsa
    yine 17.850" (sepette hedef mevcutsa tek seferlik sabit indirim).

**Composition (birleşme)**:
- `combines_with_others: bool` (varsayılan `true`).
- `exclusion_group: str | None` (nullable). Aynı gruptaki kampanyalardan sepet için yalnızca biri uygulanır.

### 1.2 Kategori ilişkisi

Mevcut `campaign_version_products` yalnız ürün tutar. Yeni `campaign_version_targets` (veya
`campaign_version_categories`) ile kategori hedefi eklenir; `target_type` (`product`|`category`),
`product_id` (nullable), `category_id` (nullable), `relation_type`, `quantity_required`.
Ürün ilişkisi mevcut tablodan taşınır veya mevcut tablo hedef tipiyle genişletilir (migration kararı).

### 1.3 Saf çözümleme motoru (yeni `domain/campaigns/resolution.py`)

- `resolve_campaigns(basket, campaigns, payment) -> ResolutionResult`
  - Tarih + arşiv + ödeme koşulu filtrele.
  - Her kampanya için trigger'ı **sepet genelinde** doğrula.
  - Her kampanyanın **sepet geneli toplam indirimini** hesapla (benefit kuralları + `applies_per_unit`).
  - `combines_with_others=False` / `exclusion_group` çakışmasını çöz: **aynı dışlama grubundaki
    kampanyalar arasında sepette en büyük toplam indirimi veren kazanır** (POS davranışı, kullanıcı onayı #4).
  - `ResolutionResult`: kazanan kampanya + her satır için benefit (`ResolvedLineBenefit`: `campaign_id`,
    `discount_amount`, `final_price`, `share_amount`, `source`) + kazanamayan adaylar (UI'da
    "neden uygulanmadı" açıklaması için).
- Teklif tarafındaki `_campaign_candidate` / `_campaign_price` bu motorun çıktısını kullanır.

**Not:** "Otomatik (en yüksek indirim)" teklif UI'ında kaldırıldı (çipler, çalışan seçer); ancak motor,
çalışanın seçtiği kampanya ile POS'un gerçekte uygulayacağı kazanan kampanya arasında fark varsa bunu
uyarı olarak gösterir. Böylece teklif, POS çıktısıyla tutarlı olur.

### 1.4 Veri modeli migration notları

- Append-only: yeni alanlar nullable / `server_default` ile eklenir; eski sürümler değişmez.
- `discount_type` enum'una `free` eklenir (check constraint güncellenir).
- `campaigns`/ `campaign_versions`a `combines_with_others`, `exclusion_group`,
  `trigger_type`, `min_basket_total`, `payment_condition` (`bank_id` nullable) eklenir.
- Benefit/target kuralları (hedef + hedef başına indirim) ve kategori hedefleri için yeni tablo
  (`campaign_version_benefits` veya benzeri) + repository/port genişletmesi.
- Teklif `offer_items.campaign_snapshot` artık `resolved_benefit` (uygulanan indirim + pay + kaynak) taşır;
  eski `campaign_discount_amount` alanları okunabilir kalır (backward-compatible okuma).

---

## 2. İş kırılımı (kullanıcı maddeleriyle eşleşen)

### İş 1 — Kampanya modeli + motor (kullanıcı madde 1)

1. `domain/campaigns`: `CampaignContract`a trigger/benefit/composition alanları + `free` indirim tipi.
2. Yeni `domain/campaigns/resolution.py`: saf `resolve_campaigns`.
3. `application/campaigns`: `_build_contract` ve form parse trigger/benefit/kategori alanlarını okur.
4. Repository: kategori hedefleri; `active_for_product` → `active_for_basket` (relation_type'a göre
   trigger vs benefit ayrımı yaparak; şart ürünü artık indirim adayı üretmez).
5. `application/offers/__init__.py`: `_prepare_items` motoru kullanır; `select_company_price` yerine
   seçilen kampanya için sepet-geneli doğrulama.
6. UI: kampanya formu trigger/benefit/kategori/ödeme/birleşme alanları + ilişki etiketleri netleştirilir.
7. "Seçili kurutma/klima" kampanyası şu net modele oturur (kullanıcı onayı #1 + #4):
   - Trigger: `qualifying` = seçili 70cm+ Buzdolabı/Çamaşır/Bulaşık/Ankastre (şart ürünleri).
   - Benefit kuralları (her biri `basket_flat`, `applies_per_unit=false`): Kurutma → `fixed_amount 17.850`
     on `regular`; Klima → `fixed_amount 19.200` on `regular`. (İki kurutma da alsa yine 17.850 —
     "1 kez yararlanılabilir"; 802 KMX / 09605'in "%50" görünümü, o model fiyatının yarısına denk gelen tutardır.)
   - `combines_with_others=false`.
8. **Sonuç:** aynı kampanya içinde birden çok benefit hedefi ve hedef başına farklı indirim değeri
   gerekir → Benefit modeli `benefit_rules[]` olarak tasarlandı (bkz. §1.1).

### İş 2 — Kayıt sonrası toplamlar (kullanıcı madde 2)

1. `build_offer_profit_summary`: `OfferProfitSummary`a `total_sale_price`,
   `total_net_after_commission`, `total_campaign_share`, `total_oliz_share` ekle.
2. `offers/detail.html` "Kâr/Komisyon Özeti" tfoot: satış fiyatı, komisyon sonrası, toplam kampanya
   hakedişi, toplam Oliz hakedişi, toplam gelir, maliyet, kâr/zarar, marj.
3. `offers/detail.html` "Teklif Satırları": "Satır Toplamı" sütununu kaldır; tfoot'a
   **Toplam Adet**, **Normal Toplam**, **Oliz Toplam**, **Taban Toplam**, **Nakit Toplam**, **Kart Toplam** ekle.
   (Bu değerler `offer` zaten `regular_total/oliz_total/cost_total` taşıyor; taban = seçilen şirket fiyatı
   toplamı, nakit/kart = `cash_total`/`card_total`.)

### İş 3 — Ödeme tipi geçişi + indirim gösterimi (kullanıcı madde 3)

1. Form: `paymentType` değişince Alpine tarafında satır `unit_price_cash`/`unit_price_card` önerilen
   fiyatlara göre yeniden doldurulur (mevcut seçili kampanya/oliz tabanı × ilgili bayi indirimi).
   `campaignChanged` ve bayi indirimi input'larına da aynı yeniden hesaplama bağlanır.
2. Nakit→kart geçişinde `channel`/`installment_count`/`card_type` boşsa kayıt engellenir ama kullanıcıya
   **net, satır-içi** uyarı gösterilir (şu anki genel "zorunludur" mesajı yetersiz).
3. Kayıtta `payment_type=cash` ise `channel/bank_id/installment_count/card_type` **null'a çekilir**;
   `offers/detail.html:70` yalnızca `payment_type=='card'` iken kart detayını gösterir.
4. `offers/detail.html` kart/nakit indirimi büyük kutuları kaldırılır; yüzde, satır bazında nakit/kart
   fiyatının yanında küçük etiket olarak (ve sepet toplam satırında) gösterilir.

### İş 4 — Sepet eşiği + hediye + banka özel kampanya (kullanıcı madde 4)

- `trigger_type=basket_total_min` + `benefit_type=gift` + `payment_condition.bank_id` desteği.
- "125 BİN TL üzeri alışverişte Çaycı hediye CM 3626 IC" örneği: `min_basket_total=125000`,
  `gift_products=[CM 3626 IC]`, `payment_condition={bank_id}`.
- **Karar (onaylandı #3):** koşul doğrudan `bank_id` ile tutulur. Şimdilik banka adları elle girilir
  (World kampanyasında ilgili bankalar ayrı ayrı seçilir).
- **Yeni milestone/todo — kart ağı:** bankalara **kart ağı** (World, Bonus, Maximum, Axess, Paraf, Flexi …)
  etiketi eklenir. Böylece kampanya "tüm World kartlar" gibi ağ bazlı hedeflenebilir. Banka ana verisinde
  `card_network` (tek veya çoklu) alanı + Ayarlar ekranında yönetim + kampanya
  `payment_condition.card_network` desteği. (todo.md'ye eklenir.)

### İş 5 — Kategori bazlı şart/fayda + free ürün (kullanıcı madde 5)

- Kategori hedefi (İş 1 ile birlikte).
- `benefit_type=free_product` + `discount_type=free` → "BYM bedava" (bundle: şart ürünü + %100 fayda).
- Test senaryoları: `9120 DMX + 820 KMX → 17.850 indirim (79598-17850=61748 POS)`;
  `12142 A + 802 KMX` (düğün ayrı).

### İş 6 — Otomatik seçim (kullanıcı madde 6 + 5)

- **Karar (onaylandı #2):** "Otomatik (en yüksek indirim)" varsayılanı kaldırılır; sepet satırında ürüne
  özgü **aktif kampanya çipleri** gösterilir, çalışan seçer. PRD "çalışan kampanyayı seçer" ilkesine uyar.
- Öneri B (sonraki faz, isteğe bağlı): sepet-geneli otomatik seçim motoru (İş 1.3) — düğün verisi
  toplanana kadar ertelenir.

### İş 7 — Yan düzeltme: karma ürün grubu komisyonu

- `application/offers/__init__.py:1161/1291/800` `resolve_commission(... product_group=prepared[0].product_group ...)`
  yalnızca ilk satırın grubunu kullanır. Klima + Diğer karışık sepette Ödero bandı/oranı yanlış çözülür.
  `resolve_commission` sepet genelinde en kısıtlayıcı çözümü üretsin ya da ürün grubu başına oran
  ayrıştırılsın (komisyon matrahı sepet toplamı olduğu için grubun tanımı netleştirilmeli).

---

## 3. Düğün + kampanya (kural netleşti — motor kapsamında kodlanır)

**Çözülen kural (kullanıcı POS testi, onaylandı #4):**
- Düğün = `percent 10` on `regular`, benefit ürünleri = düğün ürünleri; her düğün ürünü kendi %10'unu alır
  (adet başına). "Düğün toplamı" = sepetteki tüm düğün ürünlerinin %10 indirimlerinin toplamı.
- 17.850 kampanyası = `basket_flat` sabit indirim; **iki kurutma da alsa yine 17.850** (tek seferlik, adet başına değil).
- İkisi `combines_with_others=false` (birleşmez). POS **toplam indirimi büyük olanı** seçer:
  - 12142 A (düğün, 47.599 → ~4.760 indirim) + 802 KMX (düğün yok) → düğün toplamı ~4.760 < 17.850 →
    **17.850 kazanır** (79598 − 17850 = 61748 POS).
  - Daha fazla düğün ürünü olup düğün toplamı (örn. 18.591) > 17.850 olsaydı → **düğün kazanırdı**.

**Sonuç:** düğün ayrı bir motor değil; genel "karşılıklı dışlama + en büyük toplam indirim kazanır"
kuralının bir örneği. §1.3'teki motor bu kuralı doğrudan karşılar.

**Karar (onaylandı #5):** kurutma + klima birlikte satılmaz; bayiler ürünleri ayrı satıp ayrı fatura
keserek 17.850 ve 19.200'den ayrı ayrı yararlanır. Bu yüzden aynı sepette kurutma + klima toplaması
modellenmez (prd.md §4.7'ye not eklendi).

---

## 4. Uygulama sırası ve kabul kriterleri

1. Migration: kampanya alanları + kategori hedefi + `free` tipi.
2. `domain/campaigns/resolution.py` saf motor + unit testler.
3. Application: kampanya create/update + teklif `_prepare_items` motor entegrasyonu + kategori/banka/hediye.
4. Web: kampanya formu, teklif formu (ödeme geçişi), detay toplamları.
5. Export/import (Excel/JSON) kampanya yeni alanlarını taşır.
6. `ruff check` + hedefli testler + tam `pytest`.

**Kabul kriterleri:**
- Seçili 70cm+ şart ürünü sepetteyken kurutma 17.850 / klima 19.200 **tek seferlik** (adet başına değil)
  uygulanır; `combines_with_others=false` kampanyalar arasında **en büyük toplam indirim kazanır**
  (düğün vs 17.850 örneği POS ile tutarlı).
- Teklif #21/#22 senaryoları aynı sepette şeffaf biçimde açıklanır (hangi indirim, hangi kaynak).
- Kayıt sonrası teklif satırı ve kâr özeti tüm toplamları gösterir; "Satır Toplamı" sütunu kalkar.
- Nakit↔kart geçişi satır fiyatlarını günceller; kart detayı nakitte kalmaz; indirim yüzdesi satır içinde görünür.
- 125B eşik + hediye + banka özel kampanya kurulabilir ve test edilir.
- Kategori bazlı şart/fayda ve "BYM bedava" kurulabilir.
- "Otomatik" seçim kaldırılmış; sepette ürüne özgü kampanya çipleri görünür ve çalışan seçer.

---

## 5. Uygulama durumu (26 Kasım 2026)

Bu bölüm, planın koda nasıl geçtiğini özetler; ayrıntı için kod ve testler esastır.

- **Veri modeli:** `campaign_versions` alanlarına `combines_with_others`, `exclusion_group` ve
  `min_basket_total` eklendi. `campaign_version_products` artık ürün veya kategori hedefi
  taşıyabilir (`category_id`) ve hedef başına `discount_type`, `discount_value`,
  `base_price_type`, `applies_per_unit` alanlarını içerir. Kategori hedefleri `product_name_snapshot`
  içinde kategori adını saklar; kategori silinse de sürüm okunabilir kalır. Migration: `0021`.
- **Saf motor:** `domain/campaigns/resolution.py` sepeti çözer. Şart ürünleri/kategorileri tetikleyici,
  `qualifying` ilişkisi; fayda ürünleri/kategorileri indirim hedefidir. `applies_per_unit=False`
  olan kural sepette bir kez uygulanır ve tutar katılan satırlara normal fiyat ağırlığıyla orantılı
  dağıtılır. Aynı satırda yalnızca tek şirket indirimi (kampanya veya Oliz) geçerlidir. Birden fazla
  olası birleşimde toplam indirimi en büyük yapan çözüm seçilir (POS davranışı).
- **Teklif:** `_prepare_items` satır bazlı seçim yerine sepet çözümlemesini kullanır. Düz (sepet)
  indiriminin satır payı `offer_items.campaign_snapshot` içinde `is_flat_allocation` ve
  `campaign_discount_amount` olarak saklanır; kâr/komisyon satır payı üzerinden hesaplanır.
  Teklif formunda "POS ile aynı (otomatik)" ve yalnız o satıra uygun kampanya seçenekleri gösterilir;
  ayrıca "Sepet Kampanya Önizlemesi" kayıt öncesi gerçek satır paylarını ve toplamı gösterir.
- **Kampanya formu:** Ürün ve kategori hedefleri, hedef başına indirim türü/değeri/tabanı,
  "adet başına / sepette bir kez", birleşme ve sepet alt sınırı düzenlenebilir. Form sade tutuldu.
- **Ödeme koşulu:** Kampanya kanal (POS/Ödero/Chippin), banka(lar), kart tipi ve taksit sayısıyla
  sınırlanabilir. Koşullu kampanya nakit teklifte uygulanmaz; kart teklifinde yalnız eşleşen
  kanal/banka/kart/taksit için geçerlidir. Şart ürününde `quantity_required` artık asgari adet
  olarak doğrulanır. Ödeme koşulları JSON ile taşınır; Excel güncellemesinde korunur.
- **Dışlama grubu:** `exclusion_group` alanı DB/JSON'da korunur; aynı grup için sepet geneli
  "yalnızca bir kampanya" zorlaması henüz UI'da yok. Satır bazlı tek kampanya kuralı geçerlidir.
- **Kart ağı:** `banks.card_networks` ile bankaya World/Bonus/Maximum gibi ağlar atanır; teklifte
  kart ağı seçilebilir ve kampanya ödeme koşulu kart ağına göre filtrelenir.
- **Hediye:** `gift` ilişkili ürünler, kampanyanın tetikleyicisi ve ödeme koşulu sağlandığında teklife
  ayrı satır olarak eklenir. Hediye satırının fiyatı, ilişkideki `gift_price` alanıdır; boşsa ürünün
  Oliz indirimi (normal - Oliz) kullanılır. Satır **Oliz** kaynağıyla işlenir; normal/Oliz fiyatları ve
  Oliz hakedişi (%85) teklif toplamlarına yansır. İsteğe bağlı hediyede çalışan "Hediye yok" seçerse
  satır eklenmez. Hediye satırı rezervasyon/teslim akışına dahildir; stok çıkışı normal teslimatla yapılır.
- **Bedava ürün indirimi:** %100 indirimli ürün (fiyatı sıfırlayan kural) henüz ayrı bir benefit türü
  olarak modellenmedi; hediye satırı bunun pratik karşılığıdır.
- **Dışlama grubu:** Aynı `exclusion_group` değerine sahip kampanyalardan sepet genelinde en yüksek
  toplam indirimi veren uygulanır; gruptaki diğer kampanyalar o sepette devre dışı kalır.
- **İçe/dışa aktarma:** JSON kategori hedeflerini ve kural alanlarını taşır; aynı şema ile geri
  içe aktarılabilir. Excel ürün sayfası yalnız ürün ilişkilerini taşır; mevcut kampanya Excel'den
  güncellenirse kategori kuralları ve kampanya seviyesindeki birleşme/eşik alanları korunur.
- **Gerçek veri:** "Seçili Beyaz Eşya, Ankastre Set..." kampanyasının mevcut 75/77 ürün ilişkisi
  `qualifying` yapıldı; Kurutma Makinesi kategorisi için 17.850 TL ve Klima kategorisi için
  19.200 TL `applies_per_unit=False` fayda kuralı eklendi. Yeni sürüm: v7.
- **Doğrulama:** Düğün + Oliz ve 17.850 TL sepet indirimi senaryoları domain, application ve
  web testlerinde doğrulanır; sepette bir kez uygulanan tutarın katılan satırlara orantılı dağıtımı
  test edilir. Tam test paketi ve `ruff check` temizdir.
