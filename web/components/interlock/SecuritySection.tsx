"use client"

import { motion } from "framer-motion"
import {
  KeyRound,
  Shield,
  Users,
  Timer,
  PauseOctagon,
  RefreshCw,
  SearchCheck,
  LockKeyhole,
  AlertCircle,
} from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface Control {
  label: string
  description: string
  icon: ElementType
}

const controls: Control[] = [
  {
    label: "Default-deny authorization",
    description:
      "ALLOW / DENY / REQUIRE_HITL decisions evaluated per service, action, and resource with configurable restrictions.",
    icon: Shield,
  },
  {
    label: "Tenant isolation",
    description:
      "Every record carries a tenant_id and is filtered at the query layer; cross-tenant access is denied and tested.",
    icon: Users,
  },
  {
    label: "Single-use execution tokens",
    description:
      "Ed25519 JWTs consumed exactly once via atomic nonce; a replay is rejected.",
    icon: KeyRound,
  },
  {
    label: "Fail-closed nonce",
    description:
      "In production, unavailable nonce storage denies execution rather than permitting it.",
    icon: LockKeyhole,
  },
  {
    label: "Approval policies",
    description:
      "Recovery plans require single, dual, or M-of-N approval before execution.",
    icon: Timer,
  },
  {
    label: "Containment",
    description:
      "Agents are quarantined and authority revoked across the delegation chain; sessions are frozen.",
    icon: PauseOctagon,
  },
  {
    label: "Idempotency",
    description:
      "Re-executing a completed recovery step returns the prior result without re-applying the mutation.",
    icon: RefreshCw,
  },
  {
    label: "Independent verification",
    description:
      "A verification pass compares actual state to expected state before success is reported.",
    icon: SearchCheck,
  },
]

const notClaimed = [
  "No SOC 2, HIPAA, PCI-DSS, or other regulatory compliance certification.",
  "No independent penetration test by a qualified security firm.",
  "SSO, OIDC, SAML, MFA, and SCIM are adapter stubs, not production integrations.",
  "Testing evidence is not equivalent to certification.",
]

export function SecuritySection() {
  return (
    <section id="security" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Security model"
          title="Fail closed by design."
          description="Interlock denies by default and never claims a secure state without independent verification of the resulting system state."
          align="center"
        />

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-20">
          {controls.map((c, i) => (
            <motion.div
              key={c.label}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.05 }}
              className="rounded-2xl border border-white/5 bg-white/[0.03] p-6"
            >
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-white/5 bg-white/[0.03] text-emerald-400">
                <c.icon className="h-5 w-5" />
              </div>
              <h3 className="text-lg font-semibold tracking-tight mb-1">{c.label}</h3>
              <p className="text-sm text-intent-muted leading-relaxed">{c.description}</p>
            </motion.div>
          ))}
        </div>

        <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.3 }}
          className={cn(
            "rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6 md:p-8",
          )}
        >
          <div className="flex items-start gap-3 mb-4">
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400" />
            <h3 className="text-lg font-semibold tracking-tight">What is not claimed</h3>
          </div>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {notClaimed.map((item) => (
              <li
                key={item}
                className="flex items-start gap-2 text-sm text-amber-300/80 leading-relaxed"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-400/70" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </motion.div>
      </div>
    </section>
  )
}
