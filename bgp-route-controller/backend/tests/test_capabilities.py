import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as main_module
from app.main import action_history, execute_capability, seed_data


class CapabilityExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        seed_data()

    def test_execute_capability_logs_timestamped_entry(self) -> None:
        payload = execute_capability(
            {
                "capability": "divert",
                "router_id": "router-002",
                "prefix": "10.10.10.0/24",
            },
            x_user_role="Operator",
        )

        self.assertEqual(payload["status"], "executed")
        self.assertEqual(payload["capability"], "divert")
        self.assertEqual(main_module.capability_state.mode, "diverted")
        self.assertTrue(action_history)
        last_entry = action_history[-1]
        self.assertIn("prefix", last_entry.details)
        self.assertTrue(last_entry.created_at)
        self.assertIn("duration_ms", payload)
        self.assertIn("route-map", payload["config"])

    def test_acl_execution_includes_circuit_config(self) -> None:
        payload = execute_capability(
            {
                "capability": "acl-filters",
                "router_id": "router-002",
                "prefix": "10.10.10.0/24",
                "circuit": "GigabitEthernet0/0",
            },
            x_user_role="Operator",
        )

        self.assertEqual(payload["status"], "executed")
        self.assertIn("GigabitEthernet0/0", payload["config"])
        self.assertIn("access-list", payload["config"])


if __name__ == "__main__":
    unittest.main()
