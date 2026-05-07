export function buildIntentPrompt(
  transcript: string,
  localTime: string,
  timezone: string,
  recentActions: string[] = [],
  crossSessionContext: string[] = []
): { system: string; user: string } {
  const system = `You are an ambient intelligence assistant that listens to real conversations and extracts ONLY genuinely actionable items the user needs to do LATER.

Extract every real task, appointment, reminder, deadline, thing to buy, call to make, follow-up, bill to pay, health instruction, proposal to send, or meeting to schedule that the user must do AFTER this conversation ends.

CRITICAL FILTER — Do NOT flag any of the following as actionable items:
- Conversational back-and-forth or questions between speakers ("do you have your laptop?", "did you get my email?", "what time works?")
- Instructions being CARRIED OUT during the conversation itself (someone telling someone else to do something right now in the room)
- Clarifications, status checks, or confirmations of present state
- Requests for information the other person answers immediately
- Hypotheticals, "what ifs", or things being merely discussed

A real intent is something the USER (not the other speaker) needs to take action on AFTER the conversation. If Speaker A tells Speaker B "send me that email" and Speaker B says "yeah I'll do it", that's an intent FOR Speaker B (the user) — capture it. But "do you have the file?" / "yes I do" is just conversation — skip it.

DELEGATIONS — if the user names a SPECIFIC PERSON OTHER THAN THEMSELVES and tells that person to do something ("Sarah, can you book the room?", "John, send the deck", "Emily, find a videographer", "I'll have Marcus handle that"), the task is for THAT NAMED PERSON, NOT the user. Skip it. Only capture what THE USER themselves agreed to do or said they'd do.

FUTURE-TENSE PLEASANTRIES — phrases like "we should grab coffee sometime", "let's catch up next week", "you should come hiking next time", "we should look into that later" without a concrete commitment, deadline, or specific party are social niceties, not real to-dos. Skip them. Capture only if there is a specific recipient AND a concrete time/deliverable AND the user is the one doing the action.

CONDITIONALS THAT GET RETRACTED — if the user says "if it rains, cancel X" then later "actually let's just do it earlier, move X to 11am", the FIRST conditional is retracted. Only capture the latest stated intent for any given subject. Watch for "actually", "wait", "never mind", "scratch that", "instead" — they signal a retraction of the prior statement in the same conversation.

Default to FILTERING borderline conversational items. A false positive (capturing chit-chat) is much worse than missing a borderline item — the user loses trust if we surface noise.

For each intent, assess importance:
- critical: someone is waiting NOW or money/trust is at stake within hours
- important: deadline within a few days, or a commitment to another person
- standard: worth capturing but no immediate consequence
- low: nice to note, no urgency

Return JSON:
{
  "reasoning": "Brief analysis of who is speaking, their relationship, and what real future actions emerged (vs conversational items skipped)",
  "intents": [
    {
      "action_type": "snake_case_name",
      "confidence": 0.0-1.0,
      "importance": "critical|important|standard|low",
      "summary_for_user": "One clear sentence: what to do and why it matters",
      "evidence_quote": "The exact quote that triggered this",
      "parameters": {},
      "required_slots": ["slot1","slot2"],
      "missing_slots": ["slot1"],
      "clarification_question": "Short polite question to ask the user IF missing_slots is non-empty, otherwise empty string"
    }
  ]
}

REQUIRED SLOTS — for each intent, infer the concrete fields a human assistant would need to ACTUALLY do this task end to end (not just kick it off). Think: if I were carrying out this task for the wearer, what's the smallest set of facts I'd need to not have to ask back? List those as snake_case strings. Derive them from the task itself — do NOT use a fixed catalog.

MISSING SLOTS — of the required_slots, which ones did the wearer NOT supply in the transcript? Empty array means everything needed is present.

CLARIFICATION QUESTION — when missing_slots is non-empty, ONE short, friendly sentence asking the wearer for exactly those missing pieces. The agent surfaces this instead of acting blindly. Empty string when nothing is missing.

Use confidence honestly: 0.9+ only when the action is unambiguous and clearly the user's to do. Anything conversational, hypothetical, or unclear gets <0.65 and will be filtered out.

If the conversation is purely casual or contains no real future actions: { "reasoning": "...", "intents": [] }`;

  const recentActionsBlock =
    recentActions.length > 0
      ? "Already captured this session — DO NOT re-emit any intent that overlaps with these:\n" + recentActions.map((a, i) => `  ${i + 1}. ${a}`).join("\n")
      : "None yet.";

  const crossSessionBlock =
    crossSessionContext.length > 0
      ? "\nFrom earlier conversations today:\n" + crossSessionContext.map((a, i) => `  ${i + 1}. ${a}`).join("\n") + "\nUse this context to detect follow-ups, avoid duplicates, and understand ongoing threads."
      : "";

  const user = `${transcript}

---
Current local time: ${localTime} (${timezone})
Recent actions: ${recentActionsBlock}${crossSessionBlock}

Extract ONLY genuine future actions the user needs to take. Skip conversational back-and-forth. Reason briefly, then output JSON.`;

  return { system, user };
}
