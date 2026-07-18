import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
from app.main import app, seed_data, action_history
from fastapi.testclient import TestClient

seed_data()
client = TestClient(app)
response = client.post('/capabilities/execute', json={'capability':'divert','router_id':'router-001','prefix':'10.10.10.0/24'})
print(response.status_code)
print(response.json())
print('history_len', len(action_history))
print('last_action', action_history[-1].details)
