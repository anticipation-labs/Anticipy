// Anthropic Computer Use — canvas-app fallback (Google Sheets, Google
// Docs canvas, Figma). Per correction #2 (2026-05-13), the Mac executor
// app calls the Anthropic Computer Use API DIRECTLY — Claude Code is the
// dev tool, not the production runtime.
//
// Wires the screenshot + pixel-action loop:
//   1. capture screenshot of the active tab via CDP
//   2. POST to /v1/messages with computer-use tool_use enabled
//   3. apply Anthropic's returned tool_use actions (click/type) via CDP
//   4. loop until done, max N steps

const Anthropic = require('@anthropic-ai/sdk');

const DEFAULT_MODEL = 'claude-opus-4-7';
const DEFAULT_MAX_STEPS = 12;

class AnthropicComputerUse {
  constructor({ apiKey, model = DEFAULT_MODEL } = {}) {
    if (!apiKey) {
      throw new Error('ANTHROPIC_API_KEY required for canvas fallback');
    }
    this.client = new Anthropic({ apiKey });
    this.model = model;
  }

  // Run a single canvas-fallback step. Returns the assistant's tool_use
  // commands for the executor to apply via CDP. The executor is
  // responsible for the screenshot capture loop.
  async nextAction({ screenshotBase64, taskGoal, history = [] }) {
    const msg = await this.client.messages.create({
      model: this.model,
      max_tokens: 1024,
      system:
        'You are operating a canvas-rendered web app on the user’s behalf. ' +
        'Issue ONE tool_use command per turn (click, type, key, scroll). ' +
        'When the goal is achieved, return text describing the verified state.',
      tools: [
        {
          type: 'computer_20241022',
          name: 'computer',
          display_width_px: 1440,
          display_height_px: 900,
        },
      ],
      messages: [
        ...history,
        {
          role: 'user',
          content: [
            { type: 'text', text: `GOAL: ${taskGoal}` },
            {
              type: 'image',
              source: { type: 'base64', media_type: 'image/png', data: screenshotBase64 },
            },
          ],
        },
      ],
    });
    return msg.content;
  }
}

module.exports = { AnthropicComputerUse };
