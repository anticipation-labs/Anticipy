"use client";

import { motion } from "motion/react";
import Image from "next/image";
import { slideTransition } from "@/lib/animation";

interface ProductSplitProps {
  imageSrc: string;
  imageAlt: string;
  headline: string;
  body: string;
  body2?: string;
  imageLeft?: boolean;
  theme?: "cream" | "dark";
  id?: string;
}

export function ProductSplit({
  imageSrc,
  imageAlt,
  headline,
  body,
  body2,
  imageLeft = true,
  theme = "cream",
  id,
}: ProductSplitProps) {
  const isDark = theme === "dark";

  return (
    <section
      id={id}
      className={`${isDark ? "section-dark" : "section-cream"} py-0 overflow-hidden`}
    >
      <div
        className={`grid grid-cols-1 md:grid-cols-2 min-h-[600px] ${
          !imageLeft ? "md:[direction:rtl]" : ""
        }`}
      >
        {/* Image */}
        <motion.div
          initial={{ opacity: 0, x: imageLeft ? -60 : 60 }}
          whileInView={{ opacity: 1, x: 0 }}
          transition={slideTransition}
          viewport={{ once: true, amount: 0.3 }}
          className="relative h-[400px] md:h-auto overflow-hidden md:[direction:ltr]"
        >
          <Image
            src={imageSrc}
            alt={imageAlt}
            fill
            className="object-cover"
            loading="lazy"
          />
        </motion.div>

        {/* Text */}
        <div
          className={`flex flex-col justify-center px-8 md:px-16 lg:px-20 py-16 md:py-20 md:[direction:ltr]`}
        >
          <motion.h2
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...slideTransition, delay: 0.1 }}
            viewport={{ once: true, amount: 0.3 }}
            className="font-serif text-section tracking-tight-section leading-[1.15] mb-6"
            style={{
              color: isDark ? "var(--text-on-dark)" : "var(--text-on-light)",
            }}
            dangerouslySetInnerHTML={{ __html: headline }}
          />

          <motion.p
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ ...slideTransition, delay: 0.25 }}
            viewport={{ once: true, amount: 0.3 }}
            className="text-[17px] leading-[1.7] font-light mb-4"
            style={{
              color: isDark
                ? "var(--text-on-dark-muted)"
                : "var(--text-on-light-muted)",
            }}
          >
            {body}
          </motion.p>

          {body2 && (
            <motion.p
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ ...slideTransition, delay: 0.4 }}
              viewport={{ once: true, amount: 0.3 }}
              className="text-[17px] leading-[1.7] font-light"
              style={{
                color: isDark
                  ? "var(--text-on-dark-muted)"
                  : "var(--text-on-light-muted)",
              }}
            >
              {body2}
            </motion.p>
          )}
        </div>
      </div>
    </section>
  );
}
