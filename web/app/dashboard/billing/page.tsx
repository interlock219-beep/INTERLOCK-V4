"use client"

import { useEffect, useState } from "react"
import { motion } from "framer-motion"
import { CreditCard, ArrowRight, Check, Loader2, ExternalLink } from "lucide-react"
import { api, type Plan, type Subscription } from "@/lib/api"
import { useAuth } from "@/components/AuthProvider"

export default function BillingPage() {
  const [plans, setPlans] = useState<Plan[]>([])
  const [subscription, setSubscription] = useState<Subscription | null>(null)
  const [publishableKey, setPublishableKey] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isUpgrading, setIsUpgrading] = useState(false)
  const [isManaging, setIsManaging] = useState(false)
  const [error, setError] = useState("")
  const { user } = useAuth()

  useEffect(() => {
    Promise.all([
      api.billing.listPlans(),
      api.billing.getSubscription(),
      api.billing.getPublishableKey().catch(() => ({ publishableKey: null })),
    ])
      .then(([plansData, sub, keyData]) => {
        setPlans(plansData)
        setSubscription(sub)
        setPublishableKey(keyData.publishableKey)
      })
      .catch(() => {})
      .finally(() => setIsLoading(false))
  }, [])

  const handleUpgrade = async (planId: string) => {
    setError("")
    setIsUpgrading(true)
    try {
      const baseUrl = typeof window !== "undefined" ? window.location.origin : "http://localhost:3000"
      const checkout = await api.billing.createCheckout({
        plan_id: planId,
        interval: "monthly",
        success_url: `${baseUrl}/dashboard/billing?success=true`,
        cancel_url: `${baseUrl}/dashboard/billing?canceled=true`,
      })
      if (checkout.url.startsWith("http")) {
        window.location.href = checkout.url
      } else {
        window.location.href = checkout.url
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Checkout failed")
    } finally {
      setIsUpgrading(false)
    }
  }

  const handleManageSubscription = async () => {
    setError("")
    setIsManaging(true)
    try {
      const portal = await api.billing.createPortal()
      window.location.href = portal.url
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unable to open billing portal")
    } finally {
      setIsManaging(false)
    }
  }

  const handleCancel = async () => {
    try {
      await api.billing.cancelSubscription()
      setSubscription((prev) => prev ? { ...prev, cancel_at_period_end: true } : null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Cancellation failed")
    }
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="loader" />
      </div>
    )
  }

  const formatPrice = (plan: Plan): string => {
    if (plan.price_monthly_cents === 0) return "$0"
    return `$${Math.round(plan.price_monthly_cents / 100)}`
  }

  const planDescription = (plan: Plan): string => {
    const agents = plan.limits.agents
    const intents = plan.limits.intents_per_day
    if (plan.tier === "enterprise") return "Custom limits, dedicated support, 99.99% SLA"
    if (agents !== undefined && intents !== undefined) {
      return `${agents} agents, ${intents.toLocaleString()} intents/day`
    }
    return "Custom plan"
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold mb-1">Billing</h1>
        <p className="text-intent-muted">Manage your subscription and payment details.</p>
      </motion.div>

      {error && (
        <div className="p-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {subscription && (
        <div className="glass-panel rounded-xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Current Subscription</h2>
              <p className="text-sm text-intent-muted capitalize">
                {subscription.plan_name} — {subscription.status}
              </p>
            </div>
            <div className="flex items-center gap-3">
              {publishableKey && (
                <button
                  onClick={handleManageSubscription}
                  disabled={isManaging}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-cyan-500/30 hover:border-cyan-400/50 text-sm text-cyan-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isManaging ? <Loader2 className="w-4 h-4 animate-spin" /> : <CreditCard className="w-4 h-4" />}
                  Manage Subscription
                </button>
              )}
              {!subscription.cancel_at_period_end && subscription.tier !== "enterprise" && (
                <button
                  onClick={handleCancel}
                  className="px-4 py-2 rounded-lg border border-white/10 hover:border-red-500/30 text-sm hover:text-red-400 transition-colors"
                >
                  Cancel Subscription
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {plans.map((plan, i) => {
          const isCurrent = subscription?.plan_name?.toLowerCase() === plan.tier
          return (
            <motion.div
              key={plan.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
              className={`glass-panel rounded-xl p-6 relative ${isCurrent ? "border-cyan-500/50" : ""}`}
            >
              {isCurrent && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 bg-cyan-500 text-black text-xs font-medium rounded-full">
                  Current Plan
                </div>
              )}
              <h3 className="text-lg font-semibold mb-1">{plan.name}</h3>
              <p className="text-3xl font-bold mb-2">{formatPrice(plan)}<span className="text-sm text-intent-muted font-normal">/mo</span></p>
              <p className="text-sm text-intent-muted mb-6">{planDescription(plan)}</p>
              {plan.tier === "enterprise" ? (
                <a
                  href="mailto:interlock677@gmail.com"
                  className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl border border-white/10 hover:border-cyan-500/30 font-medium transition-colors"
                >
                  Contact Sales
                  <ExternalLink className="w-4 h-4" />
                </a>
              ) : (
                <button
                  onClick={() => handleUpgrade(plan.id)}
                  disabled={isUpgrading || isCurrent}
                  className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold transition-all duration-200 hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isUpgrading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : isCurrent ? (
                    <>
                      <Check className="w-4 h-4" />
                      Current Plan
                    </>
                  ) : (
                    <>
                      {subscription ? "Change Plan" : "Upgrade"}
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              )}
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
