"use client"

import { motion } from "framer-motion"
import { ArrowRight, ShieldCheck } from "lucide-react"
import { Velaris } from "@/components/ui/velaris"
import { cn } from "@/lib/utils"

export function HeroSection() {
  const headline = {
    initial: { opacity: 0, y: 30 },
    animate: { opacity: 1, y: 0 },
  }

  return (
    <section
      id="hero"
      className="relative flex min-h-screen flex-col items-center justify-between overflow-hidden px-6 pt-28 pb-24 sm:pt-32 sm:pb-28"
    >
      <Velaris className="absolute inset-0" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(16,185,129,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(16,185,129,0.02)_1px,transparent_1px)] bg-[size:60px_60px]" />

      <div className="relative z-10 flex w-full max-w-4xl flex-1 flex-col items-center justify-center text-center">
        <motion.div
          initial={headline.initial}
          animate={headline.animate}
          transition={{ duration: 0.8 }}
          className="mb-5 flex items-center justify-center gap-3"
        >
          <ShieldCheck className="w-5 h-5 text-emerald-400/60" />
          <span className="text-xs font-medium tracking-widest uppercase text-emerald-300/60">
            Control plane for AI agents
          </span>
        </motion.div>

        <motion.h1
          {...headline}
          transition={{ duration: 0.8, delay: 0.1 }}
          className="text-5xl sm:text-6xl md:text-8xl font-extrabold tracking-tight leading-[1.05] mb-6"
        >
          UNDO THE AGENT.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.25 }}
          className={cn(
            "mx-auto mb-10 max-w-2xl text-lg md:text-xl text-intent-muted",
            "leading-relaxed",
          )}
        >
          AI agents can change production systems. Interlock gives teams a control
          plane to authorize, observe, contain, recover, and verify those actions.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.4 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <a
            href="mailto:interlock677@gmail.com"
            className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold transition-colors"
          >
            Request a Demo
          </a>
          <a
            href="#recovery"
            className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-4 rounded-xl border border-white/10 hover:border-emerald-500/30 text-intent-text font-medium transition-colors"
          >
            See Recovery in Action
          </a>
        </motion.div>
      </div>

      <div className="relative z-10 mt-10 flex w-full max-w-4xl flex-col items-center gap-8">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.6 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-x-6 gap-y-3 text-xs text-intent-muted tracking-widest uppercase"
        >
          <span>Recovery-tested engine</span>
          <span className="hidden sm:block w-1 h-1 rounded-full bg-white/20" />
          <span>Fail-closed by design</span>
          <span className="hidden sm:block w-1 h-1 rounded-full bg-white/20" />
          <span>Open architecture</span>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 1 }}
          aria-hidden="true"
          className="flex flex-col items-center gap-2"
        >
          <span className="text-xs text-intent-muted tracking-widest uppercase">
            Scroll
          </span>
          <motion.div
            animate={{ y: [0, 6, 0] }}
            transition={{ duration: 1.8, repeat: Infinity }}
          >
            <ArrowRight className="w-4 h-4 rotate-90 text-intent-muted" />
          </motion.div>
        </motion.div>
      </div>

      <div className="absolute -bottom-24 left-1/2 -translate-x-1/2 w-80 h-80 bg-emerald-500/10 rounded-full blur-[120px] opacity-30" />
    </section>
  )
}
