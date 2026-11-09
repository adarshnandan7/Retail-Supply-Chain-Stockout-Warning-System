# Gen AI planner notes: evaluation and quality gate

_Captured 2026-11-09 13:30 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

- Writer: `databricks-claude-haiku-5-5` | Judge: `databricks-claude-sonnet-5-5` (a different model)
- MLflow experiment `/Users/adarsh.nandan@databricks.com/inventory-risk-radar-planner-note-eval`, run `d6b17417eee941b9a6207067e803fba7`
- Quality gate (final pass rate >= 90%): **PASS**; 22 failing notes replaced by the deterministic template before publishing

| Metric | Value |
|---|---|
| notes_evaluated | 400 |
| deterministic_pass_rate | 0.955 |
| number_faithfulness_rate | 0.990 |
| action_match_rate | 1.000 |
| quantity_match_rate | 1.000 |
| judge_pass_rate | 0.988 |
| judge_faithfulness_mean | 4.950 |
| judge_actionability_mean | 4.963 |
| judge_clarity_mean | 3.797 |
| final_pass_rate | 0.945 |

### Failing notes and why (judge issue / unsupported numbers)

```sql
SELECT recommendation_id, recommended_action, recommended_qty, unsupported_numbers, action_match, quantity_match, sentence_count,
  judge_faithfulness, judge_verdict, judge_issue FROM serverless_stable_3vku19_catalog.inventory_risk.risk_explanation_eval WHERE NOT final_pass ORDER BY judge_faithfulness LIMIT 10
```

| recommendation_id | recommended_action | recommended_qty | unsupported_numbers | action_match | quantity_match | sentence_count | judge_faithfulness | judge_verdict | judge_issue |
|---|---|---|---|---|---|---|---|---|---|
| S041-P00092 | EXPEDITE | 24 | [] | true | true | 2 | 3 | FAIL | The note says the inbound units are "2 days late", but the facts say they are late and now projected to arrive in 2 days. This misstates the delay. The other numbers (0 on hand, 24 inbound, 51.8 vs 28.7, +23, 7.0 vs 5.5) and the action (expedite 24 units with Summit Dairy Wholesale) match. The first sentence is also long and crowded. |
| S012-P00290 | EXPEDITE | 56 | [] | true | true | 4 | 3 | FAIL | The facts say the 56 inbound units are projected to arrive in 2 days, but the note says they arrive '2 days late'. That invents a lateness amount. Sentence 1 is also long and crowded. The action (expedite 56 units with Pacific Fresh Foods) does match the facts. |
| S033-P00078 | EXPEDITE | 528 | [] | true | true | 3 | 3 | FAIL | The note says the 528 inbound units arrive in 5 days 'instead of within the window'. The window is 10 days, so 5 days is inside it, and the note wrongly implies the delivery misses the window. The other numbers (0 on hand, 82.5/day vs 36.4/day, expedite 528 units from Summit Snacks Supply Co.) match the facts. |
| S014-P00262 | REORDER | 42 | [] | true | true | 2 | 3 | FAIL | The note says the inbound 96 units arrive '2 days late', but the facts say they are late and now projected to arrive in 2 days. The lateness amount is invented. The action (reorder 42 units from Summit Pantry Foods, case pack 6) matches the facts. The first sentence is long and crowded. |
| S035-P00096 | EXPEDITE | 20 | [] | true | true | 2 | 3 | FAIL | The note says the 20 inbound units are "projected 3 days late". The facts say they are "now projected in 3 days", meaning they arrive in 3 days, not that they are 3 days late. This misstates a number. The other figures (9 on hand, 33.5 forecast, +16 promotion, 7.1 vs 4.9 per day) and the action (expedite 20 units with Evergreen Meat Foods) match the facts. |
| S023-P00006 | EXPEDITE | 96 | [] | true | true | 4 | 5 | PASS | Facts all supported and action matches (expedite 96 units). Sentence 1 is long and crowded, and 'expedite' is repeated, which hurts clarity slightly. |
| S017-P00333 | EXPEDITE | 42 | [] | true | true | 5 | 5 | PASS |  |
| S046-P00092 | REORDER | 48 | [4.0] | true | true | 2 | 5 | PASS |  |
| S038-P00332 | EXPEDITE | 56 | [] | true | true | 4 | 5 | PASS | Format deviation: the note has three sentences instead of the requested two, and the first is long. Content is accurate. |
| S017-P00332 | EXPEDITE | 52 | [81.0] | true | true | 2 | 5 | PASS |  |

### Passing notes (sample)

```sql
SELECT recommendation_id, judge_faithfulness, judge_actionability, judge_clarity, llm_explanation FROM serverless_stable_3vku19_catalog.inventory_risk.risk_explanation_eval WHERE final_pass LIMIT 4
```

| recommendation_id | judge_faithfulness | judge_actionability | judge_clarity | llm_explanation |
|---|---|---|---|---|
| S044-P00043 | 5 | 5 | 4 | Only 46 units are on hand against 255.3 units of forecast demand over the 3-day window (usual 230.2), and the 348 inbound units are late, now projected to arrive in 5 days, after the window closes. Ask Riverbend Fresh Supply Co. to expedite the 348 delayed PO units. |
| S040-P00062 | 5 | 5 | 3 | Harvest Lane Heavy Cream Large has 0 units on hand and no inbound units arriving within the 3-day window, while forecast demand of 139.7 units (usual 88.9) is pushed up by a promotion adding 51 units, and its 138 late inbound units are now projected to arrive in 4 days. Expedite 138 units by asking Summit Dairy Wholesale to speed up the delayed PO units to cover the $820.0 in revenue at risk. |
| S004-P00114 | 5 | 5 | 4 | Crestline Sweet Potatoes Value Pack at Harvest Lane Dunmore Superstore has 0 units on hand, its 192 inbound units are late and now projected in 2 days, and an upcoming promotion pushes forecast demand to 296.3 units over the 4-day window (usual: 135.0). Ask Pacific Fresh Foods to expedite 192 delayed PO units to protect the $532.0 in revenue at risk. |
| S024-P00114 | 5 | 5 | 4 | Forecast demand of 425.1 units over the next 4 days far exceeds the 86 units on hand, driven by a promotion adding 248 units versus usual, and the 192 inbound units are late and now projected to arrive in 2 days. Ask Pacific Fresh Foods to expedite the 192 delayed PO units. |

### Published notes: LLM vs template after the gate

```sql
SELECT explanation_is_llm, count(*) AS rows FROM serverless_stable_3vku19_catalog.inventory_risk.risk_recommendations WHERE risk_tier IN ('Critical','High') GROUP BY 1
```

| explanation_is_llm | rows |
|---|---|
| false | 1960 |
| true | 378 |
