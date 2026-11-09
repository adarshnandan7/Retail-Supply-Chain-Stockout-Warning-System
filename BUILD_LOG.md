# Build log: how this was built, and where AI made the difference

**Builder:** Adarsh Nandan (Databricks Field Engineering)
**AI coding tool:** Claude Code v2.1 (terminal agent, model Claude Opus 5.5), running locally against the Databricks workspace through the Databricks CLI profile `serverless-stable-3vku19`, plus `git` and `uv`.
**Claude Code skills loaded during the build:** `databricks-lakebase-autoscale` (projects, branches, OAuth tokens, synced tables), `databricks-genie` (serialized space format), `databricks-aibi-dashboards` (widget spec versions, field-name rules), `fe-google-tools:google-slides` (Databricks corporate template, deck validator, thumbnail QA).
**AI inside the product (separate from the build tooling):** `ai_query` on Databricks Foundation Model endpoints. Claude Haiku 5.5 writes the planner notes and Claude Sonnet 5.5 judges them. A Genie space answers natural-language questions.

All timestamps below are UTC on 2026-11-07, taken from the git history and the Databricks job-run history.

---

## 1. Workflow

| Phase | What the builder did | What Claude Code did |
|---|---|---|
| **Brief** | Pasted the FE-Bar requirements, the business statement (retail inventory risk radar) and the environment details. Asked for questions first, then a plan with a time estimate. | Read the brief and checked access read-only: `gh auth status` (the Databricks EMU account had pull-only access to the personal repo), the `databricks current-user` profile, `gcloud` ADC. Listed the workspace's catalogs, SQL warehouses, Lakebase projects and Foundation Model endpoints. |
| **Platform discovery** | | Instead of guessing YAML from docs, introspected `databricks bundle schema` and found that the installed CLI supports `postgres_projects`, `postgres_databases`, `postgres_synced_tables`, `genie_spaces`, `dashboards` and `apps` with `postgres` / `genie_space` / `uc_securable` resource bindings. **This decision made the whole stack bundle-managed**, including Lakebase and Genie, rather than half-scripted. |
| **Decisions** | Answered four questions: push via a fine-grained PAT; Streamlit for the app; Google Slides for the deck; a grocery scenario at 50 stores × 400 SKUs. | Asked the four questions that changed the build, using the trade-offs it had discovered. Picked sensible defaults for everything else (new schema in the existing catalog, serverless everywhere). |
| **Plan** | Approved a 14-step plan estimated at **9.5 hours**. | Wrote the plan: repo layout, design, step list with estimates, and the verification evidence each step would produce. |
| **Credentials** | Stored the PAT in the macOS keychain himself with a `!` shell command, scoped to this repo's path only. | Its auto-mode safety classifier **refused to handle the token itself**. It paused, explained why, and gave the exact one-line command, then verified push access with an initial commit before writing any build code. |
| **Build (auto mode)** | Reviewed results at checkpoints, asked for fixes, and decided what went into the repo (deck and script kept local). | Wrote the code, deployed with `databricks bundle deploy`, ran jobs, read failures from run output, fixed them, unit-tested, and committed in logical steps. Reported progress as a step table with time remaining. |
| **Evidence** | Asked for execution evidence readable as text. | Wrote scripts that pull evidence from the live workspace (job runs, pipeline event log, MLflow and UC model alias, SQL results, Genie API answers, Postgres queries) rather than hand-written claims. Also wrote a notebook exporter that decodes each executed notebook into Markdown with its outputs. |
| **Readout** | Chose Google Slides; reviewed the deck. | Built the deck from a JSON spec on the Databricks corporate template, with five-part speaker notes per slide, and validated it programmatically. Fixed issues found in the thumbnails (a slide that silently failed to render, tables at half width), exported the PDF and wrote the role-play script. |

**Actual time:** the first commit was at 12:51 and the deck and script were done by 14:44. That is **about 2 hours of execution after plan approval, against the 9.5-hour estimate**. Of that, the full end-to-end job took about 19 minutes (13:51–14:10).

| UTC | Milestone |
|---|---|
| 12:51 | Repo initialised; push verified with the PAT |
| 12:53 | Bundle scaffold, schema and volumes |
| 12:56 → 12:58 | First data-generation run failed; fixed and re-run (14.6M inventory rows, 12.7M POS rows in 4 min) |
| 13:03 | Lakeflow pipeline full refresh complete (bronze → silver → gold) |
| 13:10 | Model trained: LightGBM WAPE 0.455 vs baseline 0.529, registered `@champion` |
| 13:16 → 13:20 | Gen AI task failed, fixed, re-run |
| 13:27 → 13:33 | Metric-view task failed (tag policy), fixed, re-run |
| 13:40–13:48 | Genie, dashboard and app deployed; headless app test passed |
| 13:51 → 14:10 | **Final full end-to-end run `465476598725505`: 9 of 9 tasks succeeded** |
| 14:11–14:20 | Evidence captured and committed |
| 14:26–14:44 | Deck built, validated and exported; role-play script written |

---

## 2. Where AI measurably sped things up

| Area | What happened | Effect |
|---|---|---|
| Volume of correct boilerplate | About 3,700 lines of Python and YAML across 24 source files: generator, pipeline, features, training, scoring, governance, metric views, Lakebase export, app, dashboard and Genie builders, evidence tooling | The bulk of a 9.5-hour plan landed in about 2 hours |
| Bundle-first platform discovery | Read the CLI's own JSON schema to find exact field names (for example `file_path` for a `.geniespace.json` file, and `postgres.database` taking a full resource path) | No trial-and-error on resource YAML; Lakebase and Genie became bundle resources on the first or second deploy |
| Failure triage from run output | Every failed run was diagnosed from the run's error trace and fixed within minutes (list below) | Each of the 3 failed job runs was green on the next attempt |
| Data reconciliation | Noticed bronze held 4,790 fewer PO events than the generator reported. It counted raw file lines with `read_files` to prove ingestion was right, and traced the gap to a pandas index misalignment in the generator's summary | A silent bug found and fixed before it reached the evidence |
| Evidence automation | Scripts produce text evidence straight from the workspace | Re-capturing all evidence after a run takes about 3 minutes, which made it cheap to re-run everything after each fix |
| Deck QA | Programmatic deck validation plus thumbnail contact sheets | Found a missing slide and two unreadable tables that the validator itself had passed |

**Failures hit and how they were resolved:**

| Symptom | Root cause found | Fix |
|---|---|---|
| `Operation not supported: /Volumes/.../inventory_risk` | Bundle development mode silently prefixed the schema (`dev_adarsh_nandan_inventory_risk`) | Dropped development mode and set the presets explicitly |
| `Principal does not have CREATE CATALOG` | Lakebase-as-UC-catalog needs metastore rights the user doesn't have | Changed the design: synced table in the project schema, plus a job task that copies Lakebase decisions back to Delta |
| `model does not support the parameter(s): temperature` | The Claude Haiku 5.5 endpoint rejects `temperature` | Removed the parameter |
| 393 of 400 LLM notes empty or truncated, with no error | Tested `max_tokens` 160 vs 2000 side by side: hidden reasoning was using up the small budget | `max_tokens` 2000, `failOnError => false`, template fallback; next run had 400 of 400 complete |
| `UC_TAG_POLICY_VALUE_NOT_ALLOWED` | The metastore has governed tag policies on `data_owner`, `sensitivity` and `data_product` | Queried the tag-policy API for allowed values and re-keyed the tags to comply |
| App service principal could not read the synced table | Lakebase privileges are Postgres grants, separate from UC | Added Postgres grants to the job so every refresh re-applies them |
| "Median time to planner action" showed -0.26 h | A decision recorded before the morning re-score was counted against the new publication time | The KPI only counts decisions on the current publication, made after it was published |
| `bad math expression` in a shell step | `GID` is a read-only zsh variable | Renamed the variable |

---

## 3. Where AI changed a decision

**1. The risk logic was redesigned after the first backtest disagreed with it.**
The first version used *p90 supplier lead time + 1 day* as the window, and treated overdue POs as arriving tomorrow. Claude Code ran the backtest it had written and reported results that went against the plan:
- ranked at the same alert volume, today's rule beat the radar (top 500: rule 62% precision vs radar 51%);
- there were **zero EXPEDITE recommendations**, even though the data had a planted supplier disruption (supplier V004 at 58% on time).

It traced both problems to the code:
- 530 overdue PO lines were being projected to land tomorrow, which hid the lateness;
- the p90+1 window was long enough for routine orders to "rescue" items, which inflated alerts.

It changed the window to the supplier's mean actual lead time over the last 30 days, projected overdue lines using lateness-when-late, made EXPEDITE fire when the item runs out before the late units arrive, and added a unit test for each case. It also made the backtest fairer: it excludes items already at zero stock (those aren't predictions) and compares at equal alert volume. **Result: radar precision 62.5% vs 20.4% for the rule, and 732 vs 475 real stockouts caught at the same workload.** Without that run, the deck would have been built on a model that lost to the incumbent.

**2. Stockout days are censored demand.** Claude Code proposed excluding days that ended at zero on hand from training labels and history averages, because sales on those days understate demand. Otherwise the model learns to under-forecast exactly the items that run out. That shaped the feature module and the evaluation.

**3. Lakebase design under a permission constraint.** When `CREATE CATALOG` was denied, it didn't try to work around the permission. It moved the read model into the project schema and added a Lakebase → Delta export task, so the "analytics in Delta, transactions in Lakebase" principle still holds.

**4. Trust in Gen AI output.** After finding silent empty LLM responses, the design changed: the deterministic risk logic owns every number and action, the LLM only rephrases, and a template fallback guarantees a note. Section 5 adds a quality gate on top.

**5. Where the builder steered the AI.**
- The builder required GitHub authentication to be working before any build step.
- The builder decided the deck and role-play script stay off GitHub. They are local preparation material.
- When Claude Code's sandbox could not log in to the app through Okta, the builder accepted a headless Streamlit `AppTest` against the live Lakebase, warehouse and Genie as functional evidence, and kept the visual browser check as a manual step.

---

## 4. How AI output was verified (not taken on trust)

- `tests/test_risk_logic.py`: unit tests for the risk logic (promotion uplift → transfer, late supplier → expedite, overdue line counts as late, well-stocked → monitor).
- `tests/test_app_smoke.py`: headless test of the real app against Lakebase, the SQL warehouse and Genie.
- The backtest measures the radar against what actually happened, using only information available on the scoring date.
- Every number in the deck and script is traced to an `evidence/` file; the deck spec's speaker notes cite the evidence path for each claim.
- Secrets were scanned before every push (Databricks pre-commit hook plus a regex scan for tokens).

---

## 5. After the FE-Bar build review (2026-11-09)

The review asked for this build narrative and suggested four improvements. Claude Code implemented all four, and the builder re-ran the full job to capture evidence:

| Suggestion | What was built | Evidence |
|---|---|---|
| Evaluate the Gen AI notes, not just check they exist | `src/risk/evaluate_explanations.py` runs four deterministic checks per note (every number must appear in the facts, the action must match, the quantity must match, at most 3 sentences), plus an LLM judge (Claude Sonnet 5.5 judging Claude Haiku 5.5) scoring faithfulness, actionability and clarity. Results are logged to MLflow, written to `risk_explanation_eval`, and failing notes are replaced by the template before planners see them | `evidence/12_genai_note_evaluation.md`: 400 notes; 99.0% number-faithful, 100% action and quantity match, judge faithfulness 4.95/5; final pass rate **94.5%** (gate 90%: PASS); 22 notes replaced by the template |
| Turn the governance tag into an enforced row filter | `planner_risk_queue` now has a UC `ROW FILTER` (region, from a `planner_region_access` entitlement table for store-level planners, else groups) and a column `MASK` on revenue at risk. The job runs an enforcement test: map its own identity to one region without financials, query, assert, unmap | `evidence/13_row_filter_enforcement.md`: unmapped admin sees 5 regions with revenue; mapped to Valley without financials sees **only Valley's 4,000 rows, with 0 revenue values** |
| Drift check that triggers retraining | `src/ml/drift_check.py` scores the `@champion` on the latest 28 days and compares with the WAPE at registration (and the baseline). A job `condition_task` runs `train_forecast` only when it detects drift, loss to baseline, a stale model or no champion. The champion only moves if the challenger beats both the baseline and the current champion. Every decision is logged to `model_monitoring` | `evidence/14_drift_monitoring.md`: full run `1079588740947181` judged the champion healthy, so `train_forecast` was **EXCLUDED**. A test run (`912248781031579`, threshold lowered to -1% to simulate drift) **triggered retraining**; the challenger did not beat the champion's 0.4547 WAPE, so `@champion` correctly stayed on v2 |
| Let Genie explain a specific recommendation | Genie instructions and a certified example SQL return the planner note, the quantified drivers and the action for a named item and store, and Genie can report note quality from `risk_explanation_eval` | `evidence/07_genie_answers.md`: "Explain the recommendation for green beans at Stonebrook" returns the planner note, drivers and expedite action; "How good are the Gen AI planner notes?" answers from `risk_explanation_eval` |

**What this second pass taught (AI-assisted, verified by tests):**
- **The enforcement test caught a real bug on its first run.** The row-filter function took a parameter named `region`, and inside its lookup subquery `a.region = region` resolved to the mapping table's own column, so it was always true. The mask worked but the filter didn't (a Valley-only user still saw all 5 regions). The assertion failed the job. Claude Code read the printed test output, identified the name shadowing and renamed the parameter, and the next run passed. Without an executable test, the governance tag alone would have claimed a protection that wasn't enforced.
- **The LLM judge catches what string checks can't.** It failed notes that said units were "2 days late" when the facts said they "arrive in 2 days", a misreading with every number still correct. The deterministic checks are deliberately strict in the other direction: a note that adds 14 + 40 = 54 counts as an unsupported number. Both are kept, because a planner-facing note should be traceable to the facts.
- **Champion/challenger needs a tie-break rule.** Retraining on unchanged data reproduced the same model quality, and the rule "must beat the current champion" correctly kept v2. The decision and its reason are in `model_monitoring` and in the run's notebook output.

Full end-to-end run after these changes: `1079588740947181`, 12 tasks (11 ran; retraining skipped by the drift check), about 18 minutes of task time, all succeeded.
