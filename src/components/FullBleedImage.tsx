"use client";

import { useRef, useEffect } from "react";
import Image from "next/image";
import { motion } from "motion/react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { ease } from "@/lib/animation";

gsap.registerPlugin(ScrollTrigger);

interface FullBleedImageProps {
  src: string;
  alt: string;
  overlayText?: string;
  ledPosition?: { top: string; left: string };
  parallaxSpeed?: number;
}

export function FullBleedImage({
  src,
  alt,
  overlayText,
  ledPosition,
  parallaxSpeed = 0.85,
}: FullBleedImageProps) {
  const sectionRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      if (!imageRef.current || !sectionRef.current) return;

      const offset = (1 - parallaxSpeed) * 100;
      gsap.fromTo(
        imageRef.current,
        { y: offset },
        {
          y: -offset,
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        }
      );
    });

    return () => ctx.revert();
  }, [parallaxSpeed]);

  return (
    <section
      ref={sectionRef}
      className="section-dark w-full overflow-hidden relative"
    >
      <div ref={imageRef} className="parallax-image">
        <Image
          src={src}
          alt={alt}
          width={1408}
          height={768}
          className="w-full h-auto object-cover"
          loading="lazy"
        />
      </div>

      {/* LED glow overlay */}
      {ledPosition && (
        <div
          className="absolute led-pulse pointer-events-none"
          style={{
            top: ledPosition.top,
            left: ledPosition.left,
            width: "40px",
            height: "40px",
            borderRadius: "50%",
            background:
              "radial-gradient(circle, rgba(255,240,220,0.6) 0%, rgba(255,240,220,0) 70%)",
            transform: "translate(-50%, -50%)",
          }}
        />
      )}

      {/* Overlay text */}
      {overlayText && (
        <div className="absolute bottom-0 left-0 right-0 p-8 md:p-16">
          <motion.p
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: ease }}
            viewport={{ once: true }}
            className="font-serif text-[clamp(18px,3vw,24px)] text-[var(--text-on-dark)] max-w-2xl"
          >
            {overlayText}
          </motion.p>
        </div>
      )}
    </section>
  );
}
