"use client"

import { motion } from "framer-motion"
import {
  Code,
  Settings,
  Database,
  ShieldCheck,
  Building2,
  Server,
} from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface UseCase {
  title: string
  problem: string
  response: string
  matters: string
  icon: ElementType
}

const useCases: UseCase[] = [
  {
    title: "AI coding agents",
    problem: "An agent rewrites a config file or commits a breaking change to a repository.",
    response:
      "The filesystem and Git repository adapters capture before/after state and can revert the change with conflict and drift detection.",
    matters:
      "A single bad commit is contained to the agent's change set, not rolled back against the clock.",
    icon: Code,
  },
  {
    title: "Production operations agents",
    problem: "An agent applies configuration that breaks a service at runtime.",
    response:
      "Atomic configuration replacement and hash-based drift detection classify the change and restore the prior state.",
    matters:
      "Operations retain a verified recovery path for every mutating deployment action.",
    icon: Settings,
  },
  {
    title: "Database-changing agents",
    problem: "An agent runs a DELETE or destructive query against production data.",
    response:
      "Destructive SQL is blocked by the intent evaluator; where data was changed, the database adapter performs row-level recovery (INSERT/UPDATE/DELETE) with parameterized, foreign-key-aware, transactional compensation.",
    matters: "Data mutations are attributable and compensated, not guessed at.",
    icon: Database,
  },
  {
    title: "Security automation",
    problem: "A security agent escalates privileges or disables a guardrail automatically.",
    response:
      "High-risk actions require human-in-the-loop approval through a durable, database-backed approval queue with RBAC.",
    matters: "Escalation is gated, auditable, and survivable across restarts.",
    icon: ShieldCheck,
  },
  {
    title: "Enterprise agent platforms",
    problem: "A platform delegates authority across many agents and tenants.",
    response:
      "Authority grants form auditable delegation chains; tenant isolation, blast-radius calculation, and containment are enforced per tenant.",
    matters: "One tenant's incident cannot cross tenant or delegation boundaries.",
    icon: Building2,
  },
  {
    title: "External-system agents",
    problem: "An agent triggers an email, a webhook, or a payment outside the repository.",
    response:
      "If no recovery adapter supports the system, the action is classified as irreversible or unknown and escalated for manual resolution.",
    matters: "Interlock is honest about where automatic recovery stops.",
    icon: Server,
  },
]

export function UseCasesSection() {
  return (
    <section id="use-cases" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Use cases"
          title="Where agents act, Interlock has a recovery story."
          description="Recovery stories grounded in the adapters and signals that actually exist."
          align="center"
        />

        <div className="space-y-12">
          {useCases.map((uc, i) => (
            <motion.div
              key={uc.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              className={cn(
                "rounded-2xl border border-white/5 bg-white/[0.03] p-7 md:p-9",
                "transition-colors hover:border-emerald-500/20",
              )}
            >
              <div className="mb-6 flex items-center gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/5 bg-white/[0.03] text-emerald-400">
                  <uc.icon className="h-6 w-6" />
                </div>
                <h3 className="text-2xl font-bold tracking-tight">{uc.title}</h3>
              </div>

              <div className="grid md:grid-cols-3 gap-6">
                <div>
                  <p className="text-xs font-medium tracking-widest uppercase text-intent-muted/70 mb-2">
                    Problem
                  </p>
                  <p className="text-sm text-intent-muted leading-relaxed">{uc.problem}</p>
                </div>
                <div>
                  <p className="text-xs font-medium tracking-widest uppercase text-emerald-300/60 mb-2">
                    Interlock response
                  </p>
                  <p className="text-sm text-intent-text leading-relaxed">{uc.response}</p>
                </div>
                <div>
                  <p className="text-xs font-medium tracking-widest uppercase text-intent-muted/70 mb-2">
                    Why it matters
                  </p>
                  <p className="text-sm text-intent-muted leading-relaxed">{uc.matters}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
