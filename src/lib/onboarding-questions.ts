// Shared between /api/twilio/onboarding/initial and /answer so both
// routes ask from the same question list. Phrasing matches the local
// INTERVIEW_SCRIPT closely; it is simplified for a Polly TTS voice
// that does not handle long parentheticals well.
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
