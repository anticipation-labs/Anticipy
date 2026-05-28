// Shared easing curve — smooth deceleration (similar to power3.out)
export const ease = [0.22, 1, 0.36, 1] as [number, number, number, number];

export const defaultTransition = {
  duration: 0.8,
  ease,
};

export const slideTransition = {
  duration: 1,
  ease,
};
