"use client"

import { motion } from "framer-motion"
import {
  RotateCw,
  ShieldCheck,
  Ban,
  UserCheck,
  AlertCircle,
} from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface RecoveryType {
  label: string

  description: string

  automatic: string
  icon: ElementType
  tone: "positive" | "warn" | "destructive"
}

const types: RecoveryType[] = [
  {
    label: "REVERSIBLE",
    description:
      "A production-validated adapter can restore the prior state: delete a created record, revert a file, undo a commit.",
    automatic: "Recovered automatically",
    icon: RotateCw,
    tone: "positive",
  },
  {
    label: "CONDITIONAL",
    description:
      "Reversible only if preconditions hold: no drift, no concurrent mutation, and the compensation is validated against the expected state.",
    automatic: "Recovered if preconditions pass",
    icon: ShieldCheck,
    tone: "warn",
  },
  {
    label: "IRREVERSIBLE",
    description:
      "An external side effect (message delivered, physical action, time-dependent effect) cannot be safely undone.",
    automatic: "Not recoverable",
    icon: Ban,
    tone: "destructive",
  },
  {
    label: "HUMAN REQUIRED",
    description:
      "Interlock provides evidence and a recommended operation, but a trained responder must decide and act.",
    automatic: "Requires human intervention",
    icon: UserCheck,
    tone: "warn",
  },
]

const toneColor: Record<RecoveryType["tone"], string> = {
  positive: "border-emerald-500/20 bg-emerald-500/10",
  warn: "border-amber-500/20 bg-amber-500/10",
  destructive: "border-red-500/20 bg-red-500/10",
}

const toneText: Record<RecoveryType["tone"], string> = {
  positive: "text-emerald-400",
  warn: "text-amber-400",
  destructive: "text-red-400",
}

export function RecoveryTypesSection() {
  return (
    <section id="recovery-types" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Recovery classification"
          title="Four outcomes. Two of them are not automatic."
          description="Not every action is reversible, and Interlock does not pretend otherwise."
          align="center"
        />

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
          {types.map((t, i) => (
            <motion.div
              key={t.label}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              className={cn(
                "rounded-2xl border p-7 text-center",
                toneColor[t.tone],
              )}
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl border border-white/5 bg-white/[0.03] mx-auto">
                <t.icon className={cn("h-6 w-6", toneText[t.tone])} />
              </div>
              <h3 className="text-xl font-bold tracking-tight mb-3">{t.label}</h3>
              <p className="text-xs font-medium tracking-widest uppercase text-intent-muted/70 mb-3">
                {t.automatic}
              </p>
              <p className="text-sm text-intent-muted leading-relaxed">{t.description}</p>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.5 }}
          className="mt-16 flex items-start gap-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-6 md:p-8"
        >
          <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-300" />
          <p className="text-sm text-emerald-200/80 leading-relaxed">
            Interlock reports what it recovered and what it could not. A
            successful recovery is never claimed unless the resulting state is
            independently verified against the expected recovered state.
          </p>
        </motion.div>
      </div>
    </section>
  )
}
