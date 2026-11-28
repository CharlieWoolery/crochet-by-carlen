export default function Checkout() {
  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <h1 className="font-display italic font-light text-3xl text-ink mb-6">
        Checkout
      </h1>
      {/*
        Fulfillment method (ship / pickup / drop-off), shipping address
        (required for ship and drop-off), customer name/email/phone,
        order summary with server-computed totals. POSTs to /api/orders.
      */}
      <p className="text-ink/35 text-sm">Checkout coming soon.</p>
    </div>
  )
}
