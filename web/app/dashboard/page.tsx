"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { Shield, ArrowRight, ExternalLink, Activity, CreditCard, Users } from "lucide-react"
import Link from "next/link"
import { api, type ActivityEvent, type BillingOverview } from "@/lib/api"
import { useAuth } from "@/components/AuthProvider"

export default function DashboardPage() {
  const [overview, setOverview] = useState<BillingOverview | null>(null)
  const [activities, setActivities] = useState<ActivityEvent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const { user } = useAuth()

  useEffect(() => {
    let active = true
    Promise.all([
      api.billing.getOverview().then(setOverview).catch(() => {}),
      api.activity.list().then((events) => active && setActivities(events)).catch(() => {}),
    ])
      .finally(() => active && setIsLoading(false))
    return () => {
      active = false
    }
  }, [])

  const plan = overview?.plan
  const subscription = overview?.subscription
  const usage = overview?.usage || []

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold mb-1">Welcome back, {user?.email?.split("@")[0]}</h1>
        <p className="text-intent-muted">Here is what is happening with your workspace.</p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-panel rounded-xl p-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
              <Shield className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <p className="text-sm text-intent-muted">Current Plan</p>
              <p className="font-semibold">{plan?.name || subscription?.plan_name || "Free"}</p>
            </div>
          </div>
          <p className="text-xs text-intent-muted capitalize">{subscription?.status || "Active"}</p>
        </div>
        <div className="glass-panel rounded-xl p-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
              <Activity className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <p className="text-sm text-intent-muted">Usage This Period</p>
              <p className="font-semibold">{usage.length > 0 ? `${usage[0].current} / ${usage[0].limit}` : "0"}</p>
            </div>
          </div>
          <p className="text-xs text-intent-muted">Resets {subscription?.current_period_end ? new Date(subscription.current_period_end).toLocaleDateString() : "daily"}</p>
        </div>
        <div className="glass-panel rounded-xl p-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
              <Users className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <p className="text-sm text-intent-muted">Agents</p>
              <p className="font-semibold">No active agents</p>
            </div>
          </div>
          <p className="text-xs text-intent-muted">Register your first agent to get started</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <Link href="/dashboard/usage" className="flex items-center justify-between p-4 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
              <div className="flex items-center gap-3">
                <Activity className="w-4 h-4 text-cyan-400" />
                <span className="text-sm">View usage metrics</span>
              </div>
              <ArrowRight className="w-4 h-4 text-intent-muted" />
            </Link>
            <Link href="/dashboard/billing" className="flex items-center justify-between p-4 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
              <div className="flex items-center gap-3">
                <CreditCard className="w-4 h-4 text-cyan-400" />
                <span className="text-sm">Manage billing</span>
              </div>
              <ArrowRight className="w-4 h-4 text-intent-muted" />
            </Link>
            <Link href="/dashboard/api-keys" className="flex items-center justify-between p-4 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
              <div className="flex items-center gap-3">
                <Shield className="w-4 h-4 text-cyan-400" />
                <span className="text-sm">Manage API keys</span>
              </div>
              <ArrowRight className="w-4 h-4 text-intent-muted" />
            </Link>
          </div>
        </div>

        <div className="glass-panel rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4">Recent Activity</h2>
          {activities.length === 0 ? (
            <div className="flex flex-col items-center justify-center text-center py-10">
              <Activity className="w-8 h-8 text-intent-muted mb-3" />
              <p className="text-sm text-intent-muted">No activity yet</p>
              <p className="text-xs text-intent-muted mt-1">
                Events like logins and plan changes will appear here.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {activities.map((event, index) => (
                <div key={index} className="flex items-center gap-3 p-3 rounded-lg bg-white/5">
                  <div className="w-2 h-2 rounded-full bg-cyan-400" />
                  <div className="flex-1">
                    <p className="text-sm capitalize">{event.event_type.replace(/_/g, " ")}</p>
                    <p className="text-xs text-intent-muted">
                      {new Date(event.timestamp).toLocaleString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
