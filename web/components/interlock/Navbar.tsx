"use client"

import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Menu, X, ArrowRight } from "lucide-react"
import { InterlockBrand } from "./Brand"

const navLinks = [
  { label: "Product", href: "#control" },
  { label: "How It Works", href: "#architecture" },
  { label: "Recovery", href: "#recovery" },
  { label: "Security", href: "#security" },
  {
    label: "Documentation",
    href: "https://github.com/interlock677-debug/intentlock/tree/master/docs/INDEX.md",
    external: true,
  },
]

export function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    window.addEventListener("scroll", onScroll)
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-intent-bg/80 border-b border-white/5 backdrop-blur-xl"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex items-center justify-between h-16">
          <a href="/" aria-label="Interlock home" className="flex items-center">
            <InterlockBrand size="md" />
          </a>

          <div className="hidden md:flex items-center gap-8">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                target={link.external ? "_blank" : undefined}
                rel={link.external ? "noopener noreferrer" : undefined}
                className="text-sm text-intent-muted hover:text-emerald-300 transition-colors"
              >
                {link.label}
              </a>
            ))}
          </div>

          <div className="hidden md:flex items-center gap-3">
            <a
              href="mailto:interlock677@gmail.com"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black text-sm font-medium transition-colors"
            >
              Request Demo
              <ArrowRight className="w-4 h-4" />
            </a>
          </div>

          <button
            type="button"
            onClick={() => setOpen(!open)}
            className="md:hidden p-2 text-intent-muted hover:text-emerald-300 transition-colors"
            aria-label="Toggle menu"
            aria-expanded={open}
          >
            {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="md:hidden border-t border-white/5 bg-intent-bg/90 backdrop-blur-xl"
          >
            <div className="px-6 py-4 space-y-3">
              {navLinks.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  target={link.external ? "_blank" : undefined}
                  rel={link.external ? "noopener noreferrer" : undefined}
                  className="block text-sm text-intent-muted hover:text-emerald-300 transition-colors py-2"
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                </a>
              ))}
              <div className="pt-3 border-t border-white/10">
                <a
                  href="mailto:interlock677@gmail.com"
                  className="flex items-center justify-center gap-2 w-full px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black text-sm font-medium transition-colors"
                  onClick={() => setOpen(false)}
                >
                  Request Demo
                  <ArrowRight className="w-4 h-4" />
                </a>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  )
}
