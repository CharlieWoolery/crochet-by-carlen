import { Route, Routes } from 'react-router-dom'
import Footer from './components/layout/Footer'
import Header from './components/layout/Header'
import About from './pages/About'
import Admin from './pages/Admin'
import Cart from './pages/Cart'
import Checkout from './pages/Checkout'
import Collection from './pages/Collection'
import CustomRequest from './pages/CustomRequest'
import Home from './pages/Home'
import OrderConfirmation from './pages/OrderConfirmation'
import PastWork from './pages/PastWork'
import Product from './pages/Product'

export default function App() {
  return (
    <div className="min-h-screen flex flex-col bg-white text-ink">
      <Header />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/shop" element={<Collection />} />
          <Route path="/products/:slug" element={<Product />} />
          <Route path="/cart" element={<Cart />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/orders/:orderNumber" element={<OrderConfirmation />} />
          <Route path="/custom-request" element={<CustomRequest />} />
          <Route path="/past-work" element={<PastWork />} />
          <Route path="/about" element={<About />} />
          {/* Admin routes — owner-only, mobile-first dashboard */}
          <Route path="/admin/*" element={<Admin />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
