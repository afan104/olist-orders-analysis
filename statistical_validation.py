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
WHERE orders.order_status IN ('delivered','canceled', 'unavailable')
ORDER BY seller_state ASC, order_status DESC"""

df = pd.read_sql(query, conn)
crosstab = pd.crosstab(df["seller_state"], df["order_status"])
res = scipy.stats.chi2_contingency(crosstab)
expected_df = pd.DataFrame(
    res.expected_freq, index=crosstab.index, columns=crosstab.columns
)
print("Observed:")
print(crosstab)
print("\nExpected:")
print(expected_df.round(2))
print(f"\nchi2 = {res.statistic:.2f}, dof = {res.dof}, p = {res.pvalue:.4g}")

conn.close()
