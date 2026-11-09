# Task `generate_raw_data` - SUCCESS
- Task run id: `1125512045038137`
- Notebook: `/Workspace/Users/adarsh.nandan@databricks.com/.bundle/retail_inventory_risk_radar/dev/files/src/datagen/generate_raw_data`
- Duration: 228 s

## Cell 1

```markdown
%md
# 01 - Synthetic raw data for Harvest Lane Markets

Generates the raw file drops that a multi-store grocer's source systems would land in cloud storage:

| Source system | Feed | Format | Landing folder |
|---|---|---|---|
| Merchandising | product master | CSV | `landing/products/` |
| Store ops | store master | CSV | `landing/stores/` |
| Purchasing | supplier master + contract lead times | CSV | `landing/suppliers/` |
| POS | daily store-SKU sales | CSV (monthly drops) | `landing/sales/` |
| Inventory mgmt | end-of-day on-hand snapshots | JSON lines (monthly drops) | `landing/inventory/` |
| Purchasing / ERP | purchase-order events (CREATED, RECEIVED) | JSON lines | `landing/purchase_orders/` |
| Marketing | promotion calendar (incl. next 4 weeks) | CSV | `landing/promotions/` |
| Calendar | holidays | CSV | `landing/calendar/` |

The simulation runs a day-by-day replenishment loop with a deliberately naive reorder policy
(trailing 28-day average, contract lead time, no promo or holiday awareness). That is how many
grocers still replenish, and it produces realistic stockouts around promotions, holiday ramps and
late supplier deliveries. A small share of defective records is planted so the Lakeflow
expectations have something to catch.
```

## Cell 2

```python
dbutils.widgets.text("catalog", "serverless_stable_3vku19_catalog")
dbutils.widgets.text("schema", "inventory_risk")
dbutils.widgets.text("as_of_date", "2026-11-06")
dbutils.widgets.text("seed", "42")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
AS_OF = dbutils.widgets.get("as_of_date")
SEED = int(dbutils.widgets.get("seed"))
LANDING = f"/Volumes/{CATALOG}/{SCHEMA}/landing"
EVIDENCE = f"/Volumes/{CATALOG}/{SCHEMA}/evidence"
print(f"Landing path: {LANDING} | as_of_date: {AS_OF} | seed: {SEED}")
```

**Output**

```text
Landing path: /Volumes/serverless_stable_3vku19_catalog/inventory_risk/landing | as_of_date: 2026-11-06 | seed: 42
```

## Cell 3

```python
import os, shutil, json, math
import numpy as np
import pandas as pd

rng = np.random.default_rng(SEED)
N_STORES, N_SKUS = 50, 400
HIST_DAYS = 730
as_of = pd.Timestamp(AS_OF)
start = as_of - pd.Timedelta(days=HIST_DAYS - 1)
dates = pd.date_range(start, as_of, freq="D")
FUTURE_DAYS = 35
future_dates = pd.date_range(as_of + pd.Timedelta(days=1), periods=FUTURE_DAYS, freq="D")
print(f"History {dates[0].date()} -> {dates[-1].date()} ({len(dates)} days); future promo horizon to {future_dates[-1].date()}")
```

**Output**

```text
History 2024-11-07 -> 2026-11-06 (730 days); future promo horizon to 2026-12-11
```

## Cell 4

```markdown
%md ## Master data: stores, suppliers, products
```

## Cell 5

```python
regions = ["Metro North", "Metro South", "Coastal", "Valley", "Lakeshore"]
formats = [("Superstore", 1.8, 0.15), ("Standard", 1.0, 0.55), ("Neighborhood", 0.6, 0.20), ("Express", 0.35, 0.10)]
town_names = ["Ashford", "Brookvale", "Cedar Point", "Dunmore", "Elmwood", "Fairhaven", "Glenrock", "Hillcrest", "Ironbridge",
              "Juniper Bay", "Kingsley", "Larkspur", "Maple Ridge", "Northgate", "Oakhurst", "Pinewood", "Quarry Hill",
              "Riverside", "Stonebrook", "Thornbury", "Upton", "Violet Springs", "Westfield", "Yarrow", "Zephyr Cove"]
stores = []
for i in range(N_STORES):
    fmt = rng.choice(len(formats), p=[f[2] for f in formats])
    region = regions[i % len(regions)]
    town = town_names[i % len(town_names)]
    stores.append({
        "store_id": f"S{i+1:03d}",
        "store_name": f"Harvest Lane {town} {formats[fmt][0]}" + ("" if i < len(town_names) else " II"),
        "region": region,
        "format": formats[fmt][0],
        "size_factor": round(float(formats[fmt][1] * rng.uniform(0.85, 1.15)), 3),
        "opened_date": str((start - pd.Timedelta(days=int(rng.integers(400, 6000)))).date()),
    })
stores_df = pd.DataFrame(stores)

# category: (perishable, base demand median, price range, contract LT range, review cycle, season amplitude, season peak doy, holiday sensitivity, promo elasticity)
categories = {
    "Fresh Produce":   (True,  9.0, (0.8, 6.0),  (2, 3),  3, 0.15, 200, 1.25, 1.6),
    "Dairy & Eggs":    (True,  8.0, (1.5, 7.0),  (2, 4),  3, 0.05, 30,  1.35, 1.4),
    "Bakery":          (True,  6.0, (2.0, 8.0),  (1, 2),  2, 0.05, 340, 1.60, 1.5),
    "Meat & Seafood":  (True,  4.0, (5.0, 25.0), (2, 4),  3, 0.10, 190, 1.80, 1.8),
    "Frozen":          (False, 3.5, (3.0, 12.0), (5, 8),  7, 0.20, 210, 1.20, 1.7),
    "Pantry & Baking": (False, 3.0, (1.5, 9.0),  (7, 12), 10, 0.10, 330, 1.70, 1.5),
    "Beverages":       (False, 6.0, (1.0, 10.0), (5, 10), 7, 0.30, 200, 1.30, 1.9),
    "Snacks":          (False, 4.5, (1.5, 6.0),  (7, 12), 10, 0.10, 220, 1.30, 2.0),
    "Household":       (False, 1.8, (3.0, 15.0), (10, 18), 14, 0.05, 90,  1.05, 1.4),
    "Personal Care":   (False, 1.5, (2.5, 14.0), (10, 18), 14, 0.05, 90,  1.05, 1.4),
}
cat_words = {
    "Fresh Produce": ["Bananas", "Gala Apples", "Avocados", "Baby Spinach", "Strawberries", "Russet Potatoes", "Yellow Onions", "Carrots", "Romaine Hearts", "Blueberries", "Lemons", "Sweet Potatoes", "Cranberries", "Celery", "Green Beans"],
    "Dairy & Eggs": ["Whole Milk", "2% Milk", "Large Eggs", "Greek Yogurt", "Butter", "Cheddar Block", "Heavy Cream", "Sour Cream", "Cream Cheese", "Oat Milk", "Mozzarella", "Cottage Cheese"],
    "Bakery": ["Sourdough Loaf", "Dinner Rolls", "Bagels", "Croissants", "Pie Crust", "Whole Wheat Bread", "Muffins", "Baguette", "Pumpkin Pie", "Brioche Buns"],
    "Meat & Seafood": ["Whole Turkey", "Chicken Breast", "Ground Beef", "Pork Chops", "Salmon Fillet", "Bacon", "Ham", "Shrimp", "Chicken Thighs", "Sirloin Steak"],
    "Frozen": ["Frozen Peas", "Ice Cream", "Frozen Pizza", "Frozen Berries", "Fish Sticks", "Frozen Waffles", "Frozen Corn", "Veggie Burgers"],
    "Pantry & Baking": ["All-Purpose Flour", "Granulated Sugar", "Brown Sugar", "Canned Pumpkin", "Stuffing Mix", "Chicken Broth", "Gravy Mix", "Cranberry Sauce", "Pasta", "Rice", "Olive Oil", "Baking Soda", "Chocolate Chips", "Peanut Butter"],
    "Beverages": ["Sparkling Water", "Orange Juice", "Cola 12pk", "Cold Brew Coffee", "Apple Cider", "Lemonade", "Sports Drink", "Ground Coffee", "Green Tea"],
    "Snacks": ["Tortilla Chips", "Potato Chips", "Pretzels", "Mixed Nuts", "Granola Bars", "Crackers", "Popcorn", "Trail Mix"],
    "Household": ["Paper Towels", "Toilet Paper", "Dish Soap", "Laundry Detergent", "Trash Bags", "Aluminum Foil", "Sponges", "All-Purpose Cleaner"],
    "Personal Care": ["Toothpaste", "Shampoo", "Body Wash", "Deodorant", "Hand Soap", "Lip Balm", "Cotton Swabs", "Sunscreen"],
}
brands = ["Harvest Lane", "Green Valley", "Sunrise", "Meadow Fresh", "Blue Harbor", "Golden Fields", "Crestline", "Prairie Co."]

cat_names = list(categories.keys())
cat_weights = np.array([0.15, 0.12, 0.07, 0.08, 0.09, 0.14, 0.11, 0.09, 0.08, 0.07])

suppliers = []
sid = 0
cat_suppliers = {}
for c in cat_names:
    n_sup = 3 if categories[c][0] else 2
    cat_suppliers[c] = []
    lt_lo, lt_hi = categories[c][3]
    for j in range(n_sup):
        sid += 1
        on_time = float(rng.uniform(0.72, 0.97))
        suppliers.append({
            "supplier_id": f"V{sid:03d}",
            "supplier_name": f"{rng.choice(['Northern', 'Pacific', 'Heartland', 'Summit', 'Riverbend', 'Evergreen', 'Atlas', 'Keystone'])} {c.split(' ')[0]} {rng.choice(['Distributors', 'Foods', 'Supply Co.', 'Wholesale'])}",
            "primary_category": c,
            "contract_lead_time_days": int(rng.integers(lt_lo, lt_hi + 1)),
            "on_time_rate_target": round(on_time, 3),
            "mean_delay_when_late_days": round(float(rng.uniform(1.0, 4.0)), 2),
            "min_order_cases": int(rng.integers(1, 4)),
        })
        cat_suppliers[c].append(len(suppliers) - 1)
suppliers_df = pd.DataFrame(suppliers)

# Current disruption: one dairy and one pantry supplier are running late in the last 3 weeks
disrupted = [cat_suppliers["Dairy & Eggs"][0], cat_suppliers["Pantry & Baking"][1]]

products = []
sku_cat = rng.choice(len(cat_names), size=N_SKUS, p=cat_weights / cat_weights.sum())
for k in range(N_SKUS):
    c = cat_names[sku_cat[k]]
    perishable, base_med, (p_lo, p_hi), _, _, _, _, _, _ = categories[c]
    item = rng.choice(cat_words[c])
    brand = rng.choice(brands)
    size = rng.choice(["", " Family Size", " Organic", " Value Pack", " 2ct", " Large"])
    price = round(float(rng.uniform(p_lo, p_hi)), 2)
    sup_idx = int(rng.choice(cat_suppliers[c]))
    products.append({
        "sku_id": f"P{k+1:05d}",
        "sku_name": f"{brand} {item}{size}",
        "category": c,
        "subcategory": item,
        "brand": brand,
        "is_perishable": perishable,
        "shelf_life_days": int(rng.integers(4, 15)) if perishable else int(rng.integers(90, 720)),
        "unit_price": price,
        "unit_cost": round(price * float(rng.uniform(0.55, 0.75)), 2),
        "case_pack": int(rng.choice([6, 12, 12, 24])) if not perishable else int(rng.choice([4, 6, 12])),
        "supplier_id": suppliers[sup_idx]["supplier_id"],
        "_sup_idx": sup_idx,
        "_base": float(base_med * rng.lognormal(0, 0.55)),
    })
products_df = pd.DataFrame(products)
print(stores_df["format"].value_counts().to_dict())
print(products_df["category"].value_counts().to_dict())
```

**Output**

```text
{'Standard': 30, 'Neighborhood': 11, 'Superstore': 6, 'Express': 3}
{'Fresh Produce': 68, 'Pantry & Baking': 61, 'Snacks': 46, 'Beverages': 37, 'Dairy & Eggs': 36, 'Frozen': 35, 'Bakery': 31, 'Household': 31, 'Meat & Seafood': 28, 'Personal Care': 27}
```

## Cell 6

```markdown
%md ## Calendar, holidays, promotions
```

## Cell 7

```python
holidays = [
    ("2024-11-28", "Thanksgiving"), ("2024-12-25", "Christmas"), ("2025-01-01", "New Year"), ("2025-04-20", "Easter"),
    ("2025-05-26", "Memorial Day"), ("2025-07-04", "Independence Day"), ("2025-09-01", "Labor Day"),
    ("2025-11-27", "Thanksgiving"), ("2025-12-25", "Christmas"), ("2026-01-01", "New Year"), ("2026-04-05", "Easter"),
    ("2026-05-25", "Memorial Day"), ("2026-07-04", "Independence Day"), ("2026-09-07", "Labor Day"),
    ("2026-11-26", "Thanksgiving"), ("2026-12-25", "Christmas"),
]
holidays_df = pd.DataFrame(holidays, columns=["holiday_date", "holiday_name"])
holiday_strength = {"Thanksgiving": 1.0, "Christmas": 0.9, "Easter": 0.5, "Independence Day": 0.45, "Memorial Day": 0.35, "Labor Day": 0.35, "New Year": 0.3}
# Thanksgiving-heavy categories get extra lift (turkey, baking, produce, bakery)
thanksgiving_cats = {"Meat & Seafood", "Pantry & Baking", "Bakery", "Fresh Produce", "Dairy & Eggs"}

all_days = dates.append(future_dates)
D_ALL = len(all_days)
day_idx = {d: i for i, d in enumerate(all_days)}

# holiday ramp multiplier per (day, category): pre-holiday 6 days ramp, post-holiday dip
hol_mult = np.ones((D_ALL, len(cat_names)), dtype=np.float32)
for hd, hn in holidays:
    hd = pd.Timestamp(hd)
    for offset in range(-6, 2):
        d = hd + pd.Timedelta(days=offset)
        if d not in day_idx:
            continue
        i = day_idx[d]
        ramp = {-6: 0.15, -5: 0.2, -4: 0.3, -3: 0.45, -2: 0.7, -1: 0.9, 0: -0.4, 1: -0.2}[offset]
        for ci, c in enumerate(cat_names):
            sens = categories[c][7] - 1.0
            extra = 1.6 if (hn == "Thanksgiving" and c in thanksgiving_cats) else 1.0
            hol_mult[i, ci] *= max(0.3, 1.0 + ramp * sens * holiday_strength[hn] * extra * 2.0)

# Promotions: region- or chain-wide, 7 days, ~every 10 weeks per SKU, including upcoming ones
promos = []
pid = 0
promo_days = []  # (sku, region_or_ALL, start_idx, end_idx, discount, uplift)
for k in range(N_SKUS):
    c = cat_names[sku_cat[k]]
    elasticity = categories[c][8]
    t = int(rng.integers(0, 70))
    while t < D_ALL:
        dur = 7
        discount = float(rng.choice([0.10, 0.15, 0.20, 0.25, 0.30]))
        uplift = 1.0 + elasticity * discount * float(rng.uniform(2.5, 4.5))
        scope = "ALL" if rng.random() < 0.35 else regions[int(rng.integers(0, len(regions)))]
        pid += 1
        s_i, e_i = t, min(t + dur - 1, D_ALL - 1)
        promos.append({
            "promo_id": f"PR{pid:06d}", "sku_id": f"P{k+1:05d}", "scope": scope,
            "start_date": str(all_days[s_i].date()), "end_date": str(all_days[e_i].date()),
            "discount_pct": discount, "promo_type": rng.choice(["Weekly Circular", "Digital Coupon", "BOGO", "Endcap Feature"]),
            "planned_uplift_hint": round(uplift, 2),
        })
        promo_days.append((k, scope, s_i, e_i, discount, uplift))
        t += int(rng.integers(50, 90))

# Force a few high-impact upcoming promos on Thanksgiving-relevant SKUs (the planners' current blind spot)
tg_skus = [k for k in range(N_SKUS) if cat_names[sku_cat[k]] in thanksgiving_cats]
for k in rng.choice(tg_skus, size=25, replace=False):
    s_i = HIST_DAYS + int(rng.integers(3, 12))
    e_i = s_i + 6
    discount = float(rng.choice([0.20, 0.25, 0.30]))
    uplift = 1.0 + categories[cat_names[sku_cat[k]]][8] * discount * 4.0
    scope = "ALL" if rng.random() < 0.5 else regions[int(rng.integers(0, len(regions)))]
    pid += 1
    promos.append({"promo_id": f"PR{pid:06d}", "sku_id": f"P{k+1:05d}", "scope": scope,
                   "start_date": str(all_days[s_i].date()), "end_date": str(all_days[e_i].date()),
                   "discount_pct": discount, "promo_type": "Holiday Feature", "planned_uplift_hint": round(uplift, 2)})
    promo_days.append((k, scope, s_i, e_i, discount, uplift))
promos_df = pd.DataFrame(promos)
print(f"{len(promos_df)} promotions, {int((pd.to_datetime(promos_df.start_date) > as_of).sum())} upcoming")
```

**Output**

```text
4433 promotions, 226 upcoming
```

## Cell 8

```markdown
%md ## Day-by-day demand and replenishment simulation (store x SKU)
```

## Cell 9

```python
S, K = N_STORES, N_SKUS
N = S * K
store_of = np.repeat(np.arange(S), K)
sku_of = np.tile(np.arange(K), S)
store_region = np.array([regions.index(r) for r in stores_df["region"]])
region_of = store_region[store_of]
cat_of = sku_cat[sku_of]

base = products_df["_base"].to_numpy()[sku_of] * stores_df["size_factor"].to_numpy()[store_of] * rng.lognormal(0, 0.25, N)
price = products_df["unit_price"].to_numpy()[sku_of]
case_pack = products_df["case_pack"].to_numpy()[sku_of]
perish = np.array([categories[cat_names[c]][0] for c in cat_of])
sup_of = products_df["_sup_idx"].to_numpy()[sku_of]
contract_lt = suppliers_df["contract_lead_time_days"].to_numpy()[sup_of]
on_time = suppliers_df["on_time_rate_target"].to_numpy()[sup_of]
late_mean = suppliers_df["mean_delay_when_late_days"].to_numpy()[sup_of]
review = np.array([categories[cat_names[c]][4] for c in cat_of])
season_amp = np.array([categories[c][5] for c in cat_names])
season_peak = np.array([categories[c][6] for c in cat_names])
dow_profile = np.array([0.92, 0.88, 0.90, 0.97, 1.10, 1.28, 1.15])  # Mon..Sun
trend = np.linspace(0.97, 1.05, D_ALL)

# promo multiplier and price per (day, series) only where active -> store as sparse dict of day -> (idx array, mult, disc)
promo_active = {}
for (k, scope, s_i, e_i, disc, upl) in promo_days:
    if scope == "ALL":
        idx = np.arange(S) * K + k
    else:
        rgi = regions.index(scope)
        idx = np.where(store_region == rgi)[0] * K + k
    for d in range(s_i, e_i + 1):
        promo_active.setdefault(d, []).append((idx, upl, disc))

on_hand = np.ceil(base * (contract_lt + review) * 1.2).astype(np.int64)
on_order = np.zeros(N, dtype=np.int64)
arrivals = np.zeros((D_ALL + 60, N), dtype=np.int64)
hist_len = 28
ring = np.tile(base, (hist_len, 1))  # trailing sales used by the naive policy
z = 1.28

sales_units = np.zeros((HIST_DAYS, N), dtype=np.int32)
eod_on_hand = np.zeros((HIST_DAYS, N), dtype=np.int32)
promo_flag = np.zeros((HIST_DAYS, N), dtype=np.int8)
sell_price = np.zeros((HIST_DAYS, N), dtype=np.float32)
po_rows = []  # (series, order_day, expected_day, actual_day, qty)

for d in range(HIST_DAYS):
    ts = all_days[d]
    # receive
    on_hand += arrivals[d]
    on_order -= arrivals[d]
    # demand
    doy = ts.dayofyear
    seas = 1.0 + season_amp * np.cos(2 * np.pi * (doy - season_peak) / 365.25)
    lam = base * dow_profile[ts.dayofweek] * seas[cat_of] * hol_mult[d, cat_of] * trend[d]
    mult = np.ones(N)
    disc = np.zeros(N)
    pf = np.zeros(N, dtype=np.int8)
    for idx, upl, dsc in promo_active.get(d, []):
        mult[idx] = upl
        disc[idx] = dsc
        pf[idx] = 1
    lam = lam * mult * rng.gamma(6.0, 1 / 6.0, N)
    demand = rng.poisson(lam)
    sold = np.minimum(demand, on_hand)
    on_hand -= sold
    # perishable shrink
    shrink = np.where(perish, np.floor(on_hand * 0.03), 0).astype(np.int64)
    on_hand -= shrink
    sales_units[d] = sold
    eod_on_hand[d] = on_hand
    promo_flag[d] = pf
    sell_price[d] = price * (1 - disc)
    ring[d % hist_len] = sold
    # naive reorder policy: trailing average, contract lead time, no promo/holiday awareness
    avg = ring.mean(axis=0)
    sd = ring.std(axis=0)
    rop = avg * (contract_lt + 1) + z * sd * np.sqrt(contract_lt + 1)
    out = rop + avg * review
    ip = on_hand + on_order
    need = ip < rop
    if need.any():
        idx = np.where(need)[0]
        qty = (np.ceil((out[idx] - ip[idx]) / case_pack[idx]) * case_pack[idx]).astype(np.int64)
        qty = np.maximum(qty, case_pack[idx])
        late = rng.random(len(idx)) > on_time[idx]
        # disruption: affected suppliers' late rate jumps to 70% with longer delays in last 21 days
        if d >= HIST_DAYS - 21:
            dis = np.isin(sup_of[idx], disrupted)
            late = late | (dis & (rng.random(len(idx)) < 0.7))
            extra = np.where(dis, rng.integers(2, 6, len(idx)), 0)
        else:
            extra = 0
        delay = np.where(late, 1 + rng.poisson(late_mean[idx]), 0) + np.where(late, extra, 0)
        actual = d + contract_lt[idx] + delay
        arrivals[np.minimum(actual, D_ALL + 59), idx] += qty
        on_order[idx] += qty
        po_rows.append(np.stack([idx, np.full(len(idx), d), d + contract_lt[idx], actual, qty], axis=1))
    if d % 120 == 0:
        print(f"day {d} {ts.date()} oos_rate={np.mean(on_hand == 0):.3%} open_po_lines={int((on_order > 0).sum())}")

po = np.concatenate(po_rows)
print(f"Simulated {HIST_DAYS} days x {N} store-SKUs; PO lines: {len(po):,}")
print(f"End-of-day stockout rate (share of store-SKU-days at zero on hand): {np.mean(eod_on_hand == 0):.2%}")
```

**Output**

```text
day 0 2024-11-07 oos_rate=0.005% open_po_lines=380
day 120 2025-03-07 oos_rate=4.495% open_po_lines=12993
day 240 2025-07-05 oos_rate=5.140% open_po_lines=13461
day 360 2025-11-02 oos_rate=4.715% open_po_lines=13201
day 480 2026-03-02 oos_rate=4.250% open_po_lines=12835
day 600 2026-06-30 oos_rate=4.995% open_po_lines=13215
day 720 2026-10-28 oos_rate=4.585% open_po_lines=12343
Simulated 730 days x 20000 store-SKUs; PO lines: 2,119,953
End-of-day stockout rate (share of store-SKU-days at zero on hand): 4.13%
```

## Cell 10

```markdown
%md ## Write raw files to the UC Volume (with planted data-quality defects)
```

## Cell 11

```python
for sub in ["products", "stores", "suppliers", "sales", "inventory", "purchase_orders", "promotions", "calendar"]:
    p = f"{LANDING}/{sub}"
    if os.path.exists(p):
        shutil.rmtree(p)
    os.makedirs(p, exist_ok=True)
os.makedirs(EVIDENCE, exist_ok=True)

products_df.drop(columns=["_sup_idx", "_base"]).to_csv(f"{LANDING}/products/products.csv", index=False)
stores_df.drop(columns=["size_factor"]).assign(size_band=stores_df["format"]).to_csv(f"{LANDING}/stores/stores.csv", index=False)
suppliers_df.to_csv(f"{LANDING}/suppliers/suppliers.csv", index=False)
promos_df.to_csv(f"{LANDING}/promotions/promotions.csv", index=False)
holidays_df.to_csv(f"{LANDING}/calendar/holidays.csv", index=False)

store_ids = stores_df["store_id"].to_numpy()
sku_ids = products_df["sku_id"].to_numpy()
months = pd.Series(dates).dt.to_period("M").astype(str).to_numpy()
defects = {"sales_negative_units": 0, "sales_null_sku": 0, "sales_duplicates": 0, "inventory_negative_on_hand": 0, "po_missing_qty": 0}
sales_rows_total = 0
inv_rows_total = 0

for m in pd.unique(months):
    dsel = np.where(months == m)[0]
    # ---- POS daily sales (only non-zero rows, as POS systems emit) ----
    dd, nn = np.nonzero(sales_units[dsel])
    day_abs = dsel[dd]
    units = sales_units[day_abs, nn].astype(np.int64)
    sp = sell_price[day_abs, nn].round(2)
    sdf = pd.DataFrame({
        "sale_date": dates[day_abs].strftime("%Y-%m-%d"),
        "store_id": store_ids[store_of[nn]],
        "sku_id": sku_ids[sku_of[nn]].astype(object),
        "units_sold": units,
        "unit_price": sp,
        "net_sales": (units * sp).round(2),
        "on_promo": promo_flag[day_abs, nn],
        "pos_batch_ts": (dates[day_abs] + pd.Timedelta(hours=23, minutes=55)).strftime("%Y-%m-%dT%H:%M:%S"),
    })
    n = len(sdf)
    neg = rng.random(n) < 0.0005
    sdf.loc[neg, "units_sold"] = -sdf.loc[neg, "units_sold"]
    nul = rng.random(n) < 0.0002
    sdf.loc[nul, "sku_id"] = None
    dup = sdf.sample(frac=0.001, random_state=int(rng.integers(1e9)))
    sdf = pd.concat([sdf, dup], ignore_index=True)
    defects["sales_negative_units"] += int(neg.sum()); defects["sales_null_sku"] += int(nul.sum()); defects["sales_duplicates"] += len(dup)
    sdf.to_csv(f"{LANDING}/sales/pos_daily_sales_{m}.csv", index=False)
    sales_rows_total += len(sdf)
    # ---- end-of-day inventory snapshots (every store-SKU, every day) ----
    rep_d = np.repeat(dsel, N)
    rep_n = np.tile(np.arange(N), len(dsel))
    idf = pd.DataFrame({
        "snapshot_date": dates[rep_d].strftime("%Y-%m-%d"),
        "store_id": store_ids[store_of[rep_n]],
        "sku_id": sku_ids[sku_of[rep_n]],
        "on_hand_units": eod_on_hand[rep_d, rep_n].astype(np.int64),
        "source_system": "store_inventory_mgmt",
    })
    negi = rng.random(len(idf)) < 0.0002
    idf.loc[negi, "on_hand_units"] = -1
    defects["inventory_negative_on_hand"] += int(negi.sum())
    idf.to_json(f"{LANDING}/inventory/inventory_snapshot_{m}.json", orient="records", lines=True)
    inv_rows_total += len(idf)
    print(f"{m}: sales rows {len(sdf):,} | inventory rows {len(idf):,}")

# ---- purchase-order events (CREATED always, RECEIVED when actual arrival <= as_of) ----
po_df = pd.DataFrame(po, columns=["series", "order_day", "expected_day", "actual_day", "qty"])
po_df["po_line_id"] = [f"PO{i:08d}" for i in range(1, len(po_df) + 1)]
po_df["store_id"] = store_ids[store_of[po_df.series]]
po_df["sku_id"] = sku_ids[sku_of[po_df.series]]
po_df["supplier_id"] = suppliers_df["supplier_id"].to_numpy()[sup_of[po_df.series]]
day_ts = lambda col: pd.to_datetime(start) + pd.to_timedelta(po_df[col], unit="D")
created = pd.DataFrame({
    "event_id": "E" + po_df["po_line_id"].str[2:] + "C",
    "event_type": "PO_CREATED",
    "event_ts": (day_ts("order_day") + pd.Timedelta(hours=21)).dt.strftime("%Y-%m-%dT%H:%M:%S"),
    "po_line_id": po_df["po_line_id"], "store_id": po_df["store_id"], "sku_id": po_df["sku_id"], "supplier_id": po_df["supplier_id"],
    "order_qty": po_df["qty"].astype("Int64"), "expected_delivery_date": day_ts("expected_day").dt.strftime("%Y-%m-%d"),
    "received_qty": pd.Series([pd.NA] * len(po_df), dtype="Int64", index=po_df.index),
})
miss = rng.random(len(created)) < 0.0003
created.loc[miss, "order_qty"] = pd.NA
defects["po_missing_qty"] = int(miss.sum())
rec = po_df[po_df.actual_day <= HIST_DAYS - 1]
received = pd.DataFrame({
    "event_id": "E" + rec["po_line_id"].str[2:] + "R",
    "event_type": "PO_RECEIVED",
    "event_ts": (pd.to_datetime(start) + pd.to_timedelta(rec["actual_day"], unit="D") + pd.Timedelta(hours=6)).dt.strftime("%Y-%m-%dT%H:%M:%S"),
    "po_line_id": rec["po_line_id"], "store_id": rec["store_id"], "sku_id": rec["sku_id"], "supplier_id": rec["supplier_id"],
    "order_qty": pd.Series([pd.NA] * len(rec), dtype="Int64", index=rec.index),
    "expected_delivery_date": None,
    "received_qty": rec["qty"].astype("Int64"),
})
events = pd.concat([created, received], ignore_index=True)
assert events["event_ts"].notna().all() and len(events) == len(created) + len(received)
events["_m"] = events["event_ts"].str[:7]
for m, g in events.groupby("_m"):
    g.drop(columns="_m").to_json(f"{LANDING}/purchase_orders/po_events_{m}.json", orient="records", lines=True)
open_lines = int((po_df.actual_day > HIST_DAYS - 1).sum())
print(f"PO events: {len(events):,} (created {len(created):,}, received {len(received):,}); open PO lines at as-of: {open_lines:,}")
```

**Output**

```text
2024-11: sales rows 412,949 | inventory rows 480,000
2024-12: sales rows 534,817 | inventory rows 620,000
2025-01: sales rows 531,982 | inventory rows 620,000
2025-02: sales rows 481,500 | inventory rows 560,000
2025-03: sales rows 534,005 | inventory rows 620,000
2025-04: sales rows 517,468 | inventory rows 600,000
2025-05: sales rows 538,943 | inventory rows 620,000
2025-06: sales rows 522,747 | inventory rows 600,000
2025-07: sales rows 540,650 | inventory rows 620,000
2025-08: sales rows 543,167 | inventory rows 620,000
2025-09: sales rows 522,525 | inventory rows 600,000
2025-10: sales rows 541,683 | inventory rows 620,000
2025-11: sales rows 520,537 | inventory rows 600,000
2025-12: sales rows 539,199 | inventory rows 620,000
2026-01: sales rows 536,592 | inventory rows 620,000
2026-02: sales rows 484,449 | inventory rows 560,000
2026-03: sales rows 536,016 | inventory rows 620,000
2026-04: sales rows 521,521 | inventory rows 600,000
2026-05: sales rows 541,625 | inventory rows 620,000
2026-06: sales rows 524,902 | inventory rows 600,000
2026-07: sales rows 543,541 | inventory rows 620,000
2026-08: sales rows 545,748 | inventory rows 620,000
2026-09: sales rows 526,435 | inventory rows 600,000
2026-10: sales rows 543,204 | inventory rows 620,000
2026-11: sales rows 102,426 | inventory rows 120,000
PO events: 4,225,358 (created 2,119,953, received 2,105,405); open PO lines at as-of: 14,548
```

## Cell 12

```markdown
%md ## Run summary (execution evidence)
```

## Cell 13

```python
summary = {
    "as_of_date": AS_OF, "history_start": str(dates[0].date()), "stores": N_STORES, "skus": N_SKUS, "store_sku_series": N,
    "suppliers": len(suppliers_df), "promotions": len(promos_df),
    "upcoming_promotions": int((pd.to_datetime(promos_df.start_date) > as_of).sum()),
    "pos_sales_rows_written": sales_rows_total, "inventory_snapshot_rows_written": inv_rows_total,
    "po_events_written": len(events), "open_po_lines_at_as_of": open_lines,
    "simulated_eod_stockout_rate": round(float(np.mean(eod_on_hand == 0)), 4),
    "stockout_rate_last_28d": round(float(np.mean(eod_on_hand[-28:] == 0)), 4),
    "disrupted_suppliers": [suppliers[i]["supplier_id"] for i in disrupted],
    "planted_defects": defects,
    "files": {sub: sorted(os.listdir(f"{LANDING}/{sub}"))[:3] + (["..."] if len(os.listdir(f"{LANDING}/{sub}")) > 3 else []) for sub in os.listdir(LANDING)},
}
print(json.dumps(summary, indent=2))
with open(f"{EVIDENCE}/01_datagen_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
```

**Output**

```text
{
  "as_of_date": "2026-11-06",
  "history_start": "2024-11-07",
  "stores": 50,
  "skus": 400,
  "store_sku_series": 20000,
  "suppliers": 24,
  "promotions": 4433,
  "upcoming_promotions": 226,
  "pos_sales_rows_written": 12688631,
  "inventory_snapshot_rows_written": 14600000,
  "po_events_written": 4225358,
  "open_po_lines_at_as_of": 14548,
  "simulated_eod_stockout_rate": 0.0413,
  "stockout_rate_last_28d": 0.0454,
  "disrupted_suppliers": [
    "V004",
    "V016"
  ],
  "planted_defects": {
    "sales_negative_units": 6409,
    "sales_null_sku": 2557,
    "sales_duplicates": 12674,
    "inventory_negative_on_hand": 2916,
    "po_missing_qty": 646
  },
  "files": {
    "products": [
      "products.csv"
    ],
    "stores": [
      "stores.csv"
    ],
    "suppliers": [
      "suppliers.csv"
    ],
    "sales": [
      "pos_daily_sales_2024-11.csv",
      "pos_daily_sales_2024-12.csv",
      "pos_daily_sales_2025-01.csv",
      "..."
    ],
    "inventory": [
      "inventory_snapshot_2024-11.json",
      "inventory_snapshot_2024-12.json",
      "inventory_snapshot_2025-01.json",
      "..."
    ],
    "purchase_orders": [
      "po_events_2024-11.json",
      "po_events_2024-12.json",
      "po_events_2025-01.json",
      "..."
    ],
    "promotions": [
      "promotions.csv"
    ],
    "calendar": [
      "holidays.csv"
    ]
  }
}
```
