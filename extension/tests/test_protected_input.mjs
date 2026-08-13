import assert from "node:assert/strict";
import { protectedInput } from "../agent_loop.js";

assert.match(protectedInput({ type: "password", attrs: "account password" }), /password field/);
assert.match(protectedInput({ type: "text", autocomplete: "cc-number" }), /payment-card field/);
assert.match(protectedInput({ type: "text", attrs: "Credit card number" }), /payment-card field/);
assert.match(protectedInput({ type: "text", attrs: "CVC security code" }), /payment-card field/);
assert.equal(protectedInput({ type: "email", attrs: "Contact email" }), null);
assert.equal(protectedInput({ type: "date", attrs: "License expiry date" }), null);
assert.equal(protectedInput({ type: "text", attrs: "Card message for recipient" }), null);

console.log("test_protected_input: password and payment-card fields fail closed; ordinary fields pass");
