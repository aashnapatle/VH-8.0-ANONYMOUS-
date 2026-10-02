import json
import time
from src.graph.detector import FraudGraphDetector

detector = FraudGraphDetector()

# Test victim account
test_account = 'KKBK10000000'
print(f'Tracing 4-hop money trail for: {test_account}...')

start = time.time()
result = detector.trace_victim_flow(test_account, max_hops=4)
latency = time.time() - start

print('=' * 60)
print(f'Execution Time: {latency:.4f} seconds')
print(f'Total Discovered Accounts (Nodes): {result["total_nodes"]}')
print(f'Total Money Transfers (Edges): {result["total_edges"]}')
print('=' * 60)

# Display sample flagged nodes
print('\nSAMPLE FLAGGED MULES IDENTIFIED:')
print(f'{"Account":<16} | {"Hop":<4} | {"Risk Score":<10} | {"Layer":<16} | {"Freeze Rec"}')
print('-' * 65)

for node in result['nodes'][:15]:  # print first 15 nodes
    print(f'{node["account"]:<16} | {node["hop"]:<4} | {node["mule_risk_score"]:<10} | {node["layer"]:<16} | {str(node["recommended_freeze"]):<10}')

# Display sample edges/transactions
print('\nSAMPLE TRANSACTION FLOW (EDGES):')
print(f'{"From":<16} -> {"To":<16} | {"Amount (INR)":<12} | {"Timestamp"}')
print('-' * 65)

for edge in result['edges'][:10]:  # print first 10 edges
    print(f'{edge["source"]:<16} -> {edge["target"]:<16} | {edge["amount"]:<12.2f} | {edge["timestamp"]}')

# Dump complete output to JSON so you can inspect it visually
with open('debug_graph_output.json', 'w') as f:
    json.dump(result, f, indent=2)

print('\nFull output saved to: debug_graph_output.json')
