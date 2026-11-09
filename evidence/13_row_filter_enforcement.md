# Unity Catalog row filter and column mask: enforcement test

_Captured 2026-11-09 13:30 UTC from workspace `https://fevm-serverless-stable-3vku19.cloud.databricks.com`._

Test identity: `adarsh.nandan@databricks.com` (the job's run-as user). The job maps it to **Valley only, without financials**, queries `planner_risk_queue`, then removes the mapping. Assertions in the job: row filter enforced = **True**, mask enforced = **True**.

### Before mapping (admin, unmapped)

| region | rows visible | revenue values visible |
|---|---|---|
| Coastal | 3998 | 3998 |
| Lakeshore | 3999 | 3999 |
| Metro North | 3999 | 3999 |
| Metro South | 4000 | 4000 |
| Valley | 4000 | 4000 |

### Mapped to Valley, no financials

| region | rows visible | revenue values visible |
|---|---|---|
| Valley | 4000 | 0 |

### After mapping removed

| region | rows visible | revenue values visible |
|---|---|---|
| Coastal | 3998 | 3998 |
| Lakeshore | 3999 | 3999 |
| Metro North | 3999 | 3999 |
| Metro South | 4000 | 4000 |
| Valley | 4000 | 4000 |

### Policies attached to the table (`DESCRIBE TABLE EXTENDED`)

| item | value |
|---|---|
| revenue_at_risk | double |
| Row Filter | `serverless_stable_3vku19_catalog`.`inventory_risk`.`region_row_filter` ON (region) |
| revenue_at_risk | `serverless_stable_3vku19_catalog`.`inventory_risk`.`mask_revenue` |

### Row filter and mask functions

```sql
SELECT routine_name, routine_definition FROM serverless_stable_3vku19_catalog.information_schema.routines
WHERE routine_schema = 'inventory_risk' AND routine_name IN ('region_row_filter', 'mask_revenue') ORDER BY 1
```

| routine_name | routine_definition |
|---|---|
| mask_revenue | CASE  -- parameter names must not collide with mapping-table columns (they would shadow the argument)   WHEN EXISTS (SELECT 1 FROM serverless_stable_3vku19_catalog.inventory_risk.planner_region_access a WHERE a.principal = current_user())     THEN CASE WHEN EXISTS (SELECT 1 FROM serverless_stable_3vku19_catalog.inventory_risk.planner_region_access a WHERE a.principal = current_user() AND a.can_see_financials)               THEN revenue_at_risk END   WHEN is_member('admins') OR is_account_group_member('supply_chain_finance') THEN revenue_at_risk END |
| region_row_filter | CASE   WHEN EXISTS (SELECT 1 FROM serverless_stable_3vku19_catalog.inventory_risk.planner_region_access a WHERE a.principal = current_user())     THEN EXISTS (SELECT 1 FROM serverless_stable_3vku19_catalog.inventory_risk.planner_region_access a WHERE a.principal = current_user() AND a.region = row_region)   ELSE is_member('admins') OR is_account_group_member('inventory_planners_all')        OR is_account_group_member(concat('planners_', lower(replace(row_region, ' ', '_')))) END |
