"use client"

import { MotionConfig } from "framer-motion"
import { Navbar } from "@/components/interlock/Navbar"
import { HeroSection } from "@/components/interlock/HeroSection"
import { ProblemSection } from "@/components/interlock/ProblemSection"
import { CoreValueSection } from "@/components/interlock/CoreValueSection"
import { RecoveryEngineSection } from "@/components/interlock/RecoveryEngineSection"
import { ControlPlaneSection } from "@/components/interlock/ControlPlaneSection"
import { SecuritySection } from "@/components/interlock/SecuritySection"
import { ArchitectureSection } from "@/components/interlock/ArchitectureSection"
import { RecoveryTypesSection } from "@/components/interlock/RecoveryTypesSection"
import { UseCasesSection } from "@/components/interlock/UseCasesSection"
import { DeveloperSection } from "@/components/interlock/DeveloperSection"
import { HonestLimitationsSection } from "@/components/interlock/HonestLimitationsSection"
import { FinalCtaSection } from "@/components/interlock/FinalCtaSection"
import { Footer } from "@/components/interlock/Footer"

export default function InterlockMarketingPage() {
  return (
    <MotionConfig reducedMotion="user">
      <div className="min-h-screen bg-intent-bg text-intent-text antialiased">
        <Navbar />

        <main id="main-content">
          <HeroSection />

          <ProblemSection />

          <CoreValueSection />

          <RecoveryEngineSection />

          <ControlPlaneSection />

          <SecuritySection />

          <ArchitectureSection />

          <RecoveryTypesSection />

          <UseCasesSection />

          <DeveloperSection />

          <HonestLimitationsSection />

          <FinalCtaSection />
        </main>

        <Footer />
      </div>
    </MotionConfig>
  )
}
