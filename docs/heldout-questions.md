# Held-out questions (10)

Add these to backend/evaluation/datasets/studymate_eval.json with "author": "user".
Page numbers are PDF page numbers (as the app reports them).

| # | Type | Document | Question | Expected page | Reference answer |
|---|---|---|---|---|---|
| 1 | answerable | IPCC | How many countries have written adaptation into their climate policies and planning? | 14 | At least 170 countries |
| 2 | answerable | IPCC | How many modelled emission pathways did the report sort into categories by warming level? | 15 | 1202 pathways |
| 3 | answerable | IPCC | What is the best estimate of warming for 2081-2100 under the very high emissions scenario? | 18 | 4.4 °C (SSP5-8.5) |
| 4 | answerable | IPCC | If a large volcanic eruption happened, how long would it mask human-caused warming? | 19 | One to three years |
| 5 | answerable | Skylab (19740024203.pdf) | On which mission day did the third crew run out of disposal bags? | 108 | Mission day 25 (MD 25) |
| 6 | answerable | Telescope (19770007900.pdf) | What is the maximum time the filter wheel needs to move from one position to any other? | 85 | 14 seconds |
| 7 | unanswerable_on_topic | IPCC | What agreement was reached at COP27? | none | Not in the documents (COP27 is never mentioned) |
| 8 | unanswerable_on_topic | Telescope | How many servicing missions did the Space Telescope receive? | none | Not in the documents (servicing missions are never mentioned) |
| 9 | unanswerable_off_topic | none | How many players are on the court for each team in basketball? | none | Not in the documents |
| 10 | unanswerable_off_topic | none | What is a good way to learn the guitar as a beginner? | none | Not in the documents |

Ground truth for 1-6: each needs a short evidence quote from the expected page, as the other
answerable items have. For 7-8, the key terms were searched in all three PDFs and do not appear.