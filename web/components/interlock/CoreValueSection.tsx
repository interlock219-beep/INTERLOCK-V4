"use client"

import { motion } from "framer-motion"
import {
  Bot,
  Eye,
  AlertTriangle,
  PauseCircle,
  FileCode,
  FileInput,
  GitMerge,
  SearchCheck,
} from "lucide-react"
import type { ElementType } from "react"
import { SectionHeader } from "./SectionHeader"
import { cn } from "@/lib/utils"

interface TimelineStep {
  label: string
  description: string
  icon: ElementType
  status: "neutral" | "warn" | "positive"
}

const steps: TimelineStep[] = [
  {
    label: "Agent acts",
    description: "An AI agent executes a tool action against a production system.",
    icon: Bot,
    status: "neutral",
  },
  {
    label: "Action observed",
    description: "Interlock journals the action with full attribution and recovery evidence.",
    icon: Eye,
    status: "neutral",
  },
  {
    label: "Risk detected",
    description: "Policy, reversibility, and blast-radius evaluation flags high-impact changes.",
    icon: AlertTriangle,
    status: "warn",
  },
  {
    label: "Session contained",
    description: "The agent is quarantined; authority grants are revoked and sessions are frozen.",
    icon: PauseCircle,
    status: "warn",
  },
  {
    label: "Evidence captured",
    description: "Before/after state, compensation payload, and idempotency key are recorded.",
    icon: FileCode,
    status: "neutral",
  },
  {
    label: "Recovery plan generated",
    description: "A dependency-aware plan is produced in reverse-topological order.",
    icon: FileInput,
    status: "neutral",
  },
  {
    label: "Reversible actions recovered",
    description: "Automatically reversible and compensatable actions are applied.",
    icon: SearchCheck,
    status: "positive",
  },
  {
    label: "Conflicts detected",
    description: "Concurrent mutations and drift are surfaced, never silently overwritten.",
    icon: GitMerge,
    status: "warn",
  },
  {
    label: "Result independently verified",
    description:
      "A verification pass compares actual state against the expected recovered state before any success is reported.",
    icon: SearchCheck,
    status: "positive",
  },
]

const statusColor: Record<TimelineStep["status"], string> = {
  neutral: "border-white/5 bg-white/[0.03] text-intent-muted",
  warn: "border-amber-500/20 bg-amber-500/10 text-amber-400",
  positive: "border-emerald-500/20 bg-emerald-500/10 text-emerald-400",
}

export function CoreValueSection() {
  return (
    <section id="incident" className="relative py-24">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-emerald-950/5 to-transparent" />

      <div className="relative mx-auto max-w-5xl px-6">
        <SectionHeader
          eyebrow="When an agent goes too far"
          title="One incident. A recorded chain of action and response."
          description="Interlock attributes every mutation to the agent that caused it, not to a clock window. That is what makes surgical recovery — and honest verification — possible."
          align="center"
        />

        <div className="relative mt-16">
          <div className="absolute left-6 top-0 bottom-0 -ml-px w-px bg-gradient-to-b from-emerald-500/30 via-emerald-500/10 to-transparent" />
          {steps.map((step, i) => (
            <motion.div
              key={step.label}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: i * 0.06 }}
              className="relative mb-12 last:mb-0"
            >
              <div className="flex items-start gap-5">
                <div
                  className={cn(
                    "relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border",
                    "transition-transform",
                    statusColor[step.status],
                  )}
                >
                  <step.icon className="h-5 w-5" />
                </div>
                <div className="pt-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium tracking-widest uppercase text-emerald-300/60">
                      {i + 1} / {steps.length}
                    </span>
                    <span className="text-sm font-semibold text-intent-text">
                      {step.label}
                    </span>
                  </div>
                  <p className="mt-1 max-w-md text-sm text-intent-muted leading-relaxed">
                    {step.description}
                  </p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
