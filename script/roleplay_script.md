# Readout script for the role-play: Inventory Risk Radar for Harvest Lane Markets

**In the room:** the business stakeholder (VP of Supply Chain, the executive sponsor who funds the decision) and the technical stakeholder (data and architecture lead, who has to run what we built).
**Length:** about 15 minutes of presenting, then 10–15 minutes of questions. Present with the deck open; the demo moments are marked **[SHOW]**.
**Structure:** frame → tell → show → tell (what it means) for each part. Lead with the outcome, speak in their KPIs, and go deeper on technology only when asked.

---

## Numbers to have ready (all from the executed build; synthetic data)

| Topic | Number |
|---|---|
| Scope | 50 stores, 5 regions, 400 SKUs, 2 years of daily data, 20,000 store/SKU combinations |
| Stockout baseline | 4.2% of store/SKU/days end empty; **19% on promotion days** (4.6x) |
| Lost sales | about **$10.8M a year** before substitution, on $226M of sales for the 400-SKU slice |
| Alert precision (4-week backtest) | **62%** for the radar vs **20%** for today's cover rule |
| Same workload | **732 vs 475** real stockouts caught (+54%) with 1,172 alerts each |
| Alert volume | 1,172 vs 5,372 (**78% fewer**) |
| Recall (honest trade-off) | radar 38% vs rule 57%; the rule catches more by flagging five times as many items |
| Forecast error (WAPE) | 0.455 vs 0.529 (**-14%**); promo days 0.401 vs 0.549 (**-27%**); bias +1.6% vs +5.8% |
| Today's queue | 2,338 Critical/High items; 2,094 driven by late suppliers; **one call to Summit Dairy covers 516 store/SKUs** (58% on time over the last 30 days vs a 2-day contract) |
| Data quality | Lakeflow rules dropped ~21,000 bad POS rows (negative units, missing SKU, duplicates), 2,900 negative inventory snapshots, 650 POs with no quantity |
| Run time | about 19 minutes end to end per day on serverless compute (9 tasks) |
| Lakebase | point query on the synced queue about 10 ms; decisions, notes and watchlists are written there and copied back to Delta |
| Illustrative value | $10.8M lost × 50% not substituted × 38% caught × 50% prevented ≈ **$1.0M a year recovered sales** on 400 SKUs (assumptions to be confirmed in the pilot) |

---

## 1. Demo setup (about 1.5 min) — slide 1

> "Thank you both for the time. I want to spend about fifteen minutes on one question your planners ask every morning: *which items will run out before the next delivery arrives, and what should we do about it?*
>
> Here is the plan. First, I will show you what we found, in the KPIs you already track: on-shelf availability, lost sales, and planner workload. Then I will show you the working build: the planner's morning queue, why each item is on it, and how a planner records a decision. I will close with what a pilot on your own data looks like and what we need from you.
>
> [To the VP] Your question is whether this moves availability and lost sales enough to fund it. [To the architect] Yours is whether it is something your team can run, govern and trust. I will cover both, and please interrupt at any point."

*Why this works:* it names the customer, the problem and the agenda, and gives each stakeholder their own question before the demo starts.

---

## 2. Lead with the outcome (about 2 min) — slide 2

**Tell**
> "Here is the headline. We took the last four weeks and replayed them. We scored risk using only what was known four weeks ago, then checked what actually happened on the shelf.
>
> Six in ten of the radar's alerts were real stockouts. For the days-of-cover rule your planners use today, it was two in ten. Give a planner the same number of alerts, and they catch 54% more real stockouts. They also review 78% fewer alerts than today. And the forecast is 27% more accurate on promotion days, which is exactly where shelves go empty."

**Land it**
> "In plain terms: your planners spend their morning on the items that will actually run out."

---

## 3. The size of the problem (about 2 min) — slides 3 and 4

**Tell**
> "Across 50 stores and the 400 SKUs we modeled, about four in every hundred shelf-days end empty. On promotion days it is almost one in five. The promotions you pay for are where you lose the sale. That adds up to about $10.8 million a year in lost sales before substitution. Some shoppers switch brands, so the true number is lower, and we will calibrate it with your data."

> "Why don't planners see it coming? The data exists, but it lives in five places. And the cover rule has two blind spots. It assumes next week looks like last week, so a promotion or Thanksgiving surprises it. It also assumes suppliers deliver on contract, so a late dairy supplier is invisible until the shelf is empty. Because it flags everything that is low, it produces about 5,400 alerts a day, and four out of five are false. Planners learn to ignore them."

**Land it (slide 5, value by owner)**
> "[To the VP] For you, this means higher availability where it matters most, lost sales tracked as one KPI, and supplier problems visible on the day they start.
> [To both] For your planning lead, it means one short ranked queue, with the reason for each item in units and a suggested action: expedite, transfer or reorder. The planner stays in charge. Nothing is ordered automatically, and every decision is recorded."

---

## 4. How it works (about 2 min) — slides 6 and 7

**Tell**
> "Every morning, four steps run as one governed job on Databricks.
> One: **Lakeflow** pipelines ingest your POS, inventory, purchase-order, promotion and supplier feeds incrementally and enforce data-quality rules. In this run they dropped about 21,000 bad sales records before they could reach a forecast.
> Two: **Unity Catalog** governs everything: tables, the model, the KPI definitions, and who can see which region.
> Three: a **28-day forecast** for every store and SKU, compared with on hand plus inbound over the supplier's *actual* recent lead time. That gives each item a stockout probability, revenue at risk, and drivers in units.
> Four: planners act in a **Databricks App** backed by **Lakebase**, and anyone can ask **Genie** a question in plain English."

[If the architect leans in] "The score itself is deterministic and unit-tested; the LLM only writes the two-sentence note from the computed facts. I can show the code path afterwards."

---

## 5. Demo (about 4 min) — slide 8, then the app

**Tell:** "Let me show you a planner's morning. I will open the queue, pick one item, show why it is at risk, and record a decision."

**[SHOW] App: Risk queue tab**
1. KPIs at the top: Critical and High counts, revenue at risk, items projected out within 3 days.
2. Filter: Region = Valley, Tier = Critical.
3. Click the top row: *Green Beans 2ct at Stonebrook*.
> "46 on hand. About 255 forecast over the next three days. The 348 units on order are late, now projected in five days. The note reads: *'...will likely run out because 46 units on hand cannot cover the 255.6 units forecast... Expedite 348 units from Riverbend Fresh Supply Co.'*"
4. Point at the chart: "The blue line is the projected stock path with the forecast. It goes below zero tomorrow. The grey line is what the old rule assumes."
5. Open POs table: "Here is the late PO."
6. Decision panel: choose EXPEDITE, keep 348, reason "Called Riverbend, truck moved up", then **Save decision**. Add the item to the watchlist.
> "That decision is now in Lakebase, our operational Postgres, in milliseconds. Tomorrow it is also in the lakehouse, so we can measure how fast planners acted and whether the shelf stayed full."

**[SHOW] App: Ask Genie tab**
> Ask: *"Which suppliers are causing the most late-delivery risks?"*
> "Genie uses the same governed definitions. Summit Dairy comes out on top: 516 store/SKUs, 58% on time over the last 30 days against a two-day contract."

**[SHOW, optional] Dashboard:** revenue at risk by region and tier, drivers, and the forecast accuracy page.

**Land it (slide 9)**
> "Step back from single items and a pattern appears. 90% of today's critical risk comes from two late suppliers. For a planner, that turns 500 line-by-line reorders into one expedite conversation. For you, it is a supplier-performance issue you can see the day it starts, not at month end."

---

## 6. Proof and value (about 2 min) — slides 10 and 11

**Tell (scorecard)**
> "This is the scorecard against today's method. Precision triples and alert volume drops by almost four fifths. At an equal workload, planners catch about half as many again of the real stockouts. To be transparent about the trade-off: the old rule catches more stockouts in total because it flags five times as many items. The tiers are adjustable, so you choose the workload, and we would set the cut-off with your planners."

**Tell (value model)**
> "To size it, take the $10.8 million in lost sales and assume half comes back through substitution. The radar catches 38% of stockouts. If planners prevent half of those, that is about one million dollars a year in recovered sales on these 400 SKUs. It scales with the assortment you include. The second benefit is time: planners review one fifth as many alerts. I am not asking you to trust these assumptions. The pilot measures each one on your data."

---

## 7. Production readiness (about 1 min) — slide 12, aimed at the architect

> "For your team: one Databricks Asset Bundle deploys the pipeline, the job, the model, the Lakebase database and synced table, the Genie space, the dashboard and the app. Dev, test and prod run the same code from git. Unity Catalog holds lineage, tags and the KPI definitions. A governed view gives regional planners only their region and masks revenue exposure unless you are in finance. The app runs as its own service principal with least privilege and one-hour tokens, so there are no passwords anywhere. The model is versioned in MLflow, and the champion alias makes rollback one step."

---

## 8. Close and ask (about 1 min) — slides 13 and 14

> "Here is how we would prove it on your data: two regions, eight weeks. Weeks 1 and 2, we connect your feeds and measure today's baseline, so the targets are yours. Weeks 3 and 4, the radar runs in shadow mode against real stockouts. Weeks 5 to 8, your planners work the queue, and we track precision, stockout rate and time to action. At week 8 you decide on targets and roll-out with evidence in hand.
>
> To start, we need three things: your approval of the pilot; two planners and an hour a week from your planning lead; and read access to the five source feeds. Shall we put the week-1 kickoff on the calendar?"

---

## Questions and objections: business stakeholder (stay at executive altitude)

**"What does this cost?"**
> "The cost has two parts. The platform runs on serverless compute: the whole morning run is about 19 minutes of compute a day, plus a small Lakebase database that scales to zero when no one is using it. We will size the exact cost in week 1 from your billing tables, before you commit to roll-out. The second part is people: two planners and an hour a week from your planning lead during the pilot. Compared with roughly $1 million a year in recovered sales on 400 SKUs, the payback question is how many SKUs you include, not whether it pays back."

**"How quickly do we see value?"**
> "You see value in weeks, not quarters. In week 4 you have the shadow-mode comparison on your own stockouts. In week 8 you have measured results from live planner use. We start from a working build, not a blank page."

**"How confident are you in the million dollars?"**
> "The precision and recall come from a backtest that only uses information available at the time, so those are solid. The two assumptions are substitution and how many caught stockouts planners actually prevent. That is exactly what the pilot measures. If planners prevent 30% instead of 50%, it is about $600K. The case still holds."

**"What is the risk? What if it is wrong?"**
> "Three things keep the risk low. It never places an order; planners decide, and every decision and override is logged. It starts in shadow mode, so nothing changes until the alerts have proven themselves on your data. And if the model degrades, we roll back to the previous version in one step, or fall back to the baseline forecast it was measured against."

**"Will my planners actually use it?"**
> "Two reasons they will. First, it removes work: a fifth of the alerts, and each one shows its reason in units, so they don't have to rebuild the story in a spreadsheet. Second, they stay in control. They can override, and we track overrides to learn where the model needs to improve. We also measure time to action, so you can see adoption."

**"We already have a replenishment system in the ERP."**
> "Keep it. The ERP still places the orders. The radar sits on top and tells planners where the ERP's plan is about to fail: a late supplier, a promotion it didn't account for, a store with no open order. It reads from the ERP and writes nothing back during the pilot."

**"This is synthetic data. Why should I believe it?"**
> "That's a fair point. The data is synthetic on purpose, so no customer data was used. What carries over is the method and the build. The pilot reruns the same backtest on your history before anyone relies on it, and your baseline sets the targets."

## Questions and objections: technical stakeholder (go deeper, then return to the business point)

**"Walk me through the architecture."**
> "Raw feeds land in a Unity Catalog volume. A Lakeflow Declarative Pipeline turns them into bronze streaming tables with Auto Loader, silver tables with expectations, and gold materialized views for joins and aggregates. A job then trains or loads the champion LightGBM model, writes a 28-day forecast to Delta, computes risk scores, adds LLM notes through `ai_query`, applies governance and metric views, and refreshes a snapshot synced table into Lakebase. The Streamlit app reads that Postgres table and writes decisions to its own Postgres schema; the job copies those back into Delta. Everything is defined in one Databricks Asset Bundle." *Then return to the business point:* "For you, that means one platform to operate instead of five reports to reconcile."

**"How do you handle data quality?"**
> "Rules are declared in the pipeline: SKU and store must be present, units can't be negative, POs need a quantity, and duplicates are removed. Every pass and drop is in the event log. In this run that was 6,400 negative-unit rows, 2,500 rows without a SKU, 12,700 duplicates and 2,900 negative inventory snapshots. There is also a subtler issue: on a day that ends with zero on hand, sales understate demand. We exclude those censored days from training and from history averages. Otherwise the model learns to under-forecast exactly the items that run out."

**"Why LightGBM? How do you know it's better?"**
> "It's one global model across all 20,000 series, so it learns promotion, holiday and weekday effects shared across items, and you govern one model instead of 20,000. We compared it against a seasonal-naive baseline, which is what a spreadsheet does, on a 28-day time-based holdout covering every store, SKU and horizon. WAPE improved from 0.53 to 0.45, and from 0.55 to 0.40 on promotion days. Both runs are in MLflow, and the winner is registered in Unity Catalog with a champion alias."

**"How does the risk score work? Is it a black box?"**
> "No. It's deterministic and unit-tested. The window is the supplier's mean actual lead time over the last 30 days. Availability is on hand plus inbound, where each PO's arrival is shifted by that supplier's recent lateness, and overdue lines by their lateness when late. Stockout probability compares cumulative forecast demand with availability under a normal error model. Revenue at risk uses expected lost units. The drivers are the same quantities broken into units: uplift against baseline, delayed inbound, demand surge, and cover gap."

**"Can the LLM hallucinate?"**
> "It only rephrases. Every number in the prompt comes from the governed tables, the instruction forbids new numbers, and the action comes from the deterministic logic. If the endpoint returns nothing, a template is used instead. In this run all 400 notes came back complete."

**"Security and access?"**
> "Users sign in with SSO. The app runs as its own service principal with only the grants it needs, declared in the bundle: warehouse use, Lakebase connect, Genie run, and select on the tables it reads. Lakebase uses OAuth tokens that expire within an hour; there are no stored passwords. Consumers query a governed view that filters rows by region group and masks revenue unless the user is in finance. Tags follow your metastore's tag policies, and lineage is automatic."

**"Why Lakebase? Why not just query Delta from the app?"**
> "The app needs two things Delta isn't designed for: millisecond reads for an interactive queue (about 10 ms in this build) and many small transactional writes, like a planner saving a decision. Lakebase is managed Postgres on the same platform and identity. The read model is synced from Delta, so there is one source of truth, and decisions flow back to Delta for analytics."

**"How does it integrate with our systems?"**
> "On the way in: Lakeflow Connect or file and API ingestion from POS, ERP and WMS. The pilot needs five feeds. On the way out: nothing goes back during the pilot. Later, approved decisions could be written to the ERP as suggested POs or transfer requests through an API, still with a planner approving them."

**"How does it scale? What about 30,000 SKUs?"**
> "The pipeline is incremental, so only new files are processed each day. Training is one global model, and scoring is a batch job on serverless compute that scales with data volume. Going from 20,000 to a few million store/SKUs means more compute minutes, not a redesign. We would size it in week 1."

**"What about model drift and monitoring?"**
> "The job logs holdout WAPE and bias every time it trains. The metric views track live forecast error and alert precision. Retraining is a task in the same job, and the champion alias only moves when the challenger beats the current model. A drift alert on WAPE is a small addition for the pilot."

**"Vendor lock-in?"**
> "The data is Delta and Postgres, both open formats. The model is a standard LightGBM artifact in MLflow, and the code is Python and SQL in your git repository."

---

## Delivery reminders

- Open with the outcome, not the architecture.
- After each section, say what it means for the business.
- When the architect asks a deep question, answer in depth, then add one sentence for the VP ("which means...").
- When you name a number, say what it means: "62% precision, so six in ten alerts are real."
- Acknowledge the trade-off on recall before they raise it. It builds trust.
- End with a specific ask and a date.
