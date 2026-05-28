"use client";

import { motion } from "motion/react";
import { ease } from "@/lib/animation";

interface NotificationCardProps {
  message: string;
  time?: string;
  delay?: number;
}

export function NotificationCard({
  message,
  time = "Just now",
  delay = 0.5,
}: NotificationCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.6,
        delay,
        ease: ease,
      }}
      viewport={{ once: true }}
      className="flex items-start gap-3 p-[14px_18px] rounded-notification"
      style={{
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        background: "rgba(255,255,255,0.12)",
        border: "1px solid rgba(255,255,255,0.15)",
      }}
    >
      {/* App icon */}
      <div
        className="flex-shrink-0 w-9 h-9 rounded-[10px] flex items-center justify-center"
        style={{ background: "var(--gold)" }}
      >
        <span className="text-[16px] font-bold" style={{ color: "var(--dark)" }}>
          A
        </span>
      </div>

      {/* Text */}
      <div className="flex-1 min-w-0">
        <p className="text-[13px] text-white leading-[1.4]">{message}</p>
        <p className="text-[11px] mt-1" style={{ color: "rgba(255,255,255,0.5)" }}>
          {time}
        </p>
      </div>
    </motion.div>
  );
}
