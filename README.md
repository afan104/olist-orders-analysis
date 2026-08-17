# E-Commerce Supply Chain Analysis

**Stack:** AWS Redshift · Python · scipy · AWS QuickSight
**Dataset:** [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) — ~100k orders, 2016–2018

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

In the AWS Console, go to **Redshift → Serverless → Get started**. Name the workgroup `ecommerce` and the namespace `ecommerce-ns`. Attach an IAM role that has `AmazonS3ReadOnlyAccess` for the COPY step.

**Create the schema:**

Open the Redshift Query Editor v2 and create four tables: `orders`, `order_items`, `products`, and `sellers`. The `orders` table needs columns for order ID, customer ID, status, purchase timestamp, approved timestamp, delivered timestamp, and estimated delivery timestamp. The `order_items` table links order IDs to product IDs and seller IDs with price and freight columns. The `products` table maps product IDs to category names (keep both the Portuguese original and the English translation). The `sellers` table maps seller IDs to their state.

**Upload to S3 and load:**

Create an S3 bucket and upload the five CSVs into a `raw/` prefix. Then use Redshift's COPY command to load each table directly from S3, pointing at your IAM role for auth. After loading, run a COUNT on each table to verify that you see ~96k orders and ~113k order items.

---

## Part 3 — SQL Analysis

### Fulfillment Rate by Month

Fulfillment rate here means: of all orders that were delivered, what fraction arrived on or before the estimated delivery date? This is the primary SLA metric for the operations team.

Write a query that truncates `purchase_ts` to month, counts total delivered orders, counts how many had `delivered_ts <= estimated_ts`, and divides to get a percentage. Filter to `order_status = 'delivered'` and exclude rows where `delivered_ts` is null.

**Result:** fulfillment rate trends upward as the platform matures, with a sharp dip to 78.6% in March 2018. The timing rules out Brazil's nationwide truckers' strike (May 2018) as the cause, that happened two months later.

Two follow-up checks rule out a platform-wide explanation. The average estimated delivery window (22 days in March) is in line with every surrounding month, so it wasn't caused by newly tightened delivery dates, since promised delivery windows remained the same. Average lead time (16 days in March) barely moved from January or February either, so orders weren't actually taking longer to arrive. If this were a capacity backlog, lead time should have spiked but didn't.

Breaking fulfillment rate down by month and seller state surfaces an interesting pattern: the dip is driven by 2 specific states. RJ falls from a normal low-90s range to 65.4% in March, then fully recovers to 96.0% in April. SP, which dominates order volume, also dips (77.0%) and drags the platform-wide average down with it. MG, PR, SC, and RS barely move over the same period. This points to a short, regionally-concentrated disruption centered on RJ and SP that cleared up within a month, not a nationwide demand or capacity problem.

| Month   | RJ    | SP    | MG    | PR    | SC    | RS    |
| ------- | ----- | ----- | ----- | ----- | ----- | ----- |
| 2018-01 | 92.1% | 93.7% | 95.9% | 93.5% | —    | —    |
| 2018-02 | 87.2% | 82.2% | 89.8% | 87.1% | 89.2% | —    |
| 2018-03 | 65.4% | 77.0% | 85.7% | 87.4% | 89.4% | 91.7% |
| 2018-04 | 96.0% | 94.5% | 94.5% | 96.2% | 94.8% | 95.5% |

(States with fewer than 100 delivered orders that month are omitted, shown as `—`.)

RJ has a documented cause. On February 16, 2018, President Michel Temer signed a decree placing Rio de Janeiro's public security, police, and prison system under federal military control, triggered by a wave of Carnival-period violence. The intervention took effect February 21 and ran through the rest of 2018. Military oversight of a state's security apparatus starting right before the dip is a plausible source of delivery disruption, and the timing matches both the crash and the April recovery ([2018 federal intervention in Rio de Janeiro](https://en.wikipedia.org/wiki/2018_federal_intervention_in_Rio_de_Janeiro)).

SP doesn't have an equally clear cause. A search for SP-specific disruptions in that window (postal strikes, transit strikes) turned up nothing from March 2018 specifically. It may be a secondary effect of the same national Carnival-period disruption, or something deeper than a superficial issue since online searches don't show anything directly causing it.

### Average Lead Time by Product Category

Lead time is the number of days between purchase and delivery. Breaking it down by category reveals which product types are operationally expensive to fulfill, usually large or heavy items like furniture and appliances.

Write a query that joins `orders → order_items → products`, uses `DATEDIFF('day', purchase_ts, delivered_ts)` for lead time, and groups by category. Add a `HAVING COUNT(...) > 100` clause to filter out low-volume categories to prevent scenarios like a category with three slow deliveries that dominate the top of the list and mislead the analysis.

### Order Volume Trends

Truncate `purchase_ts` to month, join through to `products` for the category name, and count distinct orders per month per category. This feeds the time-series visual in QuickSight and shows demand seasonality.

### Order Status by Region

Join `orders → order_items → sellers` and group by `seller_state` and `order_status`. This cross-tab is the raw input for the Chi-squared test in Part 5.

---

## Part 4 — QuickSight Dashboard

### Connect to Redshift

In the QuickSight console, go to **Datasets → New dataset → Redshift (Manual connection)**. Enter your Serverless endpoint, database name, and credentials. QuickSight will ask you to update the Redshift security group to allow its IP range, or you can do this manually.

Create four datasets using **Custom SQL**, one per query from Part 3.

### The Four Visuals

**Visual 1 — Fulfillment Rate Over Time**
Line chart. X axis: month. Y axis: fulfillment rate %. Add a reference line at 90% to make the SLA target visible.

**Visual 2 — Lead Time by Category (Top 10)**
Horizontal bar chart sorted descending by average lead days. Filter to the top 10 categories. Color bars that exceed 20 days using a conditional formatting rule to show which categories are bottlenecks.

**Visual 3 — Order Volume Over Time**
Area chart. X axis: month. Y axis: order volume. Use category as the color series, but filter to the top 5 categories by total volume. This shows overall platform growth and which categories drive it.

**Visual 4 — Order Status by Region**
Stacked bar chart. X axis: region. Y axis: order count. Stacked by order status. Filter to `delivered` and `canceled` only (`unavailable` is too rare, 7 orders total, to break down by region meaningfully). This sets up the statistical question answered in Part 5: does the status mix actually differ by region, or does it just look that way?

Publish the analysis as a dashboard: **Supply Chain Operations Overview**.

---

## Part 5 — Statistical Validation

The dashboard in Part 4 shows patterns. This section tests whether they hold up statistically or could be explained by chance.

Install dependencies:

```bash
pip install psycopg2-binary pandas scipy
```

Connect to Redshift using `psycopg2` with your cluster endpoint on port 5439.

### Test 1: Is the regional lead time difference real?

**Hypothesis:** Orders fulfilled by SP-state sellers arrive faster than orders from other states.

SP (São Paulo) is Brazil's logistics hub. Pull lead days per order joined to seller state, then split into two groups: SP and everything else. Run `scipy.stats.ttest_ind` with `equal_var=False` (Welch's t-test, since the group sizes and variances will differ).

**Result:** SP averages 12.29 days, other states average 12.93 days, t = -9.63, p = 6.2e-22. The gap is statistically significant but small, 0.64 days. With tens of thousands of orders in each group, even a minor difference produces a vanishingly small p-value, so the low p-value reflects sample size as much as effect size. SP sellers deliver marginally faster than the rest of the country combined, not dramatically faster.

### Test 2: Does order status distribution differ by region?

**Hypothesis:** The mix of delivered vs. canceled orders is not uniform across regions.

Pull region and order status for all orders, then build a contingency table with `pd.crosstab(df['region'], df['order_status'])`. Pass that table to `scipy.stats.chi2_contingency`.

`unavailable` was dropped from this test: it only accounts for 7 orders total across the whole dataset, too few to say anything meaningful about by region regardless of how the states are grouped. Low-volume states (fewer than 1,000 total orders) are grouped into an `OTHER` bucket so expected cell frequencies stay above the standard reliability threshold of 5.

**Result:** chi2 = 11.57, dof = 6, p = 0.072, once `unavailable` is dropped and low-volume states are grouped into `OTHER` so every expected cell clears 5. That does not reach the conventional 0.05 threshold, so this test does not confirm that the delivered/canceled mix differs by region.

This is the more important finding than the number itself. Two earlier, invalid versions of this test looked dramatically significant, and the p-value collapsed as each problem got fixed:

| Version   | `unavailable` included? | State grouping            | chi2   | dof | p-value | Smallest expected cell |
| --------- | ------------------------- | ------------------------- | ------ | --- | ------- | ---------------------- |
| 1st run   | Yes                       | None                      | 228.78 | 42  | 1.5e-27 | ~0.0002                |
| 2nd run   | Yes                       | <100 orders →`OTHER`   | 122.51 | 26  | 1.8e-14 | ~0.01                  |
| Final run | No                        | <1,000 orders →`OTHER` | 11.57  | 6   | 0.072   | 9.31                   |

Both invalid runs had expected cell counts far below the standard reliability threshold of 5 (some under 1), driven by rare states and the near-nonexistent `unavailable` category. As those sparse cells got fixed, first by grouping small states, then by dropping the 7-order `unavailable` category, the chi2 statistic dropped along with it, and the result went from "overwhelming" to "not significant." A chi-squared test run on cells that violate its own assumptions can produce an extremely small p-value that disappears once those assumptions are actually satisfied.
