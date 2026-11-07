"""Unit tests for the transparent risk scoring (run locally: `uv run --with pandas,numpy,scipy,pytest pytest tests`)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "risk"))
from risk_logic import score  # noqa: E402


def _position(**over):
    base = dict(store_id="S001", sku_id="P1", store_name="Store 1", region="Coastal", sku_name="Milk", category="Dairy & Eggs",
                supplier_id="V1", supplier_name="Dairy Co", is_perishable=True, on_hand_units=10, r7=5.0, r28=5.0, r28_std=1.5,
                unit_price=3.0, case_pack=6, contract_lead_time_days=3, p90_lead_time_days=3, on_time_rate_last_30d=0.95)
    base.update(over)
    return base


def _forecast(store, sku, daily, promo_days=()):
    return pd.DataFrame([{"store_id": store, "sku_id": sku, "horizon": h, "forecast_units": daily * (2 if h in promo_days else 1),
                          "baseline_units": daily, "on_promo": int(h in promo_days), "days_to_next_holiday": 40} for h in range(1, 29)])


def test_promo_uplift_drives_high_risk_and_reorder():
    pos = pd.DataFrame([_position(), _position(store_id="S002", store_name="Store 2", on_hand_units=500)])
    fc = pd.concat([_forecast("S001", "P1", 5.0, promo_days=(1, 2, 3, 4)), _forecast("S002", "P1", 5.0)])
    inb = pd.DataFrame(columns=["store_id", "sku_id", "qty", "expected_day", "projected_day"])
    out = score(pos, fc, inb).set_index("store_id")
    risky, safe = out.loc["S001"], out.loc["S002"]
    assert risky.stockout_probability > 0.9
    assert risky.risk_tier in ("Critical", "High")
    assert risky.primary_driver == "Upcoming promotion"
    # store 2 in the same region has spare cover -> transfer recommended
    assert risky.recommended_action == "TRANSFER" and risky.action_source_id == "S002"
    assert safe.risk_tier == "Low" and safe.recommended_action == "MONITOR"


def test_late_supplier_triggers_expedite():
    pos = pd.DataFrame([_position(on_hand_units=8, on_time_rate_last_30d=0.4)])
    fc = _forecast("S001", "P1", 5.0)
    # 30 units expected on day 2 but supplier running ~5 days late -> projected day 7 (outside the 4-day window)
    inb = pd.DataFrame([{"store_id": "S001", "sku_id": "P1", "qty": 30, "expected_day": 2, "projected_day": 7}])
    out = score(pos, fc, inb).iloc[0]
    assert out.delayed_inbound_units == 30
    assert out.recommended_action == "EXPEDITE"
    assert "Late supplier delivery" in out.driver_details


def test_well_stocked_item_is_low_risk():
    pos = pd.DataFrame([_position(on_hand_units=200)])
    out = score(pos, _forecast("S001", "P1", 5.0), pd.DataFrame(columns=["store_id", "sku_id", "qty", "expected_day", "projected_day"])).iloc[0]
    assert out.stockout_probability < 0.01 and out.risk_score < 5 and out.recommended_action == "MONITOR"
    assert np.isnan(out.projected_stockout_in_days) or out.projected_stockout_in_days > 28
