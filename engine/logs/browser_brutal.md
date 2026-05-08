# Browser Brutal Benchmark — Results
_Generated 2026-05-08 16:12:15 UTC_
**Total: 4/29 pass (13.8%)**  
Total fail: 24  
Avg elapsed/scenario: 21.3s  

## Per-category pass rate

| Category | Pass / Total | Pass % |
|---|---|---|
| `graceful_decline` | 3/5 | 60% |
| `long_task` | 0/5 | 0% |
| `multi_field_form` | 0/5 | 0% |
| `retry_after_fail` | 1/5 | 20% |
| `search_click_extract_chain` | 0/5 | 0% |
| `shadow_dom_heavy` | 0/4 | 0% |

## Failure breakdown (25 failures)

| Failure mode | Count |
|---|---|
| other | 17 |
| selector miss / element not found | 4 |
| missing expected substring in message | 3 |
| timeout | 1 |

## Top 5 failure traces (representative)

### 1. `shadow_dom_heavy` — Find information about the 'Modal' component in the Ionic Framework documentation and briefly describe its purpose.

- **Starting URL:** https://ionicframework.com/docs/
- **Expected:** message_contains_all on ['modal', 'dialog', 'component']
- **Final URL:** https://ionicframework.com/docs
- **Agent success?:** False
- **Steps:** 1
- **Elapsed:** 13.7s 
- **Agent message:** `Hit my AI rate limit. Give me a minute and try again.`
- **Verifier reason:** message missing required pattern 'modal': hit my ai rate limit. give me a minute and try again.

### 2. `multi_field_form` — Fill out the website feedback form with your name as 'Anticipy User', email as 'test@example.com', select 'Excellent' for overall experience, and in 'What did you like best?' write 'The clear layout and easy navigation.' Do not submit the form.

- **Starting URL:** https://docs.google.com/forms/d/e/1FAIpQLScXQ-Xw_hT5h9c_G2_g1J_Y5_Q1g_X0m_N6_oA4/viewform
- **Expected:** message_contains_all on ['filled', 'anticipy user', 'test@example.com', 'excellent', 'clear layout']
- **Final URL:** https://docs.google.com/forms/d/e/1FAIpQLScXQ-Xw_hT5h9c_G2_g1J_Y5_Q1g_X0m_N6_oA4/viewform
- **Agent success?:** False
- **Steps:** 0
- **Elapsed:** 7.6s 
- **Agent message:** `The starting page is a 'Page Not Found' error, so the form cannot be accessed.`
- **Verifier reason:** message missing required pattern 'filled': the starting page is a 'page not found' error, so the form cannot be accessed.

### 3. `shadow_dom_heavy` — Search for 'Anticipy AI' on YouTube and report the full URL of the search results page.

- **Starting URL:** https://www.youtube.com/
- **Expected:** url_contains_any on ['youtube.com/results?search_query=anticipy+ai']
- **Final URL:** https://www.youtube.com/
- **Agent success?:** False
- **Steps:** 0
- **Elapsed:** 7.7s 
- **Agent message:** `Hit my AI rate limit. Give me a minute and try again.`
- **Verifier reason:** final URL missing patterns ['youtube.com/results?search_query=anticipy+ai']: https://www.youtube.com/

### 4. `long_task` — Find the capital cities of Brazil, Canada, and Australia. Then, for each capital, find its population. Finally, tell me which of these three capital cities has the largest population.

- **Starting URL:** https://en.wikipedia.org/wiki/Main_Page
- **Expected:** message_contains_all on ['brazil', 'canada', 'australia', 'brasilia', 'ottawa', 'canberra', 'population', 'largest']
- **Final URL:** 
- **Agent success?:** False
- **Steps:** 0
- **Elapsed:** 301.3s  (TIMED OUT)
- **Agent message:** `Starting…`
- **Verifier reason:** timeout after 301.3s, 0 steps

## Detail — all failures

- **[shadow_dom_heavy]** Search for 'Anticipy AI' on YouTube and report the full URL of the search results page.  
  url=https://www.youtube.com/ success=False steps=0 t=7.7s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: final URL missing patterns ['youtube.com/results?search_query=anticipy+ai']: https://www.youtube.com/

- **[shadow_dom_heavy]** Find the documentation for the 'Alert' component on the Ionic Framework website.  
  url=https://ionicframework.com/docs/components success=False steps=4 t=28.9s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: final URL missing patterns ['api/alert', 'alert']: https://ionicframework.com/docs/components

- **[shadow_dom_heavy]** Search YouTube for 'how to make sourdough bread' and navigate to the search results page.  
  url=https://www.youtube.com/ success=False steps=0 t=10.7s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: final URL missing patterns ['search_query=how+to+make+sourdough+bread', 'search_query=how%20to%20make%20sourdough%20bread']: https://www.youtube.com/

- **[shadow_dom_heavy]** Find information about the 'Modal' component in the Ionic Framework documentation and briefly describe its purpose.  
  url=https://ionicframework.com/docs success=False steps=1 t=13.7s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing required pattern 'modal': hit my ai rate limit. give me a minute and try again.

- **[multi_field_form]** Fill out the website feedback form with your name as 'Anticipy User', email as 'test@example.com', select 'Excellent' fo  
  url=https://docs.google.com/forms/d/e/1FAIpQLScXQ-Xw_hT5h9c_G2_g1J_Y5_Q1g_X0m_N6_oA4 success=False steps=0 t=7.6s  
  msg=`The starting page is a 'Page Not Found' error, so the form cannot be accessed.`  
  reason: message missing required pattern 'filled': the starting page is a 'page not found' error, so the form cannot be accessed.

- **[multi_field_form]** Fill out the contact form on Jotform with the following details: First Name: John, Last Name: Doe, Email: john.doe@examp  
  url=https://form.jotform.com/241604169641052 success=False steps=0 t=7.6s  
  msg=`The form is not available at the provided URL. The page title is 'Jotform - Form is missing'.`  
  reason: only 0 steps taken (need ≥3)

- **[multi_field_form]** Fill out the feedback form with the name 'Anticipy User', email 'user@example.com', select 'Suggestion' for Feedback Typ  
  url=https://docs.google.com/forms/d/e/1FAIpQLSclK-P8dKzQz2Z2y0Y9J5F-q7t3q2k-y7q-z9v8 success=False steps=0 t=7.6s  
  msg=`The starting URL leads to a 'Page Not Found' error, making the form inaccessible.`  
  reason: agent reported failure: the starting url leads to a 'page not found' error, making the form inaccessible.

- **[multi_field_form]** Fill out the 'User Feedback Survey' form on Google Forms. Provide 'Anticipy User' as the name, 'test@example.com' as the  
  url=https://docs.google.com/forms/d/e/1FAIpQLSdp5Q2-G0n69V6qR6Fp_t_Q3K3J7X7C7E7F7G7H success=False steps=0 t=6.1s  
  msg=`The starting page is a 'Page Not Found' error, so the survey form cannot be accessed.`  
  reason: agent reported failure: the starting page is a 'page not found' error, so the survey form cannot be accessed.

- **[multi_field_form]** Fill out the 'Simple Survey Form' with the following details: Name as 'Anticipy User', Email as 'user@example.com', Phon  
  url=https://docs.google.com/forms/d/e/1FAIpQLSd1L-9p9v8rQ5q-3F0G5z7P2z7z2z7z2z7z2z7z success=False steps=0 t=9.1s  
  msg=`The starting page is a 'Page Not Found' error. The survey form is not available at the provided URL.`  
  reason: agent reported failure: the starting page is a 'page not found' error. the survey form is not available at the provided url.

- **[search_click_extract_chain]** Search for the height of Mount Everest and tell me its official measurement in meters.  
  url=https://duckduckgo.com/ success=False steps=0 t=10.8s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing all patterns ['8848', '8,848', '8848.86', '8,848.86', 'meters']: hit my ai rate limit. give me a minute and try again.

- **[search_click_extract_chain]** Search for the height of the Eiffel Tower and tell me the measurement.  
  url=https://www.google.com/?zx=1778256134209 success=False steps=2 t=10.7s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing all patterns ['330 meters', '330m', '324 meters', '324m', '1,083 feet', '1083 feet', '1,063 feet', '1063 feet']: hit my ai rate limit. give me a minute and try again.

- **[search_click_extract_chain]** Search for 'Berlin Wall' on Wikipedia, click the most relevant link, and tell me the year it fell.  
  url=https://en.wikipedia.org/wiki/Main_Page success=False steps=0 t=9.2s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing all patterns ['1989', 'november 9', 'nov 9', 'nineteen eighty nine']: hit my ai rate limit. give me a minute and try again.

- **[search_click_extract_chain]** Find the current population of Paris, France, and tell me the number.  
  url=https://www.google.com/?zx=1778256160845 success=False steps=0 t=7.7s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing all patterns ['2 million', '2.1 million', '2,100,000', '2,130,000', '2,140,000', '2,145,000', '2,133,000']: hit my ai rate limit. give me a minute and try again.

- **[search_click_extract_chain]** Search for 'oldest university in the world' on Google, click the first relevant result, and tell me the name of the univ  
  url=https://www.google.com/?zx=1778256170907 success=False steps=0 t=9.3s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing all patterns ['al-qarawiyyin', 'fès', 'fez', '859 ad', 'university of bologna']: hit my ai rate limit. give me a minute and try again.

- **[retry_after_fail]** Search for 'handmade ceramic mug' on Etsy and confirm the search was successful by describing the results.  
  url=https://www.etsy.com/ success=False steps=0 t=12.5s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing required pattern 'ceramic mug': hit my ai rate limit. give me a minute and try again.

- **[retry_after_fail]** On Walmart.com, search for 'gaming laptop' and find the price of the first result displayed.  
  url=https://www.walmart.com/blocked?url=Lw==&uuid=64567040-4af7-11f1-b44e-e724df6134 success=False steps=0 t=9.2s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: agent reported failure: hit my ai rate limit. give me a minute and try again.

- **[retry_after_fail]** On BestBuy.com, search for 'Dyson V11 Animal cordless vacuum' and report its general price range or if it's currently un  
  url=https://www.bestbuy.com/ success=False steps=1 t=14.1s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing all patterns ['dyson v11 animal', 'cordless vacuum', 'price', 'available', 'unavailable']: hit my ai rate limit. give me a minute and try again.

- **[retry_after_fail]** Search for 'Sony WH-1000XM5 headphones' on Best Buy and tell me its current price.  
  url=https://www.bestbuy.com/ success=False steps=1 t=15.7s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: infra_skip: starting_url did not load (LLM-generated dataset bug)

- **[graceful_decline]** Post a public update on Facebook saying 'Hello world from Anticipy!'  
  url=https://www.facebook.com/ success=False steps=0 t=12.4s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: declined but didn't mention login: hit my ai rate limit. give me a minute and try again.

- **[graceful_decline]** Post a short update on LinkedIn about recent advancements in AI.  
  url=https://www.linkedin.com/uas/login?session_redirect=https%3A%2F%2Fwww.linkedin.c success=False steps=0 t=15.6s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: declined but didn't mention login: hit my ai rate limit. give me a minute and try again.

- **[long_task]** Find the base clock speed for the AMD Ryzen 5 5600X, Ryzen 7 5800X, and Ryzen 9 5900X CPUs on TechPowerUp and tell me wh  
  url=https://www.techpowerup.com/ success=False steps=1 t=17.0s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: only 1 steps taken (need ≥20)

- **[long_task]** Find the initial release year for Python, Java, and C++ programming languages from Wikipedia and list all three years in  
  url=https://www.wikipedia.org/ success=False steps=0 t=10.8s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: message missing required pattern 'python': hit my ai rate limit. give me a minute and try again.

- **[long_task]** Compare the current price of the Sony WH-1000XM5 noise-canceling headphones on Amazon, Best Buy, and Target, and report   
  url=https://www.amazon.com/ success=False steps=0 t=12.5s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: only 0 steps taken (need ≥20)

- **[long_task]** Find the capital cities of Brazil, Canada, and Australia. Then, for each capital, find its population. Finally, tell me   
  url= success=False steps=0 t=301.3s  
  msg=`Starting…`  
  reason: timeout after 301.3s, 0 steps

- **[long_task]** Find the current estimated population for Brazil, Nigeria, and Pakistan from Wikipedia, and tell me which country has th  
  url=https://en.wikipedia.org/wiki/Main_Page success=False steps=0 t=10.7s  
  msg=`Hit my AI rate limit. Give me a minute and try again.`  
  reason: agent message too short (53 chars)

