import time
from src.graph.detector import FraudGraphDetector

detector = FraudGraphDetector()
print("Graph Engine Test Shuru...")

start = time.time()
# Ek sample account test karo
res = detector.trace_victim_flow("KKBK10000000", max_hops=4)
print(f"Time Taken: {time.time() - start:.4f} seconds")
print(f"Nodes mile: {res['total_nodes']}, Edges mile: {res['total_edges']}")
print("Test Complete!")
