# Nobody could connect any app, and a note said that was the vendor's fault

2026-09-06. The single defect that closed every route to a connection in this
product, found by an adversarial audit and confirmed by measuring rather than
by reading.

## The claim that was in the code

`migration/workers/src/connections/provider.ts`, above `readScopes`:

> `readScopes` came back EMPTY for every toolkit measured on the detail
> endpoint too (googlecalendar, gmail, notion, slack). The live rows carry no
> `scopes` key anywhere ... So permission scopes are UNKNOWN for every app in
> production today ... That is not this function's to fix — the data is not
> merely under another key, it is absent — and adding the other key name would
> be a change that looks like a fix and moves nothing measurable.

Careful, specific, measured against four real toolkits, and wrong.

## What is actually there

    GET https://backend.composio.dev/api/v3/toolkits/gmail

    composio_managed_auth: [ { mode: "OAUTH2",
                               scopes: { available: [ ...11 scopes... ] } } ]

Measured across twelve toolkits with production's own key:

    gmail 11   googlecalendar 2   googledrive 2   slack 47   linear 5
    github 7   hubspot 33   outlook 12   googledocs 3   googlesheets 3
    notion 0   asana 0

`readScopes` walked three paths — `root.scopes`, `meta.scopes`,
`auth_config_details[].scopes` — and none of them is where the vendor puts it.

## Why it was so expensive

`permissionSentences` refuses on an empty scope list, and that refusal is
CORRECT: a permission sentence not derived from a scope is a guess about what
somebody is handing over. So the floor did exactly its job, on every app, and
the consent page could never be drawn. Both consent surfaces — the connect page
and the phone's disclosure sheet — failed closed for every toolkit in the
catalog. The product's entire purpose was unreachable, and every test was green,
because every test used fixtures with scopes in them.

**The absence of the data was written down as a fact about the vendor instead
of as a fact about where we had looked.** That sentence is the whole lesson. A
note that closes a question is worth more scrutiny than one that opens it,
because nobody re-opens a closed one.

## The second wall behind the first

With scopes read, Gmail still failed — **6 times out of 6**, deterministically,
on an 84-character line against an 80-character limit. The prompt already
states the limit. The model misses it anyway on an app with eleven scopes.

The limit did not move. 80 characters is what a person reads and an unread line
is not consent; raising the cap would have been the easy green and the wrong
one. Instead the writer now asks again, up to four times, SHOWING the model the
line it wrote and the count it broke. Asking again identically would have been
pointless — the prompt already said 80. Asking again with the failure named is
a different question.

    gmail, one attempt   0/6
    gmail, two attempts  1/6
    gmail, four attempts 6/6

And the judge is untouched: a fourth answer that is still too long is still
refused, with cause `too-long`.

## Where it stands now

Ten of twelve apps produce consent copy against the live vendor:

    gmail          "Anticipy can read and send your email to handle mail tasks for you."
    googlecalendar "Anticipy can read your calendars and everything scheduled in them."
    googledrive    "Anticipy can read, create, edit, and delete any file in your Drive."
    slack          "Anticipy can read and search your Slack messages, files, and DMs."
    github         "Anticipy can read and write your repos, issues, pull requests, and code."
    ...
    notion         refused: no-scopes
    asana          refused: no-scopes

Notion and Asana genuinely publish none. They stay refused, and that is the
floor working rather than a bug: an app whose permissions we cannot name is an
app we cannot honestly ask about.

## One more thing the new tests caught

`readScopes` accepted a whitespace-only string as a scope. It would have
reached the model as an empty bullet under "What the connection would cover",
and the model would have had to write a permission sentence about nothing —
the exact thing the no-scopes floor exists to stop, arriving through the door
marked "we have scopes". Scopes are trimmed now, and a blank one is not one.

## Still true, and not fixed here

The consent copy can now be written. It still cannot be OFFERED to anybody by
the product itself: `installNudgeWiring` has zero callers, so no ask surface in
the spec's table can fire. That is the next wall and it is a bigger one.
