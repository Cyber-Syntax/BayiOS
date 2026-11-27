# Functional core and explicit transaction boundaries

**Status: accepted**

BayiOS, domain kurallarını framework ve I/O'dan bağımsız saf fonksiyonlarda, yan etkileri ise application/adapters katmanında tutacak. Reservation delivery, import commit ve stock count completion gibi use-case'ler açık transaction sınırları ve idempotency/concurrency kontrolleriyle uygulanacak; bu yaklaşım test edilebilirliği korurken stok ve geçmiş kayıtlarının atomikliğini sağlar. Ayrı bir SPA, mikroservis veya genel event-sourcing altyapısı MVP için reddedildi.

