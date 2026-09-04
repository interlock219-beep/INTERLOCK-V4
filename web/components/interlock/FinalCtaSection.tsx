"use client"

import { motion } from "framer-motion"
import { ArrowRight, BookOpen } from "lucide-react"

export function FinalCtaSection() {
  return (
    <section
      id="demo"
      className="relative py-24 md:py-32 border-t border-white/5"
    >
      <div className="absolute inset-0 bg-[linear-gradient(rgba(16,185,129,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(16,185,129,0.03)_1px,transparent_1px)] bg-[size:60px_60px]" />
      <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-96 w-96 rounded-full bg-emerald-500/10 blur-[140px] opacity-40" />

      <div className="relative mx-auto max-w-4xl px-6 text-center">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7 }}
          className="text-3xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-balance mb-5"
        >
          When AI acts, you should have a way back.
        </motion.h2>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="mx-auto mb-10 max-w-2xl text-lg text-intent-muted leading-relaxed"
        >
          Interlock lets you build AI systems that can act boldly without giving
          up control of the systems they touch.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="flex flex-col sm:flex-row items-center justify-center gap-4"
        >
          <a
            href="/demo"
            className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-semibold transition-colors"
          >
            Request an Interlock demo
            <ArrowRight className="h-4 w-4" />
          </a>
          <a
            href="https://github.com/interlock219-beep/INTERLOCK-V4/blob/master/docs/architecture/ARCHITECTURE.md"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 w-full sm:w-auto px-8 py-4 rounded-xl border border-white/10 hover:border-emerald-500/30 text-intent-text font-medium transition-colors"
          >
            <BookOpen className="h-4 w-4" />
            Read the architecture
          </a>
        </motion.div>
      </div>
    </section>
  )
}
