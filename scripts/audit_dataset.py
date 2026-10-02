import os
import duckdb
import polars as pl
from pathlib import Path

def main():
    csv_path = r"C:\Users\anany\Downloads\VoidHacks8_MuleAccount_2M_Transactions.csv"
    print("=== 1. DATASET CSV AUDIT ===")
    print(f"Dataset path: {csv_path}")
    print(f"Exists: {os.path.exists(csv_path)}")
    if os.path.exists(csv_path):
        size_bytes = os.path.getsize(csv_path)
        print(f"File size: {size_bytes} bytes ({size_bytes / (1024*1024):.2f} MB)")
        
        # Read header and basic info using DuckDB for speed
        con_mem = duckdb.connect()
        df_summary = con_mem.execute(f"""
            SELECT 
                count(*) as raw_row_count,
                count(DISTINCT Transaction_ID) as unique_txn_ids,
                min(Timestamp) as min_timestamp,
                max(Timestamp) as max_timestamp
            FROM read_csv_auto('{csv_path}', header=True)
        """).df()
        print(df_summary)
        
        cols = con_mem.execute(f"DESCRIBE SELECT * FROM read_csv_auto('{csv_path}', header=True) LIMIT 1").fetchall()
        print("Columns in CSV:")
        for c in cols:
            print(f"  - {c[0]} ({c[1]})")
            
        payment_modes = con_mem.execute(f"""
            SELECT Payment_Mode, count(*) as count 
            FROM read_csv_auto('{csv_path}', header=True) 
            GROUP BY Payment_Mode
        """).fetchall()
        print("Payment Types / Modes:")
        for pm in payment_modes:
            print(f"  - {pm[0]}: {pm[1]}")

        acc_summary = con_mem.execute(f"""
            SELECT 
                count(DISTINCT Sender_Account) as unique_senders,
                count(DISTINCT Receiver_Account) as unique_receivers,
                count(DISTINCT Sender_Account) + count(DISTINCT Receiver_Account) as approx_accounts
            FROM read_csv_auto('{csv_path}', header=True)
        """).fetchall()
        print("Account Counts:", acc_summary)

        # Exact unique accounts
        unique_accs = con_mem.execute(f"""
            SELECT count(DISTINCT acc) FROM (
                SELECT Sender_Account as acc FROM read_csv_auto('{csv_path}', header=True)
                UNION
                SELECT Receiver_Account as acc FROM read_csv_auto('{csv_path}', header=True)
            )
        """).fetchone()[0]
        print(f"Total Unique Accounts (Senders + Receivers): {unique_accs}")

    print("\n=== 2. PROCESSED PARQUET AUDIT ===")
    clean_pq = r"data\processed\transactions.parquet"
    flagged_pq = r"data\processed\transactions_flagged.parquet"
    print(f"Clean parquet exists: {os.path.exists(clean_pq)}")
    if os.path.exists(clean_pq):
        size_pq = os.path.getsize(clean_pq)
        print(f"Clean parquet size: {size_pq / (1024*1024):.2f} MB")
        con_mem = duckdb.connect()
        clean_count = con_mem.execute(f"SELECT count(*) FROM read_parquet('{clean_pq}')").fetchone()[0]
        print(f"Clean parquet row count: {clean_count}")
    
    print(f"Flagged parquet exists: {os.path.exists(flagged_pq)}")
    if os.path.exists(flagged_pq):
        size_fl = os.path.getsize(flagged_pq)
        print(f"Flagged parquet size: {size_fl / (1024*1024):.2f} MB")
        con_mem = duckdb.connect()
        flagged_count = con_mem.execute(f"SELECT count(*) FROM read_parquet('{flagged_pq}')").fetchone()[0]
        print(f"Flagged parquet row count: {flagged_count}")
        if os.path.exists(clean_pq):
            print(f"Total processed rows (clean + flagged) = {clean_count + flagged_count}")

    print("\n=== 3. DUCKDB AUDIT ===")
    duckdb_path = r"data\abhedya.duckdb"
    if os.path.exists(duckdb_path):
        size_db = os.path.getsize(duckdb_path)
        print(f"DuckDB path: {duckdb_path}")
        print(f"DuckDB size: {size_db / (1024*1024):.2f} MB")
        try:
            con = duckdb.connect(duckdb_path, read_only=True)
            tables = con.execute("SHOW TABLES").fetchall()
            print("Tables in DuckDB:", tables)
            for t in tables:
                tname = t[0]
                cnt = con.execute(f"SELECT count(*) FROM {tname}").fetchone()[0]
                print(f"Count in {tname}: {cnt}")
                
            # Check for synthetic data in transactions table
            synthetic_rows = con.execute("SELECT count(*) FROM transactions WHERE transaction_id LIKE 'TX0%'").fetchone()[0]
            print(f"Synthetic rows (TX0xxx) in DuckDB: {synthetic_rows}")
            con.close()
        except Exception as e:
            print(f"Error accessing DuckDB: {e}")

if __name__ == "__main__":
    main()
