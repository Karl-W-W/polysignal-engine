import os
import json
import unittest
import sys
from pathlib import Path

# Fix module discovery
sys.path.append(os.getcwd())

from lab.sentinel import analyze_market
from lab.negotiator import check_candidates

class TestHierarchy(unittest.TestCase):
    def setUp(self):
        self.candidates_path = Path("lab/candidates.json")
        self.deploy_trigger = Path("lab/.deploy-trigger")
        if self.candidates_path.exists():
            self.candidates_path.unlink()
        if self.deploy_trigger.exists():
            self.deploy_trigger.unlink()

    def test_sentinel_analysis(self):
        market = {"id": "test_m1", "title": "Test Market"}
        analysis = analyze_market(market)
        self.assertEqual(analysis["market_id"], "test_m1")
        self.assertIn("confidence", analysis)

    def test_negotiator_escalation(self):
        # Create a high-confidence candidate
        candidates = [{
            "market_id": "test_high",
            "title": "High Confidence Market",
            "confidence": 0.95
        }]
        with open(self.candidates_path, "w") as f:
            json.dump(candidates, f)
            
        check_candidates()
        
        self.assertTrue(self.deploy_trigger.exists())
        with open(self.deploy_trigger, "r") as f:
            content = f.read()
            self.assertIn("escalate test_high", content)

if __name__ == "__main__":
    unittest.main()
