"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { motion } from "framer-motion"
import { Shield, Check, ArrowRight, Loader2 } from "lucide-react"
import { useAuth } from "@/components/AuthProvider"

const STEPS = [
  {
    title: "Your workspace is ready",
    description: "We have created your personal IntentLock workspace with a default policy and API key.",
  },
  {
    title: "Create your first agent",
    description: "Register an AI agent to start evaluating its tool actions through IntentLock.",
  },
  {
    title: "Define a policy rule",
    description: "Configure which actions require approval and which are automatically allowed or blocked.",
  },
  {
    title: "Run your first verification",
    description: "Send an intent verification request and see IntentLock evaluate it in real time.",
  },
]

export default function OnboardingPage() {
  const [step, setStep] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const { user, isLoading: authLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login")
    }
  }, [user, authLoading, router])

  const handleNext = async () => {
    if (step < STEPS.length - 1) {
      setStep(step + 1)
    } else {
      setIsLoading(true)
      await new Promise((resolve) => setTimeout(resolve, 800))
      router.push("/dashboard")
    }
  }

  if (authLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="loader" />
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-2xl"
      >
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass-panel mb-6">
            <Shield className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-medium tracking-widest uppercase text-cyan-300">
              Getting Started
            </span>
          </div>
          <h1 className="text-3xl font-bold mb-2">{STEPS[step].title}</h1>
          <p className="text-intent-muted">{STEPS[step].description}</p>
        </div>

        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div key={i} className="flex items-center gap-2">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                  i <= step ? "bg-cyan-500 text-black" : "bg-white/10 text-intent-muted"
                }`}
              >
                {i < step ? <Check className="w-4 h-4" /> : i + 1}
              </div>
              {i < STEPS.length - 1 && (
                <div className={`w-12 h-0.5 ${i < step ? "bg-cyan-500" : "bg-white/10"}`} />
              )}
            </div>
          ))}
        </div>

        <div className="glass-panel rounded-2xl p-8">
          {step === 0 && (
            <div className="space-y-4">
              <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/20">
                <p className="text-sm text-cyan-300">Workspace created for <strong>{user.email}</strong></p>
              </div>
              <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                <p className="text-sm text-intent-muted">Tenant ID: {user.tenant_id || "assigned on first agent creation"}</p>
              </div>
            </div>
          )}
          {step === 1 && (
            <div className="space-y-4">
              <p className="text-sm text-intent-muted">Use the Python SDK to register your first agent:</p>
              <pre className="p-4 rounded-lg bg-black/40 border border-white/10 text-xs overflow-x-auto">
{`from sdk.intentlock import IntentLockGuard

client = IntentLockGuard(auth_token="${user.id}")

# Register agent
agent = client.register_agent(name="my-first-agent")`}
              </pre>
            </div>
          )}
          {step === 2 && (
            <div className="space-y-4">
              <p className="text-sm text-intent-muted">Add a policy rule in <code className="text-cyan-400">config/policies.yaml</code>:</p>
              <pre className="p-4 rounded-lg bg-black/40 border border-white/10 text-xs overflow-x-auto">
{`blocked_patterns:
  - "drop table"
  - "truncate table"
  - "delete from users"`}
              </pre>
            </div>
          )}
          {step === 3 && (
            <div className="space-y-4">
              <p className="text-sm text-intent-muted">Verify an intent through the API:</p>
              <pre className="p-4 rounded-lg bg-black/40 border border-white/10 text-xs overflow-x-auto">
{`POST /api/v1/intent/verify
Authorization: Bearer <your-token>
{
  "tool_name": "database_query",
  "tool_arguments": {"query": "SELECT * FROM users LIMIT 10"},
  "agent_id": "my-first-agent"
}`}
              </pre>
            </div>
          )}

          <div className="mt-8 flex justify-end">
            <button
              onClick={handleNext}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-semibold transition-all duration-200 hover:scale-[1.02] disabled:opacity-50"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : step === STEPS.length - 1 ? (
                "Go to Dashboard"
              ) : (
                <>
                  Next
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
