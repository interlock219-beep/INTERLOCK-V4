"use client"

import { motion } from "framer-motion"
import { AlertCircle, RefreshCw, Users, GitMerge, Clock } from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface Limitation {
  title: string
  description: string
  icon: ElementType
}

const limitations: Limitation[] = [
  {
    title: "Not every mutation is reversible",
    description:
      "External side effects — sent messages, delivered webhooks, third-party writes — have no compensating adapter and are classified irreversible or unknown.",
    icon: RefreshCw,
  },
  {
    title: "Compensation depends on preconditions",
    description:
      "A compensatable action only executes if the resource matches its expected before-state; drift or a missing resource blocks it.",
    icon: Clock,
  },
  {
    title: "Conflicts are surfaced, not overwritten",
    description:
      "When a human or another agent changed the same resource, recovery is blocked rather than rolled back against the clock.",
    icon: GitMerge,
  },
  {
    title: "Some actions need a human",
    description:
      "Manually recoverable actions carry evidence and a recommended operation, but a trained responder must execute them.",
    icon: Users,
  },
  {
    title: "Success requires independent verification",
    description:
      "A recovery plan is reported as succeeded only after a verification pass confirms the actual state matches the expected recovered state.",
    icon: AlertCircle,
  },
]

export function HonestLimitationsSection() {
  return (
    <section id="limitations" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Honest boundaries"
          title="Recovery works by being honest about where it stops."
          description="Interlock is built for the actions it can recover, and explicit about the ones it cannot."
          align="center"
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto">
          {limitations.map((l, i) => (
            <motion.div
              key={l.title}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: i * 0.07 }}
              className={cn(
                "rounded-2xl border border-white/5 bg-white/[0.03] p-6 md:p-7",
                "flex items-start gap-4",
              )}
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-400">
                <l.icon className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-lg font-semibold tracking-tight mb-1">{l.title}</h3>
                <p className="text-sm text-intent-muted leading-relaxed">{l.description}</p>
              </div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.5 }}
          className="mt-16 rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6 md:p-8 max-w-4xl mx-auto"
        >
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400" />
            <p className="text-sm text-amber-200/85 leading-relaxed">
              Interlock does not carry security or compliance certifications.
              It does not claim independent penetration testing by a qualified
              firm, and SSO, OIDC, SAML, and MFA are integration stubs rather
              than production identity providers. These boundaries are surfaced
              deliberately so operators can size real controls around them.
            </p>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
