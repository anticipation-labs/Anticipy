/**
 * Shared onboarding question list used by Twilio voice-onboarding
 * routes.
 *
 * Lives in src/lib (not under src/app/api/.../route.ts) because
 * Next.js 14 route files only allow a fixed set of named exports
 * (GET, POST, dynamic, runtime, etc.). Exporting constants from a
 * route file fails the production build with a Route-types error.
 *
 * Phrasing mirrors INTERVIEW_SCRIPT in
 * engine/app/anticipy/onboarding.py with phone-friendly wording (no
 * em-dashes, no nested parentheticals; speech-recognition friendly).
 */

export const ONBOARDING_QUESTIONS: string[] = [
  "What is your name, and your role or title?",
  "In one sentence, what do you do day to day?",
  "What time zone are you in, and what are your usual working hours?",
  "Who are the most important people around you? Your boss, your reports, key clients, your partner. Name who 'the boss' and 'us' refer to.",
  "Which three to five tools or systems do you live in every day? Email, calendar, the rest.",
  "What do you want Anticipy to do for you, and what is strictly off limits, your do not touch list?",
  "How should I reach you for non critical things versus critical things, and what are your quiet hours?",
];

export const QUESTION_TOTAL = ONBOARDING_QUESTIONS.length;
