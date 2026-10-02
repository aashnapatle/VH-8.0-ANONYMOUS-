import time
import duckdb

con = duckdb.connect("data/abhedya.duckdb", read_only=True)
account_ids = con.execute("SELECT sender_account FROM transactions LIMIT 500").df()["sender_account"].tolist()

placeholders = ",".join(["?" for _ in account_ids])

t0 = time.perf_counter()
cnt_or = con.execute(f"SELECT count(*) FROM transactions WHERE sender_account IN ({placeholders}) OR receiver_account IN ({placeholders})", account_ids + account_ids).fetchone()[0]
t1 = time.perf_counter()
print(f"OR condition count: {cnt_or}, time: {(t1-t0)*1000:.2f} ms")

t0 = time.perf_counter()
cnt_and = con.execute(f"SELECT count(*) FROM transactions WHERE sender_account IN ({placeholders}) AND receiver_account IN ({placeholders})", account_ids + account_ids).fetchone()[0]
t1 = time.perf_counter()
print(f"AND condition count: {cnt_and}, time: {(t1-t0)*1000:.2f} ms")

con.close()
