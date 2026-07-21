# Proof: real multi-step navigation + form filling (not just opening sites)

Agent: browser-use + DeepSeek V3.2 via OpenRouter (your key). One
natural-language goal, zero scripted steps. 6 pages, 2 forms, autonomous.

## What it did, in order
1. Opened saucedemo.com, **typed** username + password, clicked Login.
2. On the inventory page, found and **clicked Add to cart** on two specific
   products (Backpack, Bike Light).

![cart with both items](/home/ubuntu/screenshots/ss_9f9bd7ff.png)

3. Opened the cart, clicked **Checkout**, landed on the information form:

![checkout form](/home/ubuntu/screenshots/ss_a47a5b39.png)

4. **Filled the form** (Omar / Ebrahim / V6B1A1), clicked Continue.
5. On the overview page it **verified** both items and read the total:

![overview: $43.18 total](/home/ubuntu/screenshots/ss_ad61af66.png)

6. Clicked **Finish** and reported back:

![order complete](/home/ubuntu/screenshots/ss_0983040f.png)

Agent's own final report:
> "Thank you for your order! Your order has been dispatched..." —
> Order total seen on overview page: **$43.18**.

## Honesty notes
- My only intervention: dismissing Chrome's native password-manager popups
  (browser chrome, not the page — the agent can't see native dialogs).
  It's annotated in the recording.
- This is a legitimate demo store built for exactly this kind of validation —
  real DOM, real forms, real multi-page state.
