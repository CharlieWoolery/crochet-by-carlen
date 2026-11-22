from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OrderItemSummary:
    product_name: str
    variant_name: str | None
    quantity: int
    unit_price_cents: int


@dataclass
class OrderConfirmationData:
    order_number: str
    customer_name: str
    customer_email: str
    fulfillment_method: str
    address: str | None
    subtotal_cents: int
    fulfillment_fee_cents: int
    total_cents: int
    items: list[OrderItemSummary]
    venmo_handle: str | None
    zelle_contact: str | None
    paypal_link: str | None


async def send_order_confirmation(data: OrderConfirmationData) -> None:
    """
    Send an order confirmation email.

    Currently logs to the console. Replace the body of this function with a
    real email provider (e.g. Resend, SendGrid) at deploy time — the interface
    is stable.
    """
    item_lines = "\n".join(
        f"  {i.quantity}x {i.product_name}"
        + (f" ({i.variant_name})" if i.variant_name else "")
        + f" — ${i.unit_price_cents / 100:.2f} each"
        for i in data.items
    )
    payment_lines = "  ".join(
        filter(
            None,
            [
                f"Venmo: {data.venmo_handle}" if data.venmo_handle else None,
                f"Zelle: {data.zelle_contact}" if data.zelle_contact else None,
                f"PayPal: {data.paypal_link}" if data.paypal_link else None,
            ],
        )
    )

    logger.info(
        "\n"
        "=== ORDER CONFIRMATION (console stub — wire up email provider before deploy) ===\n"
        "To:              %s <%s>\n"
        "Order number:    %s\n"
        "Fulfillment:     %s%s\n"
        "Items:\n%s\n"
        "Subtotal:        $%.2f\n"
        "Fulfillment fee: $%.2f\n"
        "Total:           $%.2f\n"
        "Pay via:         %s\n"
        "                 (include %s in your payment note)\n"
        "=============================================================================",
        data.customer_name,
        data.customer_email,
        data.order_number,
        data.fulfillment_method,
        f" → {data.address}" if data.address else "",
        item_lines,
        data.subtotal_cents / 100,
        data.fulfillment_fee_cents / 100,
        data.total_cents / 100,
        payment_lines or "no payment handles configured",
        data.order_number,
    )
