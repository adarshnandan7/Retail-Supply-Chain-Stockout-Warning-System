# Business baseline (last 365 days, synthetic data)

The deck and readout value model use these numbers. Lost sales are estimated as stockout days x the store/SKU average daily units on in-stock days x price. That is before substitution, so a real retailer would calibrate it with substitution and basket-abandonment rates.

### Annual sales, stockout rate, estimated lost sales

```sql
WITH d AS (SELECT * FROM serverless_stable_3vku19_catalog.inventory_risk.gold_daily_store_sku_sales WHERE sale_date > date_sub('2026-11-06', 365)),
s AS (SELECT store_id, sku_id, avg(CASE WHEN NOT is_stockout THEN units_sold END) AS avg_units, avg(CASE WHEN NOT is_stockout THEN unit_price END) AS price FROM d GROUP BY ALL)
SELECT round(sum(d.net_sales)/1e6, 2) AS annual_net_sales_musd, count_if(d.is_stockout) AS stockout_store_sku_days, round(avg(d.is_stockout::int), 4) AS stockout_rate,
 round(sum(CASE WHEN d.is_stockout THEN s.avg_units * s.price END)/1e6, 2) AS est_lost_sales_musd_before_substitution,
 round(sum(CASE WHEN d.is_stockout THEN s.avg_units * s.price END) / sum(d.net_sales), 4) AS lost_sales_share_of_sales
FROM d JOIN s USING (store_id, sku_id)
```

| annual_net_sales_musd | stockout_store_sku_days | stockout_rate | est_lost_sales_musd_before_substitution | lost_sales_share_of_sales |
|---|---|---|---|---|
| 226.12 | 304342 | 0.0417 | 10.83 | 0.0479 |

### Stockout rate on promotion vs regular days

```sql
SELECT CASE WHEN on_promo THEN 'Promotion day' ELSE 'Regular day' END AS day_type, round(avg(is_stockout::int), 4) AS stockout_rate, count(*) AS store_sku_days FROM serverless_stable_3vku19_catalog.inventory_risk.gold_daily_store_sku_sales WHERE sale_date > date_sub('2026-11-06', 365) GROUP BY 1
```

| day_type | stockout_rate | store_sku_days |
|---|---|---|
| Regular day | 0.034 | 6942692 |
| Promotion day | 0.1923 | 355894 |

### Stockout rate by category

```sql
SELECT category, round(avg(is_stockout::int), 4) AS stockout_rate FROM serverless_stable_3vku19_catalog.inventory_risk.gold_daily_store_sku_sales WHERE sale_date > date_sub('2026-11-06', 365) GROUP BY 1 ORDER BY 2 DESC
```

| category | stockout_rate |
|---|---|
| Fresh Produce | 0.0672 |
| Dairy & Eggs | 0.066 |
| Bakery | 0.0462 |
| Beverages | 0.042 |
| Pantry & Baking | 0.0363 |
| Snacks | 0.0298 |
| Meat & Seafood | 0.0294 |
| Household | 0.0286 |
| Personal Care | 0.0248 |
| Frozen | 0.0222 |
