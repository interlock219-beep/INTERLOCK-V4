"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"

interface SectionHeaderProps {
  title: React.ReactNode
  description?: React.ReactNode
  eyebrow?: string
  align?: "center" | "left"
  className?: string
}

export function SectionHeader({
  title,
  description,
  eyebrow,
  align = "center",
  className,
}: SectionHeaderProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.6 }}
      className={cn(
        "mb-12 sm:mb-16",
        align === "center" ? "mx-auto max-w-3xl text-center" : "max-w-3xl",
        className,
      )}
    >
      {eyebrow && (
        <p className="text-xs font-medium tracking-widest uppercase text-emerald-400/60 mb-4">
          {eyebrow}
        </p>
      )}
      <h2
        className={cn(
          "text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight mb-5",
          "text-balance",
        )}
      >
        {title}
      </h2>
      {description && (
        <p className="text-base sm:text-lg text-intent-muted leading-relaxed text-balance">
          {description}
        </p>
      )}
    </motion.div>
  )
}
