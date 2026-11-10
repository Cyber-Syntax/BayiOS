# BayiOS

BayiOS is a local dealer operations context for managing products, offers, reservations, stock, and delivery workflows.

## Commercial concepts

**Campaign**:
A dated commercial promotion or pricing guide that may reference condition products, benefit products, discounts, gifts, and a price basis. In MVP it is a guide and scenario source, not a general basket optimization engine.
_Avoid_: Scraped promotion, automatic POS campaign

**Customer**:
A person or organization receiving an offer or delivery, identified by name and optionally by phone number.
_Avoid_: Client, buyer, account

**Barcode**:
The complete, unmodified text decoded from a printed Code 128 barcode. A barcode is an operational identifier only and is not linked to a product catalog record in MVP.
_Avoid_: Product code, SKU, product identifier

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

**Hızlı Teslim**:
A workflow that stores a customer's name with one confirmed Code 128 barcode text for operational tracking before or alongside WMS processing. It does not identify or select a product from the catalog and does not perform the WMS exit.
_Avoid_: Quick sale, product lookup, WMS shipment
