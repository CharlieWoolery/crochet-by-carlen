import { useParams } from 'react-router-dom'

export default function Product() {
  const { slug } = useParams<{ slug: string }>()

  return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <h1 className="font-display italic font-light text-3xl text-ink mb-6">
        {slug}
      </h1>
      {/*
        Product detail: photo gallery with focal-point aware display,
        variant swatches (image switches on tap), lead time, materials,
        dimensions, pattern credit, add-to-cart button.
        Open Graph meta tags for Instagram/Facebook link previews.
      */}
      <p className="text-ink/35 text-sm">Product detail coming soon.</p>
    </div>
  )
}
