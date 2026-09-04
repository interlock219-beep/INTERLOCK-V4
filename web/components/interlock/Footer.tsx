"use client"

import { Github, Mail } from "lucide-react"
import { InterlockBrand } from "./Brand"

const columns: Record<string, { label: string; href: string; external: boolean }[]> = {
  Product: [
    { label: "Capabilities", href: "#control", external: false },
    { label: "Recovery", href: "#recovery", external: false },
    { label: "Security", href: "#security", external: false },
  ],
  Documentation: [
    { label: "Quickstart", href: "https://github.com/interlock219-beep/INTERLOCK-V4/blob/master/docs/developer/QUICKSTART.md", external: true },
    { label: "SDK reference", href: "https://github.com/interlock219-beep/INTERLOCK-V4/blob/master/sdk/README.md", external: true },
    { label: "Architecture", href: "https://github.com/interlock219-beep/INTERLOCK-V4/blob/master/docs/architecture/ARCHITECTURE.md", external: true },
    { label: "Threat model", href: "https://github.com/interlock219-beep/INTERLOCK-V4/blob/master/docs/security/SECURITY_ASSURANCE_REPORT.md", external: true },
  ],
}

export function Footer() {
  return (
    <footer className="relative border-t border-white/5 py-16">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(16,185,129,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(16,185,129,0.02)_1px,transparent_1px)] bg-[size:60px_60px]" />

      <div className="relative mx-auto max-w-7xl px-6">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-5 mb-12">
          <div className="col-span-2 md:col-span-1">
            <div className="mb-4">
              <InterlockBrand size="lg" />
            </div>
            <p className="text-sm text-intent-muted max-w-xs">
              Recovery and control plane for AI agents.
            </p>
          </div>

          {Object.entries(columns).map(([title, links]) => (
            <div key={title}>
              <h4 className="text-xs font-semibold tracking-widest uppercase text-intent-muted mb-4">
                {title}
              </h4>
              <ul className="space-y-3">
                {links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      target={link.external ? "_blank" : undefined}
                      rel={link.external ? "noopener noreferrer" : undefined}
                      className="text-sm text-intent-muted hover:text-emerald-300 transition-colors"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="border-t border-white/5 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-sm text-intent-muted">
            © {new Date().getFullYear()} Interlock. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            <a
              href="https://github.com/interlock219-beep/INTERLOCK-V4"
              target="_blank"
              rel="noopener noreferrer"
              className="text-intent-muted hover:text-emerald-300 transition-colors"
              aria-label="GitHub"
            >
              <Github className="h-5 w-5" />
            </a>
            <a
              href="https://mail.google.com/mail/?view=cm&fs=1&to=interlock219@gmail.com&su=Interlock%20V4%20Inquiry&body=Hi%20Interlock%20team%2C%0A%0AI%20have%20a%20question%20about%20Interlock%20V4.%0A%0ABest%2C%0A%5BName%5D"
              className="text-intent-muted hover:text-emerald-300 transition-colors"
              aria-label="Email"
            >
              <Mail className="h-5 w-5" />
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
