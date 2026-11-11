from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    href: str
    enabled: bool = False  # flip to True as each module's pages land
    icon: str = ""


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("home", "Ana Sayfa", "/", enabled=True, icon="home"),
    NavItem("products", "Ürünler", "/products", enabled=True, icon="products"),
    NavItem("campaigns", "Kampanyalar", "/campaigns", enabled=True, icon="campaigns"),
    NavItem("offers", "Teklifler", "/offers", enabled=True, icon="offers"),
    NavItem("commissions", "Komisyonlar", "/commissions", enabled=True, icon="settings"),
    NavItem("reservations", "Rezervasyonlar", "/reservations", enabled=True, icon="reservations"),
    NavItem("stock", "Stok/Sayım", "/stock", enabled=True, icon="stock"),
    NavItem("quick_deliveries", "Hızlı Teslim", "/quick-deliveries", icon="quick_deliveries"),
    NavItem("settings", "Ayarlar", "/settings", icon="settings"),
)
