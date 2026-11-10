import copy
import unittest

from research_agent.ccfa_audit import (
    STUDY_DESIGN_SCHEMA,
    audit_study_design,
    study_design_template,
)

COMPLETE = {
    "schema_version": STUDY_DESIGN_SCHEMA,
    "question": "Does record completeness change the decidability of humidity-stability claims?",
    "hypothesis": "Only complete pre-registered records let the passivated/control difference be decided.",
    "claims": [
        {
            "claim": "Complete records make the stability difference decidable.",
            "type": "beats_prior",
            "evidence": "Paired comparison across complete and incomplete repeated runs.",
        },
        {
            "claim": "The gain is caused by interface hydrolysis suppression.",
            "type": "mechanism",
            "evidence": "Ablate the passivation layer while holding the ageing protocol fixed.",
        },
    ],
    "datasets": [
        {
            "name": "humid-ageing-v1",
            "role": "development",
            "splits": "device-level split; no device appears in both arms",
            "leakage_checks": "group split by device id; duplicate scans removed",
            "license": "internal lab data, no redistribution",
            "coverage": "two encapsulation types, one humidity regime",
            "data_status": "collected",
        }
    ],
    "baselines": [
        {
            "name": "unpassivated control",
            "implementation": "official protocol",
            "tuning": "no hyperparameters; fixed pre-registered protocol",
            "compute": "same chamber and wall-clock as treatment",
            "compute_matched": True,
        }
    ],
    "ablations": [
        {
            "name": "passivation removed",
            "mechanism": "interface layer only; ageing protocol unchanged",
            "single_change": True,
        }
    ],
    "robustness": [
        {"axis": "seeds", "plan": "three independent device batches"},
        {"axis": "shift", "plan": "one higher-humidity chamber"},
    ],
    "compute": {
        "hardware": "two environmental chambers",
        "training_time": "not applicable; 1000 h ageing per batch",
        "inference_cost": "not applicable",
        "fairness": "all arms share chamber time and measurement schedule",
    },
    "statistics": {
        "seeds": 3,
        "effect_size": "minimum meaningful lifetime ratio 1.2",
        "confidence_interval": "bootstrap 95% CI over batches",
        "multiplicity": "Holm correction across the two comparisons",
        "missing_data": "drop batches with missing records; report the count",
        "power_analysis": {
            "effect_size": "lifetime ratio 1.2",
            "sd": "batch-level log-lifetime SD 0.25",
            "alpha": 0.05,
            "power": 0.8,
            "n_per_arm": 6,
        },
    },
    "prior_work": [
        {"title": "Passivation study A", "venue": "Fixture Venue", "year": 2025,
         "relation": "same protocol, no record-completeness contrast"},
        {"title": "Reproducibility study B", "venue": "Fixture Workshop", "year": 2024,
         "relation": "reports incomplete records but no paired test"},
    ],
    "negative_results": "Report runs where the difference stays undecidable and why.",
    "limitations": "Two encapsulation types and one lab; not a field deployment.",
}


class CCFAuditTest(unittest.TestCase):
    def test_a_complete_design_is_ready(self):
        result = audit_study_design(copy.deepcopy(COMPLETE))
        self.assertEqual(result["status"], "ready_for_g2", result["blockers"])
        self.assertEqual(result["score"], 1.0)
        self.assertFalse(result["blockers"])
        self.assertEqual(result["ccfa"]["level"], "venue_ready")

    def test_a_one_dataset_replication_is_not_venue_ready(self):
        design = copy.deepcopy(COMPLETE)
        design["replication"] = {
            "status": "one_dataset_decided",
            "datasets": 4,
            "decided_in": ["breast_cancer"],
        }
        result = audit_study_design(design)
        self.assertEqual(result["ccfa"]["level"], "evidence_ready")
        self.assertTrue(any("replication.scope" in item for item in result["warnings"]))

    def test_undecided_metric_validity_caps_a_venue_claim(self):
        design = copy.deepcopy(COMPLETE)
        design["metric_validity"] = {
            "metric": "improvement_per_evaluation",
            "sensitivity": "headroom-normalized anytime AUC (post-hoc)",
            "decided_in": ["digits"],
            "undecided_in": ["iris", "wine"],
        }
        result = audit_study_design(design)
        self.assertEqual(result["ccfa"]["level"], "evidence_ready")
        self.assertEqual(result["status"], "attention", "a metric caveat is disclosure, not a blocker")
        self.assertTrue(any("metric.validity" in item for item in result["warnings"]))
        self.assertIn("metric validity", " ".join(result["ccfa"]["reasons"]))

    def test_a_partial_claim_replication_caps_the_design_at_evidence_ready(self):
        design = copy.deepcopy(COMPLETE)
        design["replication"] = {
            "status": "consistent",
            "datasets": 4,
            "decided_in": ["a", "b", "c", "d"],
            "interaction_decided_in": ["a", "b", "c"],
        }
        result = audit_study_design(design)
        self.assertEqual(result["ccfa"]["level"], "evidence_ready")
        self.assertTrue(
            any("replication.partial_claim" in item for item in result["warnings"])
        )

    def test_an_unestimated_sd_is_not_a_power_analysis(self):
        design = copy.deepcopy(COMPLETE)
        design["statistics"]["power_analysis"]["sd"] = "not estimated"
        result = audit_study_design(design)
        self.assertEqual(result["ccfa"]["level"], "disclosure_incomplete")
        self.assertTrue(any("statistics.power_analysis" in item for item in result["blockers"]))

    def test_fixture_or_planned_data_is_not_venue_ready(self):
        design = copy.deepcopy(COMPLETE)
        design["datasets"][0]["data_status"] = "planned"
        result = audit_study_design(design)
        self.assertEqual(result["status"], "ready_for_g2")
        self.assertEqual(result["ccfa"]["level"], "disclosure_complete")

    def test_a_run_design_is_refused(self):
        run_design = {
            "design_id": "DESIGN-1",
            "question": "iris",
            "hypothesis": "logreg beats majority",
            "baseline": "majority class",
            "primary_metric": "accuracy",
            "controls": ["majority baseline"],
            "seeds": 3,
            "budget": "3 seeds",
            "stopping_rule": "freeze",
        }
        result = audit_study_design(run_design)
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(any("not a study design" in item for item in result["blockers"]))

    def test_a_tuned_baseline_is_required_for_a_beats_prior_claim(self):
        design = copy.deepcopy(COMPLETE)
        design["baselines"][0]["tuning"] = ""
        result = audit_study_design(design)
        self.assertEqual(result["status"], "incomplete")
        joined = " | ".join(result["blockers"])
        self.assertIn("baselines.1", joined)
        self.assertIn("ladder.beats_prior", joined)

    def test_a_mechanism_claim_needs_an_ablation(self):
        design = copy.deepcopy(COMPLETE)
        design["ablations"] = []
        result = audit_study_design(design)
        self.assertTrue(any("ladder.mechanism" in item for item in result["blockers"]))

    def test_claim_evidence_mapping_is_required(self):
        design = copy.deepcopy(COMPLETE)
        design["claims"][0]["evidence"] = "TODO"
        result = audit_study_design(design)
        self.assertTrue(any("claims.1.evidence" in item for item in result["blockers"]))

    def test_template_is_incomplete_until_filled(self):
        result = audit_study_design(study_design_template())
        self.assertEqual(result["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
