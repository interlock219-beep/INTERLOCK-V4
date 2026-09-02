"use client"

import { motion } from "framer-motion"
import {
  Database,
  GitMerge,
  Wrench,
  AlertCircle,
  Ban,
  HelpCircle,
  CheckCircle2,
  ScanSearch,
} from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface Classification {
  label: string
  meaning: string
  automatic: string
  icon: ElementType
  tone: "positive" | "warn" | "destructive" | "muted"
}

const classifications: Classification[] = [
  {
    label: "Directly recovered",
    meaning:
      "A production-validated adapter reverses the change automatically (delete a row, revert a file, undo a commit).",
    automatic: "Automatic",
    icon: CheckCircle2,
    tone: "positive",
  },
  {
    label: "Compensated",
    meaning:
      "Reversible with a supported compensation operation, subject to drift and conflict preconditions holding.",
    automatic: "Conditional",
    icon: Database,
    tone: "warn",
  },
  {
    label: "Conflict",
    meaning:
      "A concurrent mutation would be overwritten by a naive rollback. The action is classified, not silently applied.",
    automatic: "Manual",
    icon: GitMerge,
    tone: "warn",
  },
  {
    label: "Manual intervention",
    meaning:
      "Interlock provides evidence and a recommended operation, but a human must execute it.",
    automatic: "Manual",
    icon: Wrench,
    tone: "warn",
  },
  {
    label: "Irreversible",
    meaning:
      "An external side effect (message sent, physical action, time-dependent effect) cannot be safely undone.",
    automatic: "None",
    icon: Ban,
    tone: "destructive",
  },
  {
    label: "Unknown",
    meaning:
      "Insufficient evidence to classify. Escalated rather than assumed safe to reverse.",
    automatic: "None",
    icon: HelpCircle,
    tone: "muted",
  },
]

const toneColor: Record<Classification["tone"], string> = {
  positive: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
  warn: "border-amber-500/20 bg-amber-500/10 text-amber-400",
  destructive: "border-red-500/20 bg-red-500/10 text-red-400",
  muted: "border-white/5 bg-white/[0.03] text-intent-muted",
}

const pipeline = [
  "Observe",
  "Attribute",
  "Discover",
  "Plan",
  "Simulate",
  "Recover",
  "Verify",
]

export function RecoveryEngineSection() {
  return (
    <section id="recovery" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-7xl px-6">
        <SectionHeader
          eyebrow="Recovery engine"
          title="Recovery without false certainty."
          description="Not every action can be simply undone. Interlock classifies each outcome, simulates a plan, executes only
          what is approvable, and verifies the resulting state before reporting success."
          align="center"
        />

        <div className="mb-4 text-center">
          <p className="text-sm font-medium tracking-widest uppercase text-intent-muted">
            Recovery outcomes
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-20">
          {classifications.map((c, i) => (
            <motion.div
              key={c.label}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.06 }}
              className={cn(
                "rounded-2xl border p-6",
                toneColor[c.tone],
              )}
            >
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-white/5 bg-white/[0.03]">
                <c.icon className="h-5 w-5" />
              </div>
              <div className="flex items-baseline justify-between gap-2">
                <h3 className="text-lg font-semibold tracking-tight">{c.label}</h3>
                <span className="text-xs font-medium tracking-widest uppercase">{c.automatic}</span>
              </div>
              <p className="mt-2 text-sm text-intent-muted leading-relaxed">{c.meaning}</p>
            </motion.div>
          ))}
        </div>

        <div className="rounded-2xl border border-white/5 bg-white/[0.03] p-8">
          <div className="mb-6 flex items-center gap-3">
            <ScanSearch className="h-5 w-5 text-emerald-400" />
            <h3 className="text-xl font-semibold tracking-tight">
              Recovery pipeline
            </h3>
          </div>

          <div className="relative">
            <div className="absolute left-6 top-0 bottom-0 -ml-px w-px bg-gradient-to-b from-emerald-500/30 to-transparent" />
            <div className="space-y-4">
              {pipeline.map((step, i) => (
                <motion.div
                  key={step}
                  initial={{ opacity: 0, x: -16 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.4, delay: i * 0.06 }}
                  className="relative flex items-center gap-4"
                >
                  <div className="relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-white/5 bg-white/[0.03] text-xs font-medium">
                    {i + 1}
                  </div>
                  <span className="text-emerald-300">{step}</span>
                </motion.div>
              ))}
            </div>
          </div>

          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.6 }}
            className="mt-8 flex items-start gap-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-4"
          >
            <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-400" />
            <p className="text-sm text-amber-300/90 leading-relaxed">
              No recovery executes without a human-approved plan unless explicitly
              configured. Success is reported only after an independent verification
              pass compares the actual state against the expected state.
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
