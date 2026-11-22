# BayiOS

BayiOS is a local dealer operations context for managing products, offers, reservations, stock, and delivery workflows.

## Commercial concepts

**External product ID**:
The scraper-provided string identifier stored on a product as `external_id`; it can change when the same product is re-released under a new serial series. It is separate from the internal UUID used by offers and reservations.
_Avoid_: Primary key, product code, barcode

**Product ID history**:
The aliases (`product_external_id_history`) that map previous external IDs to a product. They let old offer, reservation and campaign files resolve to the current product while the product keeps its newest ID.
_Avoid_: Audit log, duplicate product

**Product details**:
The scraper-provided `features` and `specifications` text stored in `products.details` JSONB, together with optional `source_url`, `kind` and `scraped_at` metadata. Media files are not part of the model.
_Avoid_: Media gallery, HTML description, scraped page

**Campaign**:
A dated commercial promotion or pricing guide that may reference condition products, benefit products, discounts, gifts, and a price basis. In MVP it is a guide and scenario source, not a general basket optimization engine.
_Avoid_: Scraped promotion, automatic POS campaign

**Campaign version**:
An immutable snapshot of a campaign's fields and product relations, created on each effective edit. The campaign row points to the current version; historical versions are retained for audit and offer snapshots.
_Avoid_: Campaign edit log, mutable campaign snapshot

**Campaign scenario**:
A computed price example for a campaign, showing gift-present and gift-absent outcomes using the applicable price basis and dealer discount rate. It is a guide, not an automatically applied sale price.
_Avoid_: POS price, automatic discount

**Dealer floor price**:
The product-specific minimum cash or card sale price for the dealer, stored and historically tracked separately from the general dealer discount rate.
_Avoid_: Campaign price, offer price

**Dealer discount setting**:
The global default dealer discount percentage used by the campaign guide and as the initial card/cash discount on a new offer, defaulting to 10% and retaining a history of changes. A worker may override the card and cash rates separately per offer.
_Avoid_: Fixed dealer rate, commission rate

**Card dealer discount**:
The per-offer percentage deducted from the company base price to derive the suggested card price. The worker may override both the percentage and the final card unit price.
_Avoid_: Commission rate, cash discount

**Cash dealer discount**:
The per-offer percentage deducted from the company base price to derive the suggested cash price. It is independent of the card dealer discount and may differ from it.
_Avoid_: Commission rate, card discount

**Commission period**:
A monthly, effective-dated set of card commission rates and installment limits. A new period is normally copied from the previous month; past periods are immutable and offers keep their own commission snapshot.
_Avoid_: Live commission table, editable history

**Payment channel**:
The route used for a card payment: physical POS, Ödero mail order, or Chippin. Every channel may define a bankless general rate or a bank-specific override; Chippin typically keeps a general 1-installment rate and per-bank/card installment limits.
_Avoid_: Payment method, bank

**Product commission group**:
The product classification used for commission rates. Klima is the only separate group; every other product, including TV, uses the standard (other) group. Per-category installment caps are editable period data, not code constants.
_Avoid_: Category, campaign type

**General commission rate**:
A commission row with no bank selected. It applies to every bank that has no bank-specific row for the same scope; a bank-specific row overrides it only for that bank.
_Avoid_: Default bank, fallback rate

**Installment limit**:
The maximum number of installments for a scope (channel, bank, product group, category or card type), stored as monthly period data. A bank-specific limit replaces the bankless general limit for that bank and may raise or lower it; other scopes still apply.
_Avoid_: Hard-coded cap, TV limit

**Offer snapshot**:
The immutable record of product prices, selected campaign version, card and cash dealer discounts, bank name, commission rate and final offer lines captured when an offer is created or updated.
_Avoid_: Live offer recalculation, current price view

**Commission base**:
The amount used to select the card commission band, equal to the customer's final card total (`card_total`). It is not the pre-discount company base price and is never the cash total.
_Avoid_: Base price total, cash total

**Customer**:
A person or organization receiving an offer or delivery, identified by name and optionally by phone number.
_Avoid_: Client, buyer, account

**Offer**:
A commercial proposal containing one or more products and payment options that has not yet been accepted.
_Avoid_: Quote, sale

**Reservation**:
A record that tracks products and the customer for a confirmed sale, without reserving or reducing physical stock. Physical stock decreases only when a reservation line reaches Delivered.
_Avoid_: Order, allocation

**Delivered**:
The terminal reservation state in which the delivery is completed and physical stock is reduced once.
_Avoid_: Completed sale

**Reservation item**:
A quantity-bearing product line within a Reservation whose delivery and cancellation progress is tracked independently.
_Avoid_: Order line, shipment line

**Reservation reminder**:
The due date at which a reservation's open quantity should be reviewed with the customer, defaulting to 13 months after the reservation date. Snoozing records history and never cancels the reservation automatically.
_Avoid_: Expiry, auto-cancel

## Stock concepts

**Stock movement**:
An append-only record describing a physical stock change, such as an import update, count adjustment, or delivered quantity.
_Avoid_: Inventory overwrite, deleted adjustment

**Physical stock**:
The quantity physically present at the dealer.
_Avoid_: Inventory balance

**Open reservation**:
The quantity of products on reservations that have not yet reached Delivered. It is reported separately from physical stock and never subtracted from it.
_Avoid_: Reserved inventory

## Operational concepts

**Import batch**:
A staged set of source rows and explicit decisions prepared for review before an atomic product catalog commit.
_Avoid_: Direct CSV update

**Actor context**:
Audit metadata identifying the client device and optional worker name for an operation. It is not authentication or authorization.
_Avoid_: User identity, permission

**Depot ready**:
A reservation state meaning the products are prepared for handoff to the delivery service.
_Avoid_: Picked

**Service assigned**:
A reservation state meaning a delivery service has been assigned to the reservation.
_Avoid_: Shipped

_Avoid_: Quick sale, product lookup, WMS shipment
