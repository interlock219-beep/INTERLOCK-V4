"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils"
import type { ReactNode } from "react"

interface RevealProps {
  children: ReactNode
  className?: string
  delay?: number
  direction?: "up" | "down" | "left" | "right" | "none"
  distance?: number
  once?: boolean
}

function getOffset(
  direction: RevealProps["direction"],
  distance: number,
): Record<string, number> {
  switch (direction) {
    case "up":
      return { y: distance }
    case "down":
      return { y: -distance }
    case "left":
      return { x: -distance }
    case "right":
      return { x: distance }
    default:
      return {}
  }
}

export function Reveal({
  children,
  className,
  delay = 0,
  direction = "up",
  distance = 20,
  once = true,
}: RevealProps) {
  const offset = getOffset(direction, distance)

  return (
    <motion.div
      initial={{ opacity: 0, ...offset }}
      whileInView={{ opacity: 1, y: 0, x: 0 }}
      viewport={{ once, amount: 0.1 }}
      transition={{ duration: 0.55, delay, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  )
}
