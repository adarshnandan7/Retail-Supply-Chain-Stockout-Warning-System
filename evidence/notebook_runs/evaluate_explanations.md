# Task `evaluate_explanations` - SUCCESS
- Task run id: `728235320267827`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/risk/evaluate_explanations`
- Duration: 158 s

## Cell 1

```markdown
%md
# 05d - Evaluate the Gen AI planner notes (quality gate)

Every LLM-written note is checked against the structured facts the risk-scoring step computed:

| Check | Type | Pass rule |
|---|---|---|
| Number faithfulness | deterministic | every number in the note appears in the facts given to the LLM (rounding tolerated) |
| Action match | deterministic | the note names the recommended action (expedite / transfer / reorder) |
| Quantity match | deterministic | the note states the recommended quantity |
| Length | deterministic | at most 3 sentences |
| Faithfulness, actionability, clarity (1-5) | LLM judge (a different model than the writer) | faithfulness >= 4 and verdict PASS |

Results go to MLflow (metrics + per-note table) and to the Delta table `risk_explanation_eval`. Notes that fail are
replaced in `risk_recommendations` by the deterministic template, so a planner never sees an unverified note.
```

## Cell 2

```python
dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("judge_endpoint", "databricks-claude-sonnet-5-5")
dbutils.widgets.text("eval_experiment", "/Users/adarsh.nandan@databricks.com/inventory-risk-radar-planner-note-eval")
dbutils.widgets.text("min_pass_rate", "0.9")
CATALOG, SCHEMA = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
FQ = f"{CATALOG}.{SCHEMA}"
JUDGE = dbutils.widgets.get("judge_endpoint")
EXPERIMENT = dbutils.widgets.get("eval_experiment")
MIN_PASS = float(dbutils.widgets.get("min_pass_rate"))
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
```

## Cell 3

```markdown
%md ## LLM judge (Claude Sonnet judges notes written by Claude Haiku)
```

## Cell 4

```python
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW judged AS
SELECT e.recommendation_id, e.prompt, e.llm_explanation, s.recommended_action, s.recommended_qty, s.risk_tier, s.primary_driver,
  ai_query('{JUDGE}',
    concat(
      'You are auditing a note written for a grocery replenishment planner. Compare the NOTE with the FACTS.\\n',
      'Score 1-5: faithfulness (5 = every number and cause in the note is supported by the facts, 1 = invents or contradicts facts), ',
      'actionability (5 = states the action and quantity clearly), clarity (5 = plain, short, unambiguous). ',
      'verdict = PASS only if faithfulness >= 4 and the note states the same action as the facts.\\n',
      'Return ONLY a JSON object: {{"faithfulness": n, "actionability": n, "clarity": n, "verdict": "PASS" or "FAIL", "issue": "short reason or empty"}}\\n\\n',
      'FACTS:\\n', e.prompt, '\\n\\nNOTE:\\n', e.llm_explanation),
    modelParameters => named_struct('max_tokens', 2000), failOnError => false) AS j
FROM {FQ}.risk_explanations e JOIN {FQ}.risk_scores s USING (recommendation_id)
WHERE e.llm_explanation IS NOT NULL
""")
jud = spark.sql("""
SELECT *, from_json(regexp_extract(j.result, '\\\\{[\\\\s\\\\S]*\\\\}', 0),
          'faithfulness INT, actionability INT, clarity INT, verdict STRING, issue STRING') AS js, j.errorMessage AS judge_error
FROM judged""").toPandas()
print(len(jud), "notes judged;", int(jud.judge_error.notna().sum()), "judge errors")
```

**Output**

```text
400 notes judged; 0 judge errors
```

## Cell 5

```markdown
%md ## Deterministic faithfulness checks
```

## Cell 6

```python
import json
import re

import mlflow
import numpy as np
import pandas as pd

NUM = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?")
ACTION_WORDS = {"EXPEDITE": ("expedit",), "TRANSFER": ("transfer", "move"), "REORDER": ("reorder", "order")}


def numbers(text: str) -> list[float]:
    return [float(x.replace(",", "")) for x in NUM.findall(text or "")]


def supported(n: float, facts: list[float]) -> bool:
    return any(abs(n - f) <= 0.51 or (f and abs(n - f) / abs(f) <= 0.01) or abs(n - round(f)) < 1e-9 for f in facts)


rows = []
for r in jud.itertuples():
    facts = numbers(r.prompt)
    note_nums = numbers(r.llm_explanation)
    unsupported = [n for n in note_nums if not supported(n, facts)]
    low = (r.llm_explanation or "").lower()
    action_ok = any(w in low for w in ACTION_WORDS.get(r.recommended_action, ()))
    qty_ok = any(abs(n - float(r.recommended_qty)) < 0.51 for n in note_nums)
    sentences = len([x for x in re.split(r"(?<=[.!?])\s+", (r.llm_explanation or "").strip()) if x])
    js = r.js if isinstance(r.js, dict) else (r.js.asDict() if r.js is not None else {})
    faith, act, clar = js.get("faithfulness"), js.get("actionability"), js.get("clarity")
    verdict = (js.get("verdict") or "").upper()
    deterministic_pass = action_ok and qty_ok and not unsupported and sentences <= 3
    judge_pass = verdict == "PASS" and (faith or 0) >= 4
    rows.append({
        "recommendation_id": r.recommendation_id, "risk_tier": r.risk_tier, "primary_driver": r.primary_driver,
        "recommended_action": r.recommended_action, "recommended_qty": int(r.recommended_qty),
        "llm_explanation": r.llm_explanation, "numbers_in_note": len(note_nums), "unsupported_numbers": json.dumps(unsupported),
        "unsupported_number_count": len(unsupported), "action_match": action_ok, "quantity_match": qty_ok, "sentence_count": sentences,
        "deterministic_pass": deterministic_pass, "judge_faithfulness": faith, "judge_actionability": act, "judge_clarity": clar,
        "judge_verdict": verdict or None, "judge_issue": js.get("issue"), "judge_error": r.judge_error,
        "judge_endpoint": JUDGE, "final_pass": bool(deterministic_pass and judge_pass),
    })
ev = pd.DataFrame(rows)
metrics = {
    "notes_evaluated": len(ev),
    "deterministic_pass_rate": float(ev.deterministic_pass.mean()),
    "number_faithfulness_rate": float((ev.unsupported_number_count == 0).mean()),
    "action_match_rate": float(ev.action_match.mean()),
    "quantity_match_rate": float(ev.quantity_match.mean()),
    "judge_pass_rate": float((ev.judge_verdict == "PASS").mean()),
    "judge_faithfulness_mean": float(ev.judge_faithfulness.dropna().mean()),
    "judge_actionability_mean": float(ev.judge_actionability.dropna().mean()),
    "judge_clarity_mean": float(ev.judge_clarity.dropna().mean()),
    "final_pass_rate": float(ev.final_pass.mean()),
}
print(json.dumps({k: round(v, 4) for k, v in metrics.items()}, indent=2))
print("\nFailing notes (sample):")
print(ev[~ev.final_pass][["recommendation_id", "unsupported_numbers", "action_match", "quantity_match", "judge_faithfulness", "judge_verdict", "judge_issue"]].head(10).to_string(index=False))
```

**Output**

```text
{
  "notes_evaluated": 400,
  "deterministic_pass_rate": 0.955,
  "number_faithfulness_rate": 0.99,
  "action_match_rate": 1.0,
  "quantity_match_rate": 1.0,
  "judge_pass_rate": 0.9875,
  "judge_faithfulness_mean": 4.95,
  "judge_actionability_mean": 4.9625,
  "judge_clarity_mean": 3.7975,
  "final_pass_rate": 0.945
}

Failing notes (sample):
recommendation_id unsupported_numbers  action_match  quantity_match  judge_faithfulness judge_verdict                                                                                                                                                                                                                                                                                                                                                            judge_issue
      S038-P00332                  []          True            True                   5          PASS                                                                                                                                                                                                                                               Format deviation: the note has three sentences instead of the requested two, and the first is long. Content is accurate.
      S046-P00092               [4.0]          True            True                   5          PASS                                                                                                                                                                                                                                                                                                                                                                       
      S035-P00096                  []          True            True                   3          FAIL The note says the 20 inbound units are "projected 3 days late". The facts say they are "now projected in 3 days", meaning they arrive in 3 days, not that they are 3 days late. This misstates a number. The other figures (9 on hand, 33.5 forecast, +16 promotion, 7.1 vs 4.9 per day) and the action (expedite 20 units with Evergreen Meat Foods) match the facts.
      S023-P00006                  []          True            True                   5          PASS                                                                                                                                                                                                                  Facts all supported and action matches (expedite 96 units). Sentence 1 is long and crowded, and 'expedite' is repeated, which hurts clarity slightly.
      S041-P00092                  []          True            True                   3          FAIL                        The note says the inbound units are "2 days late", but the facts say they are late and now projected to arrive in 2 days. This misstates the delay. The other numbers (0 on hand, 24 inbound, 51.8 vs 28.7, +23, 7.0 vs 5.5) and the action (expedite 24 units with Summit Dairy Wholesale) match. The first sentence is also long and crowded.
      S012-P00290                  []          True            True                   3          FAIL                                                                                                  The facts say the 56 inbound units are projected to arrive in 2 days, but the note says they arrive '2 days late'. That invents a lateness amount. Sentence 1 is also long and crowded. The action (expedite 56 units with Pacific Fresh Foods) does match the facts.
      S017-P00332              [81.0]          True            True                   5          PASS                                                                                                                                                                                                                                                                                                                                                                       
      S017-P00333                  []          True            True                   5          PASS                                                                                                                                                                                                                                                                                                                                                                       
      S039-P00153                  []          True            True                   5          PASS                                                                                                                                                                                                                                                                                                                                                                       
      S004-P00154                  []          True            True                   5          PASS                                                                                                                                                                                                                                                  Facts and action are accurate, but the note runs well past two sentences (the task asked for exactly two short ones).
```

## Cell 7

```markdown
%md ## Log to MLflow, persist, and gate what planners see
```

## Cell 8

```python
mlflow.set_experiment(EXPERIMENT)
writer = spark.table(f"{FQ}.risk_explanations").select("llm_endpoint").first()[0]
with mlflow.start_run(run_name="planner_note_quality") as run:
    mlflow.log_params({"writer_endpoint": writer, "judge_endpoint": JUDGE, "min_pass_rate": MIN_PASS, "notes": len(ev)})
    mlflow.log_metrics(metrics)
    mlflow.log_table(ev, "planner_note_eval.json")
print("MLflow run", run.info.run_id)

spark.createDataFrame(ev).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{FQ}.risk_explanation_eval")
spark.sql(f"COMMENT ON TABLE {FQ}.risk_explanation_eval IS 'Per-note quality evaluation of Gen AI planner notes: deterministic number/action/quantity checks plus LLM-judge scores; final_pass gates what planners see.'")

failed = ev[~ev.final_pass].recommendation_id.tolist()
spark.createDataFrame(pd.DataFrame({"recommendation_id": failed or ["__none__"]})).createOrReplaceTempView("failed_notes")
spark.sql(f"""
MERGE INTO {FQ}.risk_recommendations t
USING failed_notes f ON t.recommendation_id = f.recommendation_id
WHEN MATCHED THEN UPDATE SET
  t.planner_explanation = concat(t.sku_name, ' at ', t.store_name, ' has a ', round(t.stockout_probability * 100), '% chance of running out in the next ',
    t.lead_time_window_days, ' days (', t.primary_driver, '). Suggested: ', t.recommended_action,
    CASE WHEN t.recommended_qty > 0 THEN concat(' ', t.recommended_qty, ' units.') ELSE '.' END),
  t.explanation_is_llm = false
""")
print(f"{len(failed)} notes replaced by the deterministic template; {len(ev) - len(failed)} LLM notes published")
gate = "PASS" if metrics["final_pass_rate"] >= MIN_PASS else "BELOW_THRESHOLD"
print("quality gate:", gate)

with open(f"{EVIDENCE}/05d_genai_eval.json", "w") as fh:
    json.dump({"writer_endpoint": writer, "judge_endpoint": JUDGE, "mlflow_run_id": run.info.run_id, "experiment": EXPERIMENT,
               "metrics": metrics, "quality_gate": gate, "min_pass_rate": MIN_PASS, "notes_replaced_by_template": len(failed),
               "failing_examples": ev[~ev.final_pass].head(5).to_dict(orient="records"),
               "passing_examples": ev[ev.final_pass].head(3).to_dict(orient="records")}, fh, indent=2, default=str)
```

**Output**

```text
MLflow run d6b17417eee941b9a6207067e803fba7
22 notes replaced by the deterministic template; 378 LLM notes published
quality gate: PASS
```
