# Aylık komisyon dönemleri ve değişmez geçmiş

**Status: accepted**

Kredi kartı komisyonları ay bazında değiştiği için komisyon verisi aylık dönemler halinde saklanacak. Her dönem `period_key` (`YYYY-MM`), `valid_from`–`valid_until`, durum ve önceki dönem bağlantısı taşır. Ay başında çalışan yeni dönemi önceki dönemi kopyalayarak açar, oranları ve limitleri günceller, ardından dönemi aktifleştirir. Geçmiş dönemler değiştirilmez.

Komisyon matrisi kanal, banka, ürün komisyon grubu, taksit ve Ödero tutar bandı boyutlarında tutulur. POS ve Ödero banka bazlıdır; Chippin bankadan bağımsızdır. Klima ayrı komisyon grubudur; TV diğer ürünlerle aynı komisyon oranını kullanır ancak taksit limiti farklıdır. Etkin taksit üst sınırı kanal, banka/kanal, ürün grubu, kart tipi ve mevcut oran satırlarının minimumudur.

Teklifler seçildikleri andaki komisyon oranını, bayi indirimini, kampanya sürümünü ve fiyat katmanlarını snapshot olarak taşır. Dönem veya oran sonradan değişse de eski teklif değişmez. Tek seferlik komisyon tablosu veya yalnızca güncel tablo yaklaşımı, ay geçişlerinde geçmiş teklifleri ve planlamayı güvenilir biçimde korumadığı için reddedildi.
