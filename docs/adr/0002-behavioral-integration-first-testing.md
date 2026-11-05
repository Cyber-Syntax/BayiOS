# Behavioral integration-first testing

**Status: accepted**

Test stratejisi, her fonksiyona unit test yazmak yerine kritik kullanıcı davranışlarını gerçek PostgreSQL kullanan application/HTTP integration testleriyle güvenceye alır. Yalnızca karmaşık saf hesap ve state policy'leri unit test edilir; küçük bir Playwright smoke seti browser/clipboard/print sınırlarını doğrular. Böylece MVP yön değiştirirken düşük değerli implementation testlerini koruma maliyeti alınmaz.

