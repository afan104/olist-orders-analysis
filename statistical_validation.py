import psycopg2, scipy.stats
import pandas as pd
import getpass
from statistics import mean

# connect to database
HOST = "ecommerce.381492252693.us-east-2.redshift-serverless.amazonaws.com"
PORT = 5439
DBNAME = "dev"
USER = "quicksight_reader"
PWD = getpass.getpass("enter password for redshift connection: ")

conn = psycopg2.connect(host=HOST, port=PORT, dbname=DBNAME, user=USER, password=PWD)


## T test (Welch's due to unequal variance and group size)
## regional lead time differences (SP v all other locations)
query = """SELECT
    DISTINCT orders.order_id,
    seller_state,
    DATEDIFF('day', orders.order_purchase_timestamp, orders.order_delivered_customer_date) as lead_time
FROM orders
INNER JOIN order_items
ON orders.order_id = order_items.order_id
INNER JOIN sellers
ON order_items.seller_id=sellers.seller_id
WHERE orders.order_status = 'delivered'
AND orders.order_delivered_customer_date IS NOT NULL"""

lead_time_df = pd.read_sql(query, conn)

ttest_res = scipy.stats.ttest_ind(
    (lead_time_df[lead_time_df["seller_state"] == "SP"])["lead_time"],
    (lead_time_df[lead_time_df["seller_state"] != "SP"])["lead_time"],
    equal_var=False,
)
print(
    f"SP mean: {mean((lead_time_df[lead_time_df["seller_state"] == "SP"])["lead_time"])}, Other mean: {mean((lead_time_df[lead_time_df["seller_state"] != "SP"])["lead_time"])}"
)
print(ttest_res)


## Chi squared
## Do different regions have different order status breakdowns?
query = """SELECT 
    DISTINCT orders.order_id,
    sellers.seller_state as seller_state,
    orders.order_status as order_status
FROM orders
INNER JOIN order_items
ON orders.order_id=order_items.order_id
INNER JOIN sellers
ON order_items.seller_id=sellers.seller_id
WHERE orders.order_status IN ('delivered','canceled')
ORDER BY seller_state ASC, order_status DESC"""

df = pd.read_sql(query, conn)

state_counts = df["seller_state"].value_counts()
low_volume_states = state_counts[state_counts < 1000].index
df["seller_state"] = df["seller_state"].where(
    ~df["seller_state"].isin(low_volume_states), "OTHER"
)

crosstab = pd.crosstab(df["seller_state"], df["order_status"])
res = scipy.stats.chi2_contingency(crosstab)
expected_df = pd.DataFrame(
    res.expected_freq, index=crosstab.index, columns=crosstab.columns # type: ignore
)
print("Observed:")
print(crosstab)
print("\nExpected:")
print(expected_df.round(2))
print(f"\nchi2 = {res.statistic:.2f}, dof = {res.dof}, p = {res.pvalue:.4g}") # type: ignore

## Follow-up: did the estimated delivery window itself get tighter over time,
## separate from actual delivery speed changing?
query = """SELECT
    DATE_TRUNC('month', order_purchase_timestamp) as month,
    AVG(DATEDIFF('day', order_purchase_timestamp, order_estimated_delivery_date)) as avg_estimated_window
FROM orders
WHERE order_status = 'delivered'
AND order_delivered_customer_date IS NOT NULL
GROUP BY month
ORDER BY month"""

estimated_window_df = pd.read_sql(query, conn)
print("\nAverage estimated delivery window by month:")
print(estimated_window_df.to_string(index=False))

## Follow-up: overall average lead time by month, not broken out by category,
## to see if delivery actually slowed down heading into March 2018
query = """SELECT
    DATE_TRUNC('month', order_purchase_timestamp) as month,
    AVG(DATEDIFF('day', order_purchase_timestamp, order_delivered_customer_date)) as avg_lead_time
FROM orders
WHERE order_status = 'delivered'
AND order_delivered_customer_date IS NOT NULL
GROUP BY month
ORDER BY month"""

lead_time_by_month_df = pd.read_sql(query, conn)
print("\nAverage lead time by month:")
print(lead_time_by_month_df.to_string(index=False))

## Follow-up: is the fulfillment rate dip uniform across states, or concentrated in a few?
query = """SELECT
    DATE_TRUNC('month', orders.order_purchase_timestamp) as month,
    sellers.seller_state as seller_state,
    COUNT(DISTINCT orders.order_id) as total_delivered,
    COUNT(DISTINCT CASE WHEN orders.order_delivered_customer_date <= orders.order_estimated_delivery_date THEN orders.order_id END)::FLOAT
        / COUNT(DISTINCT orders.order_id) * 100 as fulfillment_rate
FROM orders
INNER JOIN order_items
ON orders.order_id = order_items.order_id
INNER JOIN sellers
ON order_items.seller_id = sellers.seller_id
WHERE orders.order_status = 'delivered'
AND orders.order_delivered_customer_date IS NOT NULL
GROUP BY month, seller_state
HAVING COUNT(DISTINCT orders.order_id) > 100
ORDER BY month, seller_state"""

fulfillment_by_state_df = pd.read_sql(query, conn)
print(
    "\nFulfillment rate by month and state (states with >100 delivered orders that month):"
)
print(fulfillment_by_state_df.to_string(index=False))

conn.close()
