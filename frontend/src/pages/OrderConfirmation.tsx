import { useParams } from 'react-router-dom'

export default function OrderConfirmation() {
  const { orderNumber } = useParams<{ orderNumber: string }>()

  return (
    <div className="max-w-2xl mx-auto px-4 py-12 text-center">
      <h1 className="font-display italic font-light text-3xl text-ink mb-4">
        Order Confirmed
      </h1>
      <p className="text-ink/60 text-sm mb-2">Your order number is</p>
      <p className="font-semibold text-2xl text-brand mb-6">{orderNumber}</p>
      {/*
        Shows order number, instructions to include it in the payment note,
        and the owner's payment handles (Venmo / Zelle / PayPal) from settings.
      */}
      <p className="text-ink/35 text-sm">Full confirmation page coming soon.</p>
    </div>
  )
}
