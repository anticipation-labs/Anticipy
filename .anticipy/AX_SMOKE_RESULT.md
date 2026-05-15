# AX architecture smoke gate

Real artifacts from real runs. Each block is one run.

## Smoke run 2026-05-15 10:12:03

- Passed: False
- Wall latency: 32.54s
- Returned ref: None
- Resolved text: ''
- Raw model output: ''

## Smoke run 2026-05-15 10:13:49

- Passed: False
- Wall latency: 55.49s
- Returned ref: @e11
- Resolved text: ''
- Raw model output: 'Okay, let me try to figure out where the Compose button is in this HTML structure. The user is asking for the ref of the Compose button, so I need to look through the provided elements carefully.\n\nFirst, I\'ll start by scanning through the elements listed. The main content area has several rows representing emails or messages, each with gridcells and various references. There\'s also a side panel with links for storage, terms, privacy, etc. Then there\'s a tablist with tabs for Calendar, Keep, Tasks, Contacts, and Get Add-ons. A button to hide the side panel is present, and an iframe for an Information Card.\n\nNow, the Compose button is typically found in the header or side panel of an email client. Since the user mentioned "Find the Compose button," I should check if any of the existing elements might be it. Looking at the elements provided, there\'s a button labeled "Hide side panel" with ref e11. But that\'s for hiding the side panel, not composing a new email.\n\nThe tablist includes tabs like Calendar, Keep, Tasks, etc., but none of those are the Compose button. The links at the bottom (Terms, Privacy, etc.) are also not related. The iframe is for an information card, so probably not.\n\nWait, maybe the Compose button is part of the side panel that\'s currently visible. The user didn\'t mention it being hidden, so perhaps it\'s in the main area. However, looking at the rows, they all seem to be message entries. The Compose button is usually a separate element, maybe in the header or a toolbar.\n\nSince none of the listed elements directly mention a Compose button, perhaps it\'s part of the iframe? The iframe has ref e2, but that\'s the Information Card. Alternatively, maybe the Compose button is in the tab content'

## Smoke run 2026-05-15 16:20:56

- Passed: False
- Wall latency: 33.54s
- Returned ref: None
- Resolved text: ''
- Raw model output: 'Okay, let\'s see. The user is asking to find the Compose button in the given HTML structure and reply with the reference in the form @eN. \n\nFirst, I need to look through the provided HTML elements to see if there\'s a button labeled "Compose" or any element that serves as'

## Smoke run 2026-05-15 16:22:31

- Passed: True
- Wall latency: 32.33s
- Returned ref: @e2
- Resolved text: 'Compose'
- Raw model output: '@e2'
