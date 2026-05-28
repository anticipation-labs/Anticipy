"use client";

import { useRef, useEffect } from "react";
import Image from "next/image";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export function Triptych() {
  const sectionRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ctx = gsap.context(() => {
      if (!imageRef.current || !sectionRef.current) return;

      gsap.fromTo(
        imageRef.current,
        { scale: 1.0, y: 0 },
        {
          scale: 1.05,
          y: -30,
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
  }, []);

  return (
    <section ref={sectionRef} className="section-dark w-full overflow-hidden">
      <div ref={imageRef} className="parallax-image">
        <Image
          src="/images/triptych.png"
          alt="Anticipy pendant in daily life — charging, wearing, sleeping"
          width={1376}
          height={768}
          className="w-full h-auto object-cover"
          loading="lazy"
        />
      </div>
    </section>
  );
}
