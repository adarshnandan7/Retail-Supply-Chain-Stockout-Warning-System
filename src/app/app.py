"""Harvest Lane Markets - Inventory Risk Radar (planner app).

Ranked stockout risks with drivers and suggested actions; planners decide (expedite / transfer / reorder /
dismiss), and every decision, override and note is written to Lakebase. Nothing is ordered automatically.
"""
import os

import altair as alt
import pandas as pd
import streamlit as st

import backend as be

st.set_page_config(page_title="Inventory Risk Radar", page_icon="📦", layout="wide")

TIER_COLORS = {"Critical": "#B42318", "High": "#E8590C", "Medium": "#CA8A04", "Low": "#15803D"}
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")


def planner_identity() -> str:
    h = st.context.headers
    return h.get("X-Forwarded-Email") or h.get("X-Forwarded-Preferred-Username") or "planner@harvestlane.example"


@st.cache_resource(show_spinner=False)
def _init():
    be.init_app_schema()
    return True


@st.cache_data(ttl=60, show_spinner="Loading risk queue from Lakebase...")
def load_queue() -> pd.DataFrame:
    return be.risk_queue()


_init()
planner = planner_identity()
queue = load_queue()

# ---------------- header ----------------
st.title("📦 Inventory Risk Radar")
as_of = queue.as_of_date.max() if len(queue) else None
st.caption(f"Harvest Lane Markets · risk scored for business date **{as_of}** · signed in as **{planner}** · "
           "decision support only: nothing is ordered automatically")

with st.sidebar:
    st.header("Filters")
    regions = st.multiselect("Region", sorted(queue.region.unique()))
    cats = st.multiselect("Category", sorted(queue.category.unique()))
    tiers = st.multiselect("Risk tier", ["Critical", "High", "Medium"], default=["Critical", "High"])
    actions = st.multiselect("Suggested action", ["EXPEDITE", "TRANSFER", "REORDER"])
    drivers = st.multiselect("Primary driver", sorted(queue.primary_driver.unique()))
    hide_done = st.toggle("Hide items already actioned today", value=False)
    if st.button("Refresh data", use_container_width=True):
        load_queue.clear()
        st.rerun()
    if DASHBOARD_URL:
        st.link_button("Open AI/BI dashboard", DASHBOARD_URL, use_container_width=True)

q = queue.copy()
for col, sel in (("region", regions), ("category", cats), ("risk_tier", tiers), ("recommended_action", actions), ("primary_driver", drivers)):
    if sel:
        q = q[q[col].isin(sel)]
if hide_done:
    q = q[q.last_action.isna()]

crit_high = queue[queue.risk_tier.isin(["Critical", "High"])]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Critical", int((queue.risk_tier == "Critical").sum()))
k2.metric("High", int((queue.risk_tier == "High").sum()))
k3.metric("Revenue at risk (Critical+High)", f"${crit_high.revenue_at_risk.sum():,.0f}")
k4.metric("Stockouts projected ≤ 3 days", int((crit_high.projected_stockout_in_days <= 3).sum()))
k5.metric("Actioned", f"{int(crit_high.last_action.notna().sum())} / {len(crit_high)}")

tab_radar, tab_watch, tab_log, tab_genie = st.tabs(["🎯 Risk queue", "⭐ My watchlist", "🗂️ Action log & KPIs", "💬 Ask Genie"])

# ---------------- risk queue ----------------
with tab_radar:
    st.subheader(f"Ranked exceptions ({len(q):,})")
    view = q[["risk_rank", "risk_tier", "risk_score", "store_name", "sku_name", "category", "on_hand_units", "forecast_demand_window",
              "lead_time_window_days", "projected_stockout_in_days", "stockout_probability", "revenue_at_risk", "primary_driver",
              "recommended_action", "recommended_qty", "last_action"]].reset_index(drop=True)
    event = st.dataframe(
        view, hide_index=True, use_container_width=True, height=380, on_select="rerun", selection_mode="single-row",
        column_config={
            "risk_rank": st.column_config.NumberColumn("#", width="small"),
            "risk_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
            "stockout_probability": st.column_config.ProgressColumn("P(stockout)", min_value=0, max_value=1, format="%.2f"),
            "revenue_at_risk": st.column_config.NumberColumn("Revenue at risk", format="$%.0f"),
            "forecast_demand_window": st.column_config.NumberColumn("Forecast (window)", format="%.0f"),
            "lead_time_window_days": st.column_config.NumberColumn("Window (d)"),
            "projected_stockout_in_days": st.column_config.NumberColumn("Out in (d)", format="%.0f"),
            "on_hand_units": "On hand", "recommended_action": "Suggested", "recommended_qty": "Qty", "last_action": "Decision",
        })
    sel = event.selection.rows
    if not sel:
        st.info("Select a row to see why it is at risk, the projected stock path, and to record a decision.")
    else:
        row = q.iloc[sel[0]]
        st.divider()
        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"### {row.sku_name} · {row.store_name}")
            st.markdown(f"<span style='background:{TIER_COLORS[row.risk_tier]};color:white;padding:3px 10px;border-radius:12px'>"
                        f"{row.risk_tier} · {row.risk_score}/100</span> &nbsp; {row.category} · supplier {row.supplier_name} · region {row.region}",
                        unsafe_allow_html=True)
            st.markdown(f"> {row.planner_explanation}")
            st.markdown("**Quantified drivers**")
            for d in str(row.driver_details).split(" | "):
                st.markdown(f"- {d}")
            proj = be.item_projection(row.store_id, row.sku_id)
            if len(proj):
                proj["cum_forecast"] = proj.forecast_units.cumsum()
                proj["projected_on_hand"] = proj.on_hand_start + proj.inbound_units.cumsum() - proj.cum_forecast
                proj["usual_demand_path"] = proj.on_hand_start + proj.inbound_units.cumsum() - proj.baseline_units.cumsum()
                long = proj.melt(id_vars=["target_date"], value_vars=["projected_on_hand", "usual_demand_path"], var_name="series", value_name="units")
                long["series"] = long.series.map({"projected_on_hand": "Projected on hand (forecast)", "usual_demand_path": "If demand were 'usual'"})
                base = alt.Chart(long).mark_line(point=True).encode(
                    x=alt.X("target_date:T", title=None), y=alt.Y("units:Q", title="Units"), color=alt.Color("series:N", title=None,
                    scale=alt.Scale(range=["#1B5E9E", "#9AA4B2"])))
                zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#B42318", strokeDash=[4, 4]).encode(y="y:Q")
                window_end = proj.target_date.iloc[min(int(row.lead_time_window_days), len(proj)) - 1]
                wline = alt.Chart(pd.DataFrame({"x": [window_end]})).mark_rule(color="#666").encode(x="x:T")
                st.altair_chart((base + zero + wline).properties(height=260, title="Projected stock path, next 28 days (vertical line = replenishment window)"),
                                use_container_width=True)
            pos = be.open_pos(row.store_id, row.sku_id)
            st.markdown("**Open purchase orders**")
            st.dataframe(pos, hide_index=True, use_container_width=True) if len(pos) else st.caption("No open purchase orders for this item.")
        with right:
            st.markdown("#### Planner decision")
            st.markdown(f"Suggested: **{row.recommended_action} {row.recommended_qty} units** - {row.action_rationale}")
            with st.form(f"decide-{row.recommendation_id}", clear_on_submit=True):
                opts = ["EXPEDITE", "TRANSFER", "REORDER", "ACKNOWLEDGE", "DISMISS"]
                action = st.selectbox("Decision", opts, index=opts.index(row.recommended_action) if row.recommended_action in opts else 3)
                qty = st.number_input("Quantity (units)", min_value=0, value=int(row.recommended_qty), step=1)
                reason = st.text_input("Reason / override note", placeholder="e.g. DC confirmed truck tomorrow; transfer from nearby store instead")
                if st.form_submit_button("Save decision", type="primary", use_container_width=True):
                    be.record_action(row, action, int(qty) if action not in ("ACKNOWLEDGE", "DISMISS") else None, reason, planner)
                    load_queue.clear()
                    st.success("Decision saved to Lakebase.")
            watched = row.recommendation_id in set(be.watchlist(planner).recommendation_id)
            on_list = st.toggle("On my watchlist", value=watched, key=f"w-{row.recommendation_id}")
            if on_list != watched:
                be.toggle_watch(planner, row.recommendation_id, on_list)
            st.markdown("#### Notes")
            with st.form(f"note-{row.recommendation_id}", clear_on_submit=True):
                note = st.text_area("Add a note", height=80)
                if st.form_submit_button("Add note") and note.strip():
                    be.add_note(row.recommendation_id, planner, note.strip())
            st.dataframe(be.notes(row.recommendation_id), hide_index=True, use_container_width=True)

# ---------------- watchlist ----------------
with tab_watch:
    wl = be.watchlist(planner)
    if len(wl):
        st.dataframe(wl, hide_index=True, use_container_width=True)
        rm = st.selectbox("Remove from watchlist", [""] + wl.recommendation_id.tolist())
        if rm and st.button("Remove"):
            be.toggle_watch(planner, rm, False)
            st.rerun()
    else:
        st.info("Your watchlist is empty. Toggle 'On my watchlist' on any item in the risk queue.")

# ---------------- action log & KPIs ----------------
with tab_log:
    kp = be.action_kpis()
    if len(kp):
        r = kp.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Critical/High alerts", int(r.critical_high_alerts or 0))
        c2.metric("Actioned", f"{int(r.actioned or 0)} ({r.pct_actioned or 0}%)")
        c3.metric("Median time to planner action", f"{r.median_hours_to_action or 0} h")
    log = be.action_log()
    st.dataframe(log, hide_index=True, use_container_width=True)
    if len(log):
        st.caption(f"Overrides of the suggested action: {int(log.is_override.sum())} of {len(log)} decisions")

# ---------------- Genie ----------------
with tab_genie:
    st.markdown("Ask questions about stockout risk, forecasts and supplier performance in plain English. "
                "Answers come from Genie over the governed Unity Catalog tables.")
    examples = ["Which 10 store-SKUs have the highest revenue at risk this week?",
                "How many critical risks are driven by late supplier deliveries, by supplier?",
                "What is the forecast error (WAPE) of the model vs the baseline by category?",
                "Which region has the most items projected to stock out within 3 days?"]
    ex = st.selectbox("Try an example", [""] + examples)
    question = st.chat_input("Ask Genie about inventory risk...") or ex
    if question:
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"), st.spinner("Genie is thinking..."):
            ans = be.ask_genie(question, st.session_state.get("genie_conv"))
            if ans.get("error"):
                st.error(ans["error"])
            else:
                st.session_state["genie_conv"] = ans["conversation_id"]
                if ans.get("text"):
                    st.write(ans["text"])
                if ans.get("description"):
                    st.write(ans["description"])
                if ans.get("table") is not None:
                    st.dataframe(ans["table"], hide_index=True, use_container_width=True)
                if ans.get("sql"):
                    with st.expander("Generated SQL"):
                        st.code(ans["sql"], language="sql")
