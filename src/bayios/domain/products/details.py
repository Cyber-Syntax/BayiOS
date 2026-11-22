from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ProductFeature:
    title: str = ""
    text: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "text": self.text, "note": self.note}


@dataclass(frozen=True)
class ProductSpecification:
    group: str = ""
    name: str = ""
    value: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"group": self.group, "name": self.name, "value": self.value}


@dataclass(frozen=True)
class ProductDetails:
    features: tuple[ProductFeature, ...] = ()
    specifications: tuple[ProductSpecification, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.features and not self.specifications

    def to_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "features": [feature.to_dict() for feature in self.features],
            "specifications": [
                specification.to_dict()
                for specification in self.specifications
            ],
        }

    @classmethod
    def from_json(cls, value: object) -> ProductDetails:
        """Parse the canonical details object; empty lists are allowed."""
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise TypeError("Ürün detayı JSON nesnesi olmalıdır.")
        raw_features = value.get("features", [])
        raw_specifications = value.get("specifications", [])
        if not isinstance(raw_features, list):
            raise TypeError("features bir liste olmalıdır.")
        if not isinstance(raw_specifications, list):
            raise TypeError("specifications bir liste olmalıdır.")
        features = tuple(
            ProductFeature(
                title=_text(item.get("title")),
                text=_text(item.get("text")),
                note=_text(item.get("note")),
            )
            for item in raw_features
            if _is_mapping(item)
        )
        specifications = tuple(
            ProductSpecification(
                group=_text(item.get("group")),
                name=_text(item.get("name")),
                value=_text(item.get("value")),
            )
            for item in raw_specifications
            if _is_mapping(item)
        )
        if len(features) != len(raw_features):
            raise ValueError("features içindeki her öğe nesne olmalıdır.")
        if len(specifications) != len(raw_specifications):
            raise ValueError("specifications içindeki her öğe nesne olmalıdır.")
        return cls(features=features, specifications=specifications)


def _is_mapping(value: object) -> bool:
    return isinstance(value, dict)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float, Decimal)):
        return str(value).strip()
    raise ValueError("Detay alanları metin olmalıdır.")
