from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    href: str
    enabled: bool = False  # flip to True as each module's pages land


NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("home", "Ana Sayfa", "/", enabled=True),
    NavItem("products", "Ürünler", "/products"),
    NavItem("campaigns", "Kampanyalar", "/campaigns"),
    NavItem("offers", "Teklifler", "/offers"),
    NavItem("reservations", "Rezervasyonlar", "/reservations"),
    NavItem("stock", "Stok/Sayım", "/stock"),
    NavItem("quick_deliveries", "Hızlı Teslim", "/quick-deliveries"),
    NavItem("settings", "Ayarlar", "/settings"),
)
