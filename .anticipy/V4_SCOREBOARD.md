# V4-7 SCOREBOARD

Generated 2026-05-15 23:43:12

Each task: 3 runs from blank Chrome, vision-auditor grades the final state on real pixels (no fabrication possible).

## Tier 1 (general DOM) - target 95% aggregate

- [FAIL] gmail_compose_send: 0/3 (ITERATION_EXHAUSTED,HARD_FAIL,HARD_FAIL)
- [PASS] gmail_search: 3/3 (SUCCESS,SUCCESS,SUCCESS)
- [PASS] youtube_search: 3/3 (SUCCESS,SUCCESS,SUCCESS)
- [FAIL] amazon_price: 0/3 (HARD_FAIL,ITERATION_EXHAUSTED,ITERATION_EXHAUSTED)
- [FAIL] resy_restaurant: 0/3 (HARD_FAIL,HARD_FAIL,HARD_FAIL)
- [OK2of3] notion_recent: 2/3 (HARD_FAIL,SUCCESS,SUCCESS)
- [FAIL] slack_recent: 0/3 (HARD_FAIL,-,-)
- [FAIL] spotify_song: 0/3 (-,-,-)
- [FAIL] maps_coffee: 0/3 (-,-,-)
- [FAIL] github_repos: 0/3 (-,-,-)
- [FAIL] hackernews_top: 1/3 (SUCCESS,-,-)
- [FAIL] reddit_top: 0/3 (-,-,-)

**Tier 1 AGGREGATE: 9/20 successful runs = 45.0% (not rounded)**
- tasks at 3/3: 2/12 (gate A needs >=11)
- tasks at >=2/3: 3/12 (gate B needs all 12 AND aggregate >=95%)
- **Tier 1 DONE: NO** (A=N, B=N)

## Tier 2 (canvas apps) - target 90%

- [FAIL] sheets_cell_write: 0/3 (-,-,-)
- [FAIL] sheets_header_row: 0/3 (-,-,-)
- [FAIL] sheets_formula: 0/3 (-,-,-)
- [FAIL] docs_paragraph: 0/3 (-,-,-)
- [FAIL] docs_heading: 0/3 (-,-,-)
- [FAIL] slides_text: 0/3 (-,-,-)
- [FAIL] canva_navigate: 0/3 (-,-,-)
- [FAIL] figma_navigate: 0/3 (-,-,-)

**Tier 2 score: 0/8 tasks pass at >=2/3 (0%) - target 90%, 2-attempt cap, frontier limit accepted**

## Tier 1 tasks not yet at 3/3 (fix loop targets)

### gmail_compose_send (0/3)
  - run 0: ITERATION_EXHAUSTED | 22 iters exhausted | /Users/omarebrahim/.anticipy/trajectories/1778902623_024c50
  - run 1: HARD_FAIL | diverged repeatedly: The contact selection dialog remains open with no visible change; clicking at coordinate [726, 212] did not select a contact or advance the | /Users/omarebrahim/.anticipy/trajectories/1778903028_6a13a8
  - run 2: HARD_FAIL | diverged repeatedly: The contact selection dialog remains open with no visible change; clicking at coordinate [726, 213] did not select a contact or advance the | /Users/omarebrahim/.anticipy/trajectories/1778903389_4f584f

### amazon_price (0/3)
  - run 0: HARD_FAIL | diverged repeatedly: The before and after images appear identical with no visible change to the search bar or any search results for 'usb-c cable'; the action d | /Users/omarebrahim/.anticipy/trajectories/1778903863_4d2f3f
  - run 1: ITERATION_EXHAUSTED | 16 iters exhausted | /Users/omarebrahim/.anticipy/trajectories/1778903952_21535d
  - run 2: ITERATION_EXHAUSTED | 16 iters exhausted | /Users/omarebrahim/.anticipy/trajectories/1778904274_54f2d3

### resy_restaurant (0/3)
  - run 0: HARD_FAIL | diverged repeatedly: The scroll action did not reveal any restaurant listings or names; the page content remains essentially the same with only editorial articl | /Users/omarebrahim/.anticipy/trajectories/1778904511_80e856
  - run 1: HARD_FAIL | diverged repeatedly: The scroll action produced no visible change between the before and after images; the page content, layout, and all elements remain identic | /Users/omarebrahim/.anticipy/trajectories/1778904609_f67240
  - run 2: HARD_FAIL | diverged repeatedly: The scroll action did not reveal any restaurant listings or names; the page content remained essentially the same with only editorial artic | /Users/omarebrahim/.anticipy/trajectories/1778904714_576d07

### notion_recent (2/3)
  - run 0: HARD_FAIL | diverged repeatedly: The action clicked 'Log in' which opened a login page instead of accessing the workspace sidebar to find page titles. | /Users/omarebrahim/.anticipy/trajectories/1778904821_f87156

### slack_recent (0/3)
  - run 0: HARD_FAIL | diverged repeatedly: The Slack sign-in page remains unchanged with no visible progress toward opening a workspace or viewing messages. | /Users/omarebrahim/.anticipy/trajectories/1778905442_13d693
  - run 1: not yet run
  - run 2: not yet run

### spotify_song (0/3)
  - run 0: not yet run
  - run 1: not yet run
  - run 2: not yet run

### maps_coffee (0/3)
  - run 0: not yet run
  - run 1: not yet run
  - run 2: not yet run

### github_repos (0/3)
  - run 0: not yet run
  - run 1: not yet run
  - run 2: not yet run

### hackernews_top (1/3)
  - run 1: not yet run
  - run 2: not yet run

### reddit_top (0/3)
  - run 0: not yet run
  - run 1: not yet run
  - run 2: not yet run
