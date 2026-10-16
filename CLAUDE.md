Crochet by Carlen — Project Spec

New website for Crochet by Carlen, a small made-to-order crochet business. Replaces the current Google Sites page. The owner (non-technical) posts seasonal items; customers order them, and she makes each piece after the order is placed. Most orders currently come through Instagram and Facebook DMs; the site is primarily the "link in bio" destination, so nearly all visitors arrive on a phone.

This is also a portfolio project. Favor clear, explainable code over clever code. When making a non-obvious decision, leave a short comment explaining why.

Stack
Layer	Choice
Frontend	React + TypeScript (mobile-first)
Backend	Python, FastAPI
ORM / migrations	SQLAlchemy 2.0 + Alembic
Database	PostgreSQL (hosted: Neon)
Image processing	Pillow + pillow-heif, output WebP
Image storage	Object storage (Cloudflare R2 or Supabase Storage — TBD). DB stores URLs only
Payments	Phase 1: customer pays owner directly (Venmo / Zelle / PayPal). Phase 2: PayPal Checkout + webhooks
Hosting	TBD
Domain	crochetbycarlen.com (Squarespace Domains)
Branding

Keep the owner's existing look:

Logo: "Crochet by Carlen" in pink script inside a purple circle, with a purple yarn ball and crochet hook, and a small purple heart
Palette: pink (logo script), purple (circle, yarn ball), whitewashed wood / off-white, warm wood tones
Product photos are natural light: outdoor field/wood table shots and indoor shots in front of the logo sign
Need a digital logo file from the owner (don't crop it from a photo)
Core business rules
Made to order. No inventory counts. Items are made after the order is placed.
Collections / seasons. Products belong to collections (e.g. "Fall 2026") with optional open/close dates. Items can only be ordered while their collection is open.
Ended seasons are archived, never deleted. Archived items stay visible in a past-work gallery but can't be ordered. Past orders stay intact.
Lead time per product. The owner sets a free-text lead time on each product (e.g. "1–2 weeks").
Optional per-item order caps. Supported in the model, off by default (null = no cap).
Fulfillment options:
Ship: flat $6 per order (not per item). Requires shipping address.
Local pickup: free.
Local drop-off: owner delivers locally. Requires address. Fee/area TBD (default: free).
Shipping rate and drop-off fee live in settings so the owner can change them.
The pickup address is never public. It is never returned by any public endpoint or rendered on the site. It only appears in the confirmation email for pickup orders.
Payment is separate from fulfillment. Orders are created at checkout as unpaid. Customers pay the owner directly via Venmo, Zelle, or PayPal, any time up until they receive the item. The owner marks orders paid in the admin.
Order numbers. Every order gets a short, human-friendly order number (e.g. CBC-1042). The confirmation page and email tell the customer to put it in the payment note so the owner can match payments to orders.
Backend is the source of truth. Never trust prices, availability, or totals from the client. POST /orders reloads every cart item from the DB and validates:
product is live and its collection is open
per-item cap not exceeded (if set)
address present when fulfillment is ship or drop-off
If anything fails → return 409 (or 422 for bad input) with details so the frontend can notify the customer.
Totals are computed server-side: subtotal + fulfillment fee.
Guest checkout. No customer accounts. Email confirmation after ordering, including order number and the owner's payment handles.
Orders from DMs are tracked too. The owner can enter orders that came in through Instagram/Facebook so all orders live in one place. Every order records its source.
Custom requests. Customers can submit a request for something not listed. These are separate from orders.
Image handling

Owner uploads photos straight from her iPhone/iPad camera roll. Photos come in mixed shapes (portrait, landscape, square).

On upload (never per request):

Accept JPEG, PNG, and HEIC (convert with pillow-heif)
Apply EXIF orientation, then strip all EXIF metadata (iPhone photos can contain GPS location — protects the owner's home address)
Generate three WebP sizes: small (~400px, grid), medium (~1000px, product page), large (~2000px, zoom)
Upload to object storage; save URLs + original width/height in product_images

Display:

Product grid uses uniform square cards: aspect-ratio: 1 / 1; object-fit: cover;
Each image has a focal point (focal_x, focal_y, 0–100, default 50/50) applied as object-position: {focal_x}% {focal_y}% so cropping keeps the important part in view
In the admin, the owner taps the photo to set the focal point
Frontend uses srcset/sizes so the browser picks the right size; images below the fold use loading="lazy"
Data model

Money is stored as integer cents. Never floats.

collections — id, name, slug, description, opens_at (nullable), closes_at (nullable), status (draft / live / archived)
products — id, collection_id, name, slug, description, price_cents, materials, dimensions (nullable), pattern_credit, pattern_credit_url (nullable), lead_time (text, nullable), order_cap (nullable), status (draft / live / archived), created_at
product_images — id, product_id, storage_key, url_small, url_medium, url_large, width, height, focal_x (default 50), focal_y (default 50), alt_text, sort_order
variants — id, product_id, name (e.g. "Blue", "Cotton"), option_type (color / material), swatch_hex (nullable), image_id (nullable — main photo switches when selected), price_cents (nullable override)
orders — id, order_number (unique), customer_name, customer_email, customer_phone (nullable), source (website / instagram / facebook / other), fulfillment_method (ship / pickup / dropoff), address (nullable; required for ship and dropoff), subtotal_cents, fulfillment_fee_cents, total_cents, payment_status (unpaid / paid), payment_method (venmo / zelle / paypal / cash / other, nullable), paid_at (nullable), fulfillment_status (received → in_progress → shipped / ready_for_pickup / out_for_dropoff → delivered), notes, created_at
order_items — id, order_id, product_id, variant_id (nullable), quantity, unit_price_cents (snapshot at order time)
custom_requests — id, name, email, description, reference_image_url (nullable), status (new / quoted / accepted / declined), created_at
settings — single row: venmo_handle, zelle_contact, paypal_link, shipping_flat_cents (default 600), dropoff_fee_cents (default 0), pickup_address (private), contact_email, instagram_url, facebook_url, tiktok_url

Notes:

The turtle matching game is a fixed set → one product, no special handling.
Hair scrunchies (Blue/Yellow/Lavender/Hot Pink) become one product with color variants; each variant links to its own photo so the main image switches when a swatch is tapped.
API — public
GET  /collections              open collections
GET  /collections/archived     past-work gallery
GET  /products?collection=     products in a collection
GET  /products/{slug}          product detail (clean shareable URL)
POST /orders                   validate cart → create unpaid order → send confirmation
POST /custom-requests          submit a custom request
API — admin

TODO (Charlie): design these routes and decide how admin auth works.

The admin must let the owner:

create, edit, publish, and archive collections and products
upload photos from her camera roll, reorder them, and tap to set each photo's focal point
manage variants (swatches + linked photos)
see new orders and update fulfillment status
mark orders paid (with payment method)
see who still owes her, including delivered-but-unpaid orders
enter orders that came in through Instagram/Facebook DMs
view and respond to custom requests
edit settings (payment handles, shipping rate, drop-off fee, pickup address, social links)

The owner will use an iPhone or iPad → the admin UI must be touch-friendly and mobile-first. "Add a product" is the most important admin screen.

Pages (frontend)
Home / current collection
Collection page (square card grid)
Product page (photo gallery, variant swatches, lead time, materials, size, pattern credit)
Cart + checkout (fulfillment choice: ship / pickup / drop-off; address when needed; order summary)
Order confirmation (order number + how to pay)
Custom request form
Past work gallery (archived items)
About (carry over existing About content)
Admin dashboard (owner only, mobile-first)

Every product page needs Open Graph tags (title, price, photo) so links pasted into Instagram/Facebook DMs show a preview.

Content to migrate from the current site
Brand name, About page text, contact email, Facebook / Instagram / TikTok links
Full product list with prices, materials, sizes, and pattern credits
New products not on the old site: succulents, beaded wristlet keychains, pink clip-on keychain, sparkle scrubby
Photos: original files from the owner
Open questions (ask the owner)
Drop-off: any fee? Limited to a certain area?
How many orders can she handle at once? (decides whether to turn on caps)
How often do new seasonal collections go up?
Digital logo file?
Character-based items (e.g. Poké Ball, Cera): list on the site or custom-request only?
Build order
Database models + Alembic migrations (collections, products, images, variants first; orders after)
Image upload pipeline (HEIC → resize → WebP → strip EXIF → object storage)
Public collection/product endpoints
Orders + custom requests endpoints, confirmation email
Admin endpoints + auth
React frontend (start with object-fit: cover, add focal-point picker in admin)
Deploy + connect crochetbycarlen.com
Phase 2: PayPal Checkout + webhook (marks orders paid automatically; must be idempotent)
Working agreements
Keep changes small and reviewable. One feature per change.
Write tests for business rules (order window validation, caps, server-side totals incl. fulfillment fee, address required for ship/dropoff, order number uniqueness, pickup address never in public responses, EXIF stripped from processed images).
Secrets (DB URL, storage keys, email API keys) live in environment variables, never in code.
Track real usage metrics from launch (orders by source, orders processed, revenue handled, products listed, image payload size before/after processing) for the portfolio write-up.