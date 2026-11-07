"""Transparent inventory-risk scoring (pure pandas so every step is inspectable and unit-testable).

For each store/SKU at forecast origin `o`:

1. Replenishment window W = mean actual supplier lead time over the last 30 days (rounded up, min 2 days):
   "Will this item run out before an order placed today would arrive, given how the supplier is performing now?"
2. Projected availability by day h = on hand + inbound units whose *projected* arrival is on or before day h.
   Lines not yet due are shifted by the supplier's recent average delay; lines already overdue are shifted by
   the supplier's recent average lateness *when late* (they are known to be late).
3. Cumulative forecast demand by day h from the @champion model.
4. Stockout probability = max over h <= W of P(demand_1..h > available_h), with demand ~ Normal(cum forecast,
   sigma_daily * sqrt(h)), sigma_daily from recent non-stockout sales variability (Poisson floor).
5. Expected lost units at W (normal loss function) x unit price = revenue at risk.
6. Risk score (0-100) = 100 x stockout probability x (0.6 + 0.4 x value weight), value weight = revenue at risk
   relative to the 95th percentile, capped at 1. Tiers: Critical >= 70, High >= 45, Medium >= 25, else Low.
7. Drivers are quantified in units so planners can see *why*: forecast uplift vs. the seasonal-naive baseline
   (promotion / holiday ramp / demand trend), inbound units delayed past the window by a late supplier,
   recent demand surge, and structural cover gap (not enough stock or no open PO even at baseline demand).
8. Recommended action (decision support only, nothing is ordered automatically):
   EXPEDITE when late inbound units exist and the item is projected to run out before they arrive, TRANSFER when a store in the same region has spare
   cover, otherwise REORDER (case-pack rounded); MONITOR for Low tier.
"""
import math

import numpy as np
import pandas as pd
from scipy.stats import norm

H = 28
TIERS = [(70, "Critical"), (45, "High"), (25, "Medium"), (0, "Low")]


def _matrix(df: pd.DataFrame, keys: pd.MultiIndex, col: str) -> np.ndarray:
    """Pivot long (store, sku, horizon) rows into a dense series x 28 matrix aligned to `keys`."""
    m = df.pivot_table(index=["store_id", "sku_id"], columns="horizon", values=col, aggfunc="sum")
    m = m.reindex(index=keys, columns=range(1, H + 1)).fillna(0.0)
    return m.to_numpy(dtype=float)


def score(position: pd.DataFrame, forecast: pd.DataFrame, inbound: pd.DataFrame) -> pd.DataFrame:
    """position: one row per store/SKU (on hand, sales stats, supplier stats, product attributes).
    forecast: store_id, sku_id, horizon, forecast_units, baseline_units, on_promo, days_to_next_holiday.
    inbound: open PO lines at origin with projected_day / expected_day offsets (days after origin) and qty.
    """
    pos = position.set_index(["store_id", "sku_id"]).sort_index()
    keys = pos.index
    F_ = _matrix(forecast, keys, "forecast_units")
    B_ = _matrix(forecast, keys, "baseline_units")
    P_ = _matrix(forecast, keys, "on_promo") > 0
    hol1 = forecast[forecast.horizon == 1].set_index(["store_id", "sku_id"])["days_to_next_holiday"].reindex(keys).fillna(99).to_numpy()

    inb = inbound.copy()
    inb["proj_day"] = inb["projected_day"].clip(lower=1)
    inb["exp_day"] = inb["expected_day"].clip(lower=1)
    inb["is_late"] = (inb["expected_day"] <= 0) | (inb["projected_day"] > inb["expected_day"])
    in_proj = np.zeros_like(F_)
    in_exp = np.zeros_like(F_)
    for col, mat in (("proj_day", in_proj), ("exp_day", in_exp)):
        sub = inb[inb[col].between(1, H)]
        if len(sub):
            m = sub.pivot_table(index=["store_id", "sku_id"], columns=col, values="qty", aggfunc="sum").reindex(
                index=keys, columns=range(1, H + 1)).fillna(0.0)
            mat += m.to_numpy(dtype=float)
    overdue_lines = inb[inb["expected_day"] <= 0].groupby(["store_id", "sku_id"]).size().reindex(keys).fillna(0).to_numpy()
    inbound_total = inb.groupby(["store_id", "sku_id"])["qty"].sum().reindex(keys).fillna(0).to_numpy()
    next_arrival = inb.groupby(["store_id", "sku_id"])["proj_day"].min().reindex(keys).to_numpy()
    late = inb[inb.is_late]

    on_hand = pos["on_hand_units"].fillna(0).to_numpy(dtype=float)
    lt = pos["avg_lead_time_30d"].fillna(pos["contract_lead_time_days"]).to_numpy(dtype=float)
    W = np.clip(np.ceil(lt), 2, H).astype(int)
    r28 = pos["r28"].fillna(0).to_numpy(dtype=float)
    r7 = pos["r7"].fillna(0).to_numpy(dtype=float)
    sigma_d = np.maximum(pos["r28_std"].fillna(0).to_numpy(dtype=float), np.sqrt(np.maximum(r28, 0.1)))
    price = pos["unit_price"].astype(float).to_numpy()
    case = pos["case_pack"].fillna(1).to_numpy(dtype=float)

    hs = np.arange(1, H + 1)
    cumF, cumB = F_.cumsum(1), B_.cumsum(1)
    avail = on_hand[:, None] + in_proj.cumsum(1)
    within = hs[None, :] <= W[:, None]
    sig_h = sigma_d[:, None] * np.sqrt(hs)[None, :]
    p_h = 1 - norm.cdf((avail - cumF + 0.5) / sig_h)
    p = np.where(within, p_h, 0).max(1)
    gap = np.where(within, cumF - avail, -np.inf).max(1)
    shortfall = np.maximum(gap, 0)

    idx = np.arange(len(keys))
    w_i = W - 1
    mu_W, avail_W, sig_W = cumF[idx, w_i], avail[idx, w_i], sig_h[idx, w_i]
    z = (avail_W - mu_W) / sig_W
    exp_lost = sig_W * (norm.pdf(z) - z * (1 - norm.cdf(z)))
    rev_at_risk = exp_lost * price
    ref = max(np.quantile(rev_at_risk, 0.95), 1e-6)
    value_w = np.minimum(rev_at_risk / ref, 1.0)
    risk_score = np.round(100 * p * (0.6 + 0.4 * value_w)).astype(int)
    tier = np.select([risk_score >= t for t, _ in TIERS[:-1]], [n for _, n in TIERS[:-1]], default="Low")

    first_out = np.where((cumF >= avail).any(1), (cumF >= avail).argmax(1) + 1, -1)
    fwd7 = F_[:, :7].mean(1)
    days_cover = np.round(on_hand / np.maximum(fwd7, 0.05), 1)

    # ---- quantified drivers (units over the window) ----
    uplift = cumF[idx, w_i] - cumB[idx, w_i]
    promo_in_w = np.where(within, P_, False).any(1)
    holiday_in_w = hol1 <= (W + 2)
    exp_cum_W = in_exp.cumsum(1)[idx, w_i]
    proj_cum_W = in_proj.cumsum(1)[idx, w_i]
    # late units the plan was counting on inside the window, and when they are now projected to land
    late_w = late.merge(pd.DataFrame({"store_id": keys.get_level_values(0), "sku_id": keys.get_level_values(1), "W": W}),
                        on=["store_id", "sku_id"])
    late_w = late_w[late_w.exp_day <= late_w.W]
    delayed = late_w.groupby(["store_id", "sku_id"])["qty"].sum().reindex(keys).fillna(0).to_numpy(dtype=float)
    late_arrival = late_w.groupby(["store_id", "sku_id"])["proj_day"].min().reindex(keys).to_numpy(dtype=float)
    surge = np.where(r7 > 1.25 * r28, (r7 - r28) * W, 0)
    struct_gap = np.maximum(cumB[idx, w_i] - (on_hand + exp_cum_W), 0)

    sup_ot = pos["on_time_rate_last_30d"].to_numpy(dtype=float)
    drivers, primary = [], []
    for i in range(len(keys)):
        d = []
        if uplift[i] > 0.5:
            label = "Upcoming promotion" if promo_in_w[i] else ("Holiday demand ramp" if holiday_in_w[i] else "Demand trend above baseline")
            d.append((label, uplift[i], f"{label}: forecast +{uplift[i]:.0f} units vs. usual over the next {W[i]} days"))
        if delayed[i] > 0 or overdue_lines[i] > 0:
            ot = "" if np.isnan(sup_ot[i]) else f", supplier on-time {sup_ot[i]:.0%} last 30d"
            d.append(("Late supplier delivery", max(delayed[i], 1.0), f"Late supplier delivery: {delayed[i]:.0f} inbound units are late; now projected in {0 if np.isnan(late_arrival[i]) else int(late_arrival[i])} days ({int(overdue_lines[i])} PO lines overdue{ot})"))
        if surge[i] > 0.5:
            d.append(("Recent demand surge", surge[i], f"Recent demand surge: last 7 days {r7[i]:.1f}/day vs. 28-day {r28[i]:.1f}/day"))
        if struct_gap[i] > 0.5:
            lbl = "No open purchase order" if inbound_total[i] == 0 else "Insufficient stock cover"
            d.append((lbl, struct_gap[i], f"{lbl}: on hand {on_hand[i]:.0f} + inbound covers less than usual demand ({cumB[idx, w_i][i]:.0f} units)"))
        d.sort(key=lambda x: -x[1])
        primary.append(d[0][0] if d else "Normal variability")
        drivers.append(" | ".join(x[2] for x in d) if d else "No dominant driver; risk reflects normal demand variability")

    out = pos.reset_index()[["store_id", "sku_id"]].copy()
    for c in ["store_name", "region", "sku_name", "category", "supplier_id", "supplier_name", "is_perishable"]:
        out[c] = pos[c].to_numpy()
    out["on_hand_units"] = on_hand.astype(int)
    out["inbound_units_total"] = inbound_total.astype(int)
    out["inbound_units_in_window"] = proj_cum_W.astype(int)
    out["next_inbound_in_days"] = next_arrival
    out["lead_time_window_days"] = W
    out["forecast_demand_window"] = np.round(mu_W, 1)
    out["baseline_demand_window"] = np.round(cumB[idx, w_i], 1)
    out["avg_daily_units_28d"] = np.round(r28, 2)
    out["days_of_cover"] = days_cover
    out["projected_stockout_in_days"] = np.where(first_out > 0, first_out, np.nan)
    out["stockout_probability"] = np.round(p, 4)
    out["expected_shortfall_units"] = np.round(shortfall, 1)
    out["expected_lost_units"] = np.round(exp_lost, 2)
    out["revenue_at_risk"] = np.round(rev_at_risk, 2)
    out["unit_price"] = price
    out["case_pack"] = case.astype(int)
    out["risk_score"] = risk_score
    out["risk_tier"] = tier
    out["primary_driver"] = primary
    out["driver_details"] = drivers
    out["on_promo_in_window"] = promo_in_w
    out["supplier_on_time_rate_30d"] = sup_ot
    out["open_po_overdue_lines"] = overdue_lines.astype(int)
    out["forecast_uplift_units"] = np.round(uplift, 1)
    out["delayed_inbound_units"] = np.round(delayed, 1)
    out["late_inbound_arrival_in_days"] = late_arrival

    # spare units per series for transfers: on hand beyond forecast need for its own window + 7 days safety
    need_self = cumF[idx, np.minimum(w_i + 7, H - 1)] + 1.28 * sig_h[idx, np.minimum(w_i + 7, H - 1)]
    out["spare_units"] = np.floor(np.maximum(on_hand + proj_cum_W - need_self, 0))
    return _actions(out, sig_W)


def _actions(out: pd.DataFrame, sig_W: np.ndarray) -> pd.DataFrame:
    donors = (out[out.risk_tier.isin(["Low"]) & (out.spare_units > 0)]
              .sort_values("spare_units", ascending=False)
              .drop_duplicates(["region", "sku_id"])[["region", "sku_id", "store_id", "store_name", "spare_units"]]
              .rename(columns={"store_id": "donor_store_id", "store_name": "donor_store_name", "spare_units": "donor_spare"}))
    o = out.merge(donors, on=["region", "sku_id"], how="left")
    need = np.ceil(np.maximum(o.expected_shortfall_units, 0) + 0.5 * sig_W)
    action, qty, src = [], [], []
    for i, r in o.iterrows():
        if r.risk_tier == "Low":
            action.append("MONITOR"); qty.append(0); src.append(None); continue
        n = max(need[i], r.case_pack)
        runs_out_first = pd.notna(r.projected_stockout_in_days) and pd.notna(r.late_inbound_arrival_in_days) and \
            r.projected_stockout_in_days <= r.late_inbound_arrival_in_days
        if r.delayed_inbound_units > 0 and runs_out_first:
            action.append("EXPEDITE"); qty.append(int(r.delayed_inbound_units)); src.append(r.supplier_id)
        elif pd.notna(r.donor_store_id) and r.donor_store_id != r.store_id and r.donor_spare >= min(n, r.case_pack):
            action.append("TRANSFER"); qty.append(int(min(n, r.donor_spare))); src.append(r.donor_store_id)
        else:
            action.append("REORDER"); qty.append(int(math.ceil(n / r.case_pack) * r.case_pack)); src.append(r.supplier_id)
    o["recommended_action"] = action
    o["recommended_qty"] = qty
    o["action_source_id"] = src
    o["action_rationale"] = [
        {"EXPEDITE": f"Ask {r.supplier_name} to expedite delayed PO units",
         "TRANSFER": f"Transfer from {r.donor_store_name} (spare {0 if pd.isna(r.donor_spare) else int(r.donor_spare)} units)",
         "REORDER": f"Place additional order with {r.supplier_name} (case pack {r.case_pack})",
         "MONITOR": "No action needed"}[a] for a, (_, r) in zip(action, o.iterrows())]
    return o.drop(columns=["donor_store_id", "donor_store_name", "donor_spare"])
