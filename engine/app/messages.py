"""
All user-facing messages. Zero technical terms.
Every status, error, and success message the user sees is defined here.
"""

# --- Task lifecycle ---
TASK_STARTING = "Got it — working on that now."
TASK_NAVIGATING = "Opening the website..."
TASK_READING_PAGE = "Looking at the page..."
TASK_PERFORMING_ACTION = "Working on the next step..."
TASK_TYPING = "Filling in the details..."
TASK_SCROLLING = "Scrolling to find more..."
TASK_SELECTING = "Making a selection..."
TASK_WAITING = "Waiting for the page to load..."
TASK_VERIFYING = "Checking that everything looks right..."
TASK_COMPLETE = "Done."
TASK_FAILED = "I wasn't able to finish that. {reason}"
TASK_STUCK = "I couldn't find a way forward on that one. Want to try a different approach?"

# --- Budget limits ---
BUDGET_STEPS_EXCEEDED = "I've spent enough steps on this — let me know if you'd like me to try a different approach."
BUDGET_TIME_EXCEEDED = "This took longer than I expected. Want me to try again?"
BUDGET_COST_EXCEEDED = "I've reached the limit for this task. Try simplifying the request and I'll have another go."
BUDGET_DAILY_EXCEEDED = "You've used your daily allowance. Please try again tomorrow."

# --- Confirmation ---
CONFIRM_ACTION = "I'm about to {action}. Should I go ahead?"
CONFIRM_PURCHASE = "This looks like a purchase or payment. I'll need you to confirm before I proceed."

# --- Login ---
LOGIN_NEEDED = "This site needs you to sign in. Please sign in through the browser window, then send 'continue' and I'll pick up from there."
LOGIN_DETECTED = "I noticed a sign-in page. I'll need you to sign in first."

# --- CAPTCHA ---
CAPTCHA_DETECTED = "There's a verification check on this page. Trying to handle it automatically..."
CAPTCHA_SOLVED = "Verification complete — continuing."
CAPTCHA_MANUAL = "There's a verification I can't solve on my own. Please complete it in the browser window, then send 'continue'."

# --- Safety ---
BLOCKED_ACTION = "I can't do that — it's the kind of action that should be done by you directly."
SAFETY_BLOCKED = "For safety, I'm not able to perform that action."
PASSWORD_REQUEST_BLOCKED = "I won't ask for or enter passwords. Please sign in yourself in the browser window."
FINANCIAL_TRANSACTION_BLOCKED = "I don't move money or place bids on your behalf. Please complete that step yourself."

# --- Classification ---
CHAT_RESPONSE = "{response}"
QUESTION_RESPONSE = "{answer}"
AMBIGUOUS_REQUEST = "Could you give me a bit more detail? I can browse the web and complete tasks — what would you like me to do?"

# --- Auth ---
AUTH_SIGNUP_SUCCESS = "Account created. You're all set."
AUTH_LOGIN_SUCCESS = "Signed in."
AUTH_INVALID_CREDENTIALS = "That username or password isn't right."
AUTH_USER_EXISTS = "An account with that username already exists."
AUTH_TOKEN_INVALID = "Your session has expired. Please sign in again."
AUTH_MISSING_FIELDS = "Please provide both a username and password."
AUTH_RATE_LIMITED = "Too many failed attempts. Please try again in a few minutes."
AUTH_USERNAME_INVALID = "Usernames must be 3–32 characters and use only letters, numbers, dots, hyphens, or underscores."
AUTH_PASSWORD_TOO_SHORT = "Password must be at least 8 characters."
AUTH_PASSWORD_TOO_LONG = "Password is too long."
AUTH_REQUIRED = "Please sign in to continue."

# --- Connection ---
CONNECTION_ERROR = "Something went wrong on my end. Please try again in a moment."
BROWSER_ERROR = "I had trouble loading the page. Let me try again."
SERVICE_UNAVAILABLE = "The service is temporarily unavailable. Please try again shortly."

# --- Progress ---
STEP_PROGRESS = "Step {current} — {description}"
MIDTASK_CHECK = "Checking progress so far..."
TRYING_ALTERNATIVE = "That approach didn't work — trying a different angle."

# --- Loop detection ---
LOOP_DETECTED = "I noticed I was going in circles. Trying a different approach."

# --- Task interruption ---
TASK_INTERRUPTED = "That task was interrupted. Your progress has been saved."
TASK_ALREADY_RUNNING = "I'm still working on your previous request — one moment."

# --- Input validation ---
INPUT_TOO_LONG = "That request is a bit too long. Could you shorten it?"
INPUT_INVALID = "I couldn't understand that request. Could you rephrase it?"

# --- Rate limiting ---
RATE_LIMIT_TASKS = "You've sent a lot of requests recently. Please wait a moment before trying again."
RATE_LIMIT_WS = "Slow down — you're sending messages too quickly."

# --- Login wall pause ---
LOGIN_RESUME_HINT = "Sign in in the browser window, then send 'continue' to resume."
