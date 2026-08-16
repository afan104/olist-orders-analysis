# E-Commerce Supply Chain Analysis

**Stack:** AWS Redshift · Python · scipy · AWS QuickSight
**Dataset:** [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — ~100k real orders, 2016–2018

---

## What This Project Does

This project analyzes a real-world retail order dataset to surface three operational questions:

1. Are we fulfilling orders on time, and is that rate improving?
2. Which product categories take the longest to deliver, and by how much?
3. Does delivery performance differ significantly by seller region, or is it random noise?

The analysis runs entirely in SQL on Redshift, gets visualized in a QuickSight dashboard, and uses Python/scipy to validate that the regional patterns we see are statistically meaningful rather than coincidence.

---

## Part 1 — Getting the Data

Download the dataset from Kaggle (free account required). You need five files:

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `olist_product_category_name_translation.csv`

The dataset has 96,461 orders across 73 product categories, spread across five Brazilian states that map cleanly to regions.

---

## Part 2 — Redshift Setup

This project uses Redshift Serverless, which skips cluster sizing decisions and bills per query second. Provisioned clusters work identically for all the SQL here.

**Create the workgroup:**

In the AWS Console, go to **Redshift → Serverless → Get started**. Name the workgroup `ecommerce` and the namespace `ecommerce-ns`. Attach an IAM role that has `AmazonS3ReadOnlyAccess` — you need this for the COPY step.

**Create the schema:**

Open the Redshift Query Editor v2 and create four tables: `orders`, `order_items`, `products`, and `sellers`. The `orders` table needs columns for order ID, customer ID, status, purchase timestamp, approved timestamp, delivered timestamp, and estimated delivery timestamp. The `order_items` table links order IDs to product IDs and seller IDs with price and freight columns. The `products` table maps product IDs to category names (keep both the Portuguese original and the English translation). The `sellers` table maps seller IDs to their state.

**Upload to S3 and load:**

Create an S3 bucket and upload the five CSVs into a `raw/` prefix. Then use Redshift's COPY command to load each table directly from S3, pointing at your IAM role for auth. After loading, run a COUNT on each table to verify — you should see ~96k orders and ~113k order items.

---

## Part 3 — SQL Analysis

### Fulfillment Rate by Month

Fulfillment rate here means: of all orders that were delivered, what fraction arrived on or before the estimated delivery date? This is the primary SLA metric for the operations team.

Write a query that truncates `purchase_ts` to month, counts total delivered orders, counts how many had `delivered_ts <= estimated_ts`, and divides to get a percentage. Filter to `order_status = 'delivered'` and exclude rows where `delivered_ts` is null.

**Result:** fulfillment rate trends upward as the platform matures, with a sharp dip to 78.6% in March 2018. That timing does not line up with Brazil's nationwide truckers' strike (May 2018), so the strike is not the cause. A stronger candidate is the order volume surge starting November 2017: if delivery capacity did not scale with demand, a backlog could show up as a delayed drop in on-time fulfillment months later. This is not confirmed, average lead time and order status by month would need to trend the same way to support it, but the dip itself is real and shows the metric is detecting actual operational events, not noise.

### Average Lead Time by Product Category

Lead time is the number of days between purchase and delivery. Breaking it down by category reveals which product types are operationally expensive to fulfill — usually large or heavy items like furniture and appliances.

Write a query that joins `orders → order_items → products`, uses `DATEDIFF('day', purchase_ts, delivered_ts)` for lead time, and groups by category. Add a `HAVING COUNT(...) > 100` clause to filter out low-volume categories — without it, a category with three slow deliveries would dominate the top of the list and mislead the analysis.

### Order Volume Trends

Truncate `purchase_ts` to month, join through to `products` for the category name, and count distinct orders per month per category. This feeds the time-series visual in QuickSight and shows demand seasonality.

### Order Status by Region

Join `orders → order_items → sellers` and group by `seller_state` and `order_status`. This cross-tab is the raw input for the Chi-squared test in Part 5 — keep it, you will need it.

---

## Part 4 — QuickSight Dashboard

### Connect to Redshift

In the QuickSight console, go to **Datasets → New dataset → Redshift (Manual connection)**. Enter your Serverless endpoint, database name, and credentials. QuickSight will ask you to update the Redshift security group to allow its IP range — the console walks you through this.

Create four datasets using **Custom SQL**, one per query from Part 3.

### The Four Visuals

**Visual 1 — Fulfillment Rate Over Time**
Line chart. X axis: month. Y axis: fulfillment rate %. Add a reference line at 90% to make the SLA target visible. The 2018 dip appears clearly and invites conversation.

**Visual 2 — Lead Time by Category (Top 10)**
Horizontal bar chart sorted descending by average lead days. Filter to the top 10 categories. Color bars that exceed 20 days using a conditional formatting rule — this immediately shows stakeholders which categories are bottlenecks.

**Visual 3 — Order Volume Over Time**
Area chart. X axis: month. Y axis: order volume. Use category as the color series, but filter to the top 5 categories by total volume — otherwise the chart becomes unreadable. This shows overall platform growth and which categories drive it.

**Visual 4 — Order Status by Region**
Stacked bar chart. X axis: region. Y axis: order count. Stacked by order status. Filter to `delivered`, `canceled`, and `unavailable` only. This sets up the statistical question answered in Part 5: does the status mix actually differ by region, or does it just look that way?

Publish the analysis as a dashboard: **Supply Chain Operations Overview**.

---

## Part 5 — Statistical Validation

The dashboard in Part 4 shows patterns. This section proves they are real.

Install dependencies:

```bash
pip install psycopg2-binary pandas scipy
```

Connect to Redshift using `psycopg2` with your cluster endpoint on port 5439.

### Test 1: Is the regional lead time difference real?

**Hypothesis:** Orders fulfilled by SP-state sellers arrive faster than orders from other states.

SP (São Paulo) is Brazil's logistics hub. Pull lead days per order joined to seller state, then split into two groups: SP and everything else. Run `scipy.stats.ttest_ind` with `equal_var=False` (Welch's t-test, since the group sizes and variances will differ).

**Result:** SP averages 12.21 days, other states average 12.90 days, t = -10.98, p = 5.2e-28. The difference is not random, but it is small: 0.68 days, not the 5+ day gap a "logistics hub" story might suggest. With tens of thousands of orders in each group, even a minor, practically small gap produces a vanishingly small p-value. Statistical significance here means the gap is real, not that it is large.

### Test 2: Does order status distribution differ by region?

**Hypothesis:** The mix of delivered vs. canceled vs. unavailable orders is not uniform across regions.

Pull region and order status for all orders, then build a contingency table with `pd.crosstab(df['region'], df['order_status'])`. Pass that table to `scipy.stats.chi2_contingency`.

**Result:** chi2 = 228.78, dof = 42, p = 1.5e-27, confirming that where a seller is located predicts what happens to the order, not just how fast it arrives, but whether it arrives at all. One caveat: several state/status combinations have very low order counts, producing expected cell frequencies well under the standard rule-of-thumb minimum of 5. The chi-squared approximation is less reliable in those sparse cells, so treat the low-volume states in this result with caution rather than as settled fact. Grouping low-volume states into an "other" bucket before re-running the test would tighten this up.

---

## Next Steps

- **Add a dbt layer** to model the raw tables into clean `dim_` and `fct_` tables. This demonstrates data modeling and is a common interview expectation for data engineer roles.
- **Schedule the Python analysis** with AWS Lambda + EventBridge to run weekly, turning this into a live monitoring pipeline.
- **Write a Redshift stored procedure** that recalculates fulfillment rate on a schedule. Redshift stored procedures are a frequent interview topic because of how they interact with sort keys and distribution styles.
- **Add EXPLAIN output** for the lead time query and document the sort/distribution key choices that would make it faster at scale.
