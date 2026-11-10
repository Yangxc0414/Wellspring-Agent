import json
import tempfile
import unittest
from pathlib import Path

from research_agent.design_draft import DesignDraftError, request_study_design
from research_agent.host_model import ModelTurnLedger
from research_agent.project import init_project
from research_agent.storage import write_json_atomic

DESIGN = {
    "schema_version": "study-design-0.1",
    "question": "Does record completeness change the decidability of stability claims?",
    "hypothesis": "Only complete records let the passive/control difference be decided.",
    "claims": [
        {"claim": "Complete records make the difference decidable.", "type": "beats_prior",
         "evidence": "Paired comparison across complete and incomplete records."},
        {"claim": "Passivation suppresses interface hydrolysis.", "type": "mechanism",
         "evidence": "Remove only the passivation layer at a fixed ageing protocol."},
    ],
    "datasets": [
        {"name": "lab", "role": "test", "data_status": "collected",
         "splits": "batch split", "leakage_checks": "device id grouping",
         "license": "internal", "coverage": "two encapsulation types"}
    ],
    "baselines": [
        {"name": "control", "implementation": "official protocol", "tuning": "none",
         "compute": "same chamber", "compute_matched": True}
    ],
    "ablations": [
        {"name": "remove passivation", "mechanism": "interface layer only", "single_change": True}
    ],
    "robustness": [{"axis": "shift", "plan": "two humidity levels"}],
    "compute": {"hardware": "two chambers", "training_time": "1000 h per batch",
                "inference_cost": "offline scans", "fairness": "shared schedule"},
    "statistics": {
        "seeds": 3,
        "effect_size": "lifetime ratio 1.2",
        "confidence_interval": "batch bootstrap",
        "multiplicity": "Holm",
        "missing_data": "no imputation",
        "power_analysis": {"effect_size": "1.2", "sd": "0.25", "alpha": 0.05,
                           "power": 0.8, "n_per_arm": 6},
    },
    "prior_work": [
        {"title": "A", "venue": "V", "year": 2025, "relation": "same protocol"},
        {"title": "B", "venue": "W", "year": 2024, "relation": "reports missing records"},
    ],
    "negative_results": "Report undecidable runs rather than claiming failure.",
    "limitations": "Two encapsulation types and one lab.",
}


class DesignDraftTest(unittest.TestCase):
    def test_a_pending_turn_is_answered_then_replayed_into_a_study_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            init_project(project, "design draft")
            run = project / "runs" / "RUN-D"
            run.mkdir()
            write_json_atomic(run / "demo.json", {
                "topic": "perovskite humidity stability",
                "fixture_mode": True,
                "modules": {
                    "literature": {"spans": [
                        {"span_id": "S-1", "source_id": "FX-1", "section": "Results",
                         "text": "fixture evidence"}
                    ]}
                },
            })
            write_json_atomic(run / "idea.json", {"candidates": [
                {"idea_id": "IDEA-01", "title": "t", "hypothesis": "h",
                 "falsification": "f", "lens": "measurement", "evidence_refs": ["S-1"]}
            ]})
            write_json_atomic(run / "experiment.json", {"question": "q", "hypothesis": "h"})
            ledger_path = root / "turns.json"

            pending = request_study_design(project, "RUN-D", ledger_path=ledger_path)
            self.assertEqual(pending["status"], "pending")
            turn_id = pending["turn_id"]

            ledger = ModelTurnLedger(ledger_path)
            ledger.respond(turn_id, json.dumps(DESIGN, ensure_ascii=False), host_label="Qoder")

            done = request_study_design(project, "RUN-D", ledger_path=ledger_path)
            self.assertEqual(done["status"], "ready_for_g2", done.get("blockers"))
            self.assertEqual(done["ccfa"]["level"], "venue_ready")
            self.assertTrue((run / "study-design.json").is_file())
            self.assertTrue((run / "study-design-audit.json").is_file())

            with self.assertRaises(DesignDraftError):
                request_study_design(project, "RUN-D", ledger_path=ledger_path)


if __name__ == "__main__":
    unittest.main()
