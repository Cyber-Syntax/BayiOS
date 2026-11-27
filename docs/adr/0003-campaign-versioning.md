# Immutable campaign versions with a current pointer

**Status: accepted**

Kampanya düzenlemeleri, `campaigns` satırında yalnızca kimlik, arşiv durumu ve `current_version_id` işaretçisi tutacak şekilde modellenecek. Kampanya alanları ve ürün ilişkileri her düzenlemede `campaign_versions` / `campaign_version_products` içine yeni ve değişmez bir sürüm olarak yazılacak; eski sürümler hiçbir zaman güncellenmeyecek. Fiili değişiklik yoksa yeni sürüm üretilmeyecek, kampanyalar kalıcı silinmek yerine arşivlenecek.

Bu karar, geçmiş tekliflerin kampanya koşullarını sonradan değiştirmemesini (FR-CAMP-12) ve M5 teklif snapshot'ının hangi sürüme dayandığının denetlenebilmesini sağlar. Güncel kaydı yerinde güncellemek ve yalnızca `campaign_history` JSON snapshot'ı tutmak, ürün ilişkilerinin geçmişini ve sürüm kimliğini güvenilir biçimde korumadığı için reddedildi. Sürüm geçmişi audit ve snapshot kaynağıdır; aktif kampanya sorgusu güncel sürümün tarihleriyle yapılır, eski sürümler geçmiş tarihli sorgu için zaman makinesi olarak kullanılmaz.
