import time
import duckdb
import networkx as nx

def main():
    con = duckdb.connect("data/abhedya.duckdb", read_only=True)
    print("=== TOP SENDERS IN REAL DATASET ===")
    top_senders = con.execute("""
        SELECT sender_account, count(*) as tx_count, sum(amount) as total_sent, count(DISTINCT receiver_account) as distinct_receivers
        FROM transactions
        GROUP BY sender_account
        ORDER BY tx_count DESC
        LIMIT 10
    """).df()
    print(top_senders)

    print("\n=== TOP RECEIVERS IN REAL DATASET ===")
    top_receivers = con.execute("""
        SELECT receiver_account, count(*) as tx_count, sum(amount) as total_received, count(DISTINCT sender_account) as distinct_senders
        FROM transactions
        GROUP BY receiver_account
        ORDER BY tx_count DESC
        LIMIT 10
    """).df()
    print(top_receivers)

    # Let's find an account that has both incoming and outgoing transactions (e.g. intermediate mule)
    print("\n=== ACCOUNTS WITH BOTH INCOMING AND OUTGOING ===")
    mule_candidates = con.execute("""
        WITH in_tx AS (
            SELECT receiver_account as acc, count(*) as in_count, sum(amount) as in_amt
            FROM transactions GROUP BY receiver_account
        ),
        out_tx AS (
            SELECT sender_account as acc, count(*) as out_count, sum(amount) as out_amt
            FROM transactions GROUP BY sender_account
        )
        SELECT in_tx.acc, in_count, out_count, in_amt, out_amt
        FROM in_tx JOIN out_tx ON in_tx.acc = out_tx.acc
        WHERE in_count >= 5 AND out_count >= 5
        ORDER BY in_count + out_count DESC
        LIMIT 10
    """).df()
    print(mule_candidates)

    con.close()

if __name__ == "__main__":
    main()
