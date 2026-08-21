"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { motion } from "framer-motion"
import {
  Shield,
  LayoutDashboard,
  Activity,
  CreditCard,
  Settings,
  Key,
  LogOut,
  Menu,
  X,
  Bell,
  Search,
} from "lucide-react"
import { useAuth } from "@/components/AuthProvider"

const navigation = [
  { name: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { name: "Usage", href: "/dashboard/usage", icon: Activity },
  { name: "Billing", href: "/dashboard/billing", icon: CreditCard },
  { name: "API Keys", href: "/dashboard/api-keys", icon: Key },
  { name: "Settings", href: "/dashboard/settings", icon: Settings },
]

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { user, logout } = useAuth()
  const pathname = usePathname()

  return (
    <div className="min-h-screen bg-intent-bg">
      {/* Mobile sidebar */}
      <div className={`fixed inset-0 z-50 lg:hidden ${sidebarOpen ? "block" : "hidden"}`}>
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setSidebarOpen(false)} />
        <div className="fixed inset-y-0 left-0 w-64 bg-intent-surface border-r border-white/10 p-4">
          <div className="flex items-center gap-2 mb-8">
            <Shield className="w-6 h-6 text-cyan-400" />
            <span className="font-bold text-lg">IntentLock</span>
          </div>
          <nav className="space-y-1">
            {navigation.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  pathname === item.href
                    ? "bg-cyan-500/10 text-cyan-400"
                    : "text-intent-muted hover:text-intent-text hover:bg-white/5"
                }`}
                onClick={() => setSidebarOpen(false)}
              >
                <item.icon className="w-4 h-4" />
                {item.name}
              </Link>
            ))}
          </nav>
        </div>
      </div>

      <div className="flex">
        {/* Desktop sidebar */}
        <aside className="hidden lg:flex fixed inset-y-0 left-0 w-64 flex-col bg-intent-surface border-r border-white/10">
          <div className="p-4">
            <Link href="/dashboard" className="flex items-center gap-2">
              <Shield className="w-6 h-6 text-cyan-400" />
              <span className="font-bold text-lg">IntentLock</span>
            </Link>
          </div>
          <nav className="flex-1 px-3 space-y-1">
            {navigation.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  pathname === item.href
                    ? "bg-cyan-500/10 text-cyan-400"
                    : "text-intent-muted hover:text-intent-text hover:bg-white/5"
                }`}
              >
                <item.icon className="w-4 h-4" />
                {item.name}
              </Link>
            ))}
          </nav>
          <div className="p-4 border-t border-white/10">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-8 h-8 rounded-full bg-cyan-500/20 flex items-center justify-center text-cyan-400 text-sm font-medium">
                {user?.email?.[0]?.toUpperCase() || "U"}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{user?.email}</p>
                <p className="text-xs text-intent-muted capitalize">{user?.role}</p>
              </div>
            </div>
            <button
              onClick={logout}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-intent-muted hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
              Sign out
            </button>
          </div>
        </aside>

        {/* Main content */}
        <div className="flex-1 lg:ml-64">
          <header className="sticky top-0 z-30 bg-intent-bg/80 backdrop-blur-xl border-b border-white/10">
            <div className="flex items-center justify-between px-6 py-4">
              <div className="flex items-center gap-4">
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="lg:hidden p-2 rounded-lg hover:bg-white/5"
                >
                  <Menu className="w-5 h-5" />
                </button>
                <h1 className="text-lg font-semibold">{navigation.find((n) => n.href === pathname)?.name || "Dashboard"}</h1>
              </div>
              <div className="flex items-center gap-3">
                <button className="p-2 rounded-lg hover:bg-white/5 text-intent-muted">
                  <Search className="w-4 h-4" />
                </button>
                <button className="p-2 rounded-lg hover:bg-white/5 text-intent-muted relative">
                  <Bell className="w-4 h-4" />
                  <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-cyan-400 rounded-full" />
                </button>
              </div>
            </div>
          </header>
          <main className="p-6">
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
