"""Skill packs become auditable rubric data, never executed instructions."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.cli import main
from research_agent.skill_packs import (
    STAGE_PROFILES,
    _actionable,
    _stage_for,
    coverage_report,
    find_venue,
    scan_pack,
)


def _make_pack(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "LICENSE").write_text("MIT License\n\nPermission is hereby granted.\n", encoding="utf-8")
    skill = root / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: demo-journal\n"
        "description: A demo journal skill for testing.\n"
        "---\n\n"
        "# Demo journal\n\n"
        "## Submission checklist\n\n"
        "- [ ] remove author identity and affiliation\n"
        "- references use GB/T 7714\n\n"
        "## Writing checklist\n\n"
        "- abstract must have purpose method result and conclusion\n\n"
        "## Background\n\n"
        "- this journal is known for selective review\n\n"
        "## Experiment requirements\n\n"
        "| check | requirement |\n"
        "| --- | --- |\n"
        "| baseline | same compute and split |\n",
        encoding="utf-8",
    )
    resources = root / "resources"
    resources.mkdir()
    (resources / "checklist.md").write_text(
        "## Reproducibility\n\n"
        "- fix random seeds and environment\n"
        "- workflow pointer: use `demo-journal`\n"
        "- keep artifacts anonymous: README, repo names and paths must not leak identity "
        "(see `demo-journal`)\n",
        encoding="utf-8",
    )
    scripts = skill / "scripts"
    scripts.mkdir()
    marker = root / "executed.txt"
    (scripts / "run.py").write_text(
        "open(%r, 'w').write('executed')\n" % str(marker), encoding="utf-8"
    )
    return marker


class SkillPackTest(unittest.TestCase):
    def test_pack_is_scanned_with_provenance_and_checklists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            marker = _make_pack(root)
            result = scan_pack(root, max_items=20)
            self.assertEqual(result["schema_version"], "skill-pack-0.1")
            self.assertEqual(result["license"]["id"], "MIT")
            self.assertTrue(result["license"]["verified_file"])
            self.assertEqual(len(result["skills"]), 1)
            self.assertTrue(result["skills"][0]["has_scripts"])
            self.assertEqual(len(result["resources"]), 1)
            self.assertEqual(result["resources"][0]["kind"], "checklist")
            for stage in ("submission", "writing", "design", "reproducibility"):
                self.assertIn(stage, result["stage_counts"])
            self.assertIn("actionable_counts", result)
            background = [item for item in result["checklist"] if item["heading"] == "Background"]
            self.assertTrue(background)
            self.assertFalse(background[0]["actionable"])
            table = [item for item in result["checklist"] if item["heading"] == "Experiment requirements"]
            self.assertTrue(table)
            self.assertTrue(all(item["actionable"] for item in table))
            navigation = [item for item in result["checklist"] if item.get("navigation")]
            self.assertEqual(len(navigation), 1)
            self.assertIn("workflow pointer", navigation[0]["text"])
            self.assertFalse(navigation[0]["actionable"])
            cited = [
                item for item in result["checklist"] if "must not leak identity" in item["text"]
            ]
            self.assertTrue(cited)
            self.assertTrue(cited[0]["actionable"], "a real requirement that cites a sibling skill")
            self.assertFalse(marker.exists(), "the scanner must never execute scripts")

    def test_near_miss_separates_partial_disclosure_from_absence(self):
        items = [
            {"text": "report variance significance and ablations across seeds", "stage": "design"},
            {"text": "report variance", "stage": "design"},
        ]
        result = coverage_report(items[:1], "we report variance only, no other detail")
        row = result["rows"][0]
        self.assertEqual(row["status"], "missing")
        self.assertTrue(row["near_miss"])
        self.assertEqual(result["near_miss"], 1)
        self.assertLess(row["overlap"], result["threshold"])
        self.assertGreaterEqual(row["overlap"], 0.25)

    def test_zero_coverage_across_languages_is_flagged_not_reported_as_quality(self):
        items = [
            {"text": "include tuned baselines and explain any missing comparison", "stage": "design"},
            {"text": "isolate the mechanism in ablations rather than removing components", "stage": "design"},
        ]
        zh = coverage_report(items, "本文提出一种方法并在公开数据集上验证其有效性。")
        self.assertEqual(zh["covered"], 0)
        self.assertTrue(zh["language_mismatch"], "English rubric against a Chinese draft")
        self.assertTrue(zh["warnings"])
        en = coverage_report(items, "we propose a method and evaluate it publicly")
        self.assertFalse(en["language_mismatch"], "same-script zero coverage is a real gap")
        # the point of this case is that no script warning may mask a same-script gap; the pack
        # fixture is deliberately tiny, so its thin-denominator note is expected and unrelated
        self.assertEqual([w for w in en["warnings"] if "script" in w or "language" in w], [])

    def test_partial_cross_language_coverage_is_still_not_a_score(self):
        # a Chinese bullet can match an English draft through one Latin token; that is not coverage
        items = [
            {"text": "报告 mAP", "stage": "design"},
            {"text": "对每个模块做去除对照", "stage": "design"},
        ]
        result = coverage_report(items, "we report mAP on the benchmark without uncertainty")
        self.assertTrue(result["language_mismatch"])
        self.assertGreaterEqual(result["covered"], 1)
        self.assertTrue(
            any("rough punch list" in w for w in result["warnings"]),
            "cross-language counts must say they are not a score",
        )

    def test_skill_coverage_accepts_venue_routing_like_the_mcp_face(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "design.json"
            artifact.write_text(json.dumps({"plan": "report variance"}), encoding="utf-8")
            # --pack alone still works
            pack = Path(tmp) / "packs" / "Demo-Skills"
            _make_pack(pack)
            target = Path(tmp) / "coverage.json"
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                code = main(
                    ["skill", "coverage", "--pack", str(pack), "--file", str(artifact),
                     "--output", str(target)]
                )
            self.assertEqual(code, 0, captured.getvalue())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["pack"], "Demo-Skills")
            # neither --pack nor a routable root must stop: never a silent 0-of-0 card
            missing = Path(tmp) / "missing.json"
            for argv in (
                ["skill", "coverage", "--file", str(artifact), "--output", str(missing)],
                [
                    "skill", "coverage",
                    "--pack-root", str(Path(tmp) / "nowhere"),
                    "--venue", "Demo",
                    "--file", str(artifact),
                    "--output", str(missing),
                ],
            ):
                stopped = False
                try:
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        stopped = main(argv) != 0 or "pass --pack" in out.getvalue()
                except SystemExit as exc:
                    stopped = bool(str(exc))
                self.assertTrue(stopped, "an unroutable pack request must stop: %s" % argv)
                self.assertFalse(missing.exists(), "no card may be written without a rubric")

    def test_by_stage_shows_where_the_gap_actually_is(self):
        items = [
            {"text": "report variance significance", "stage": "design"},
            {"text": "address each reviewer comment separately", "stage": "review"},
        ]
        result = coverage_report(items, "we report variance and significance for every arm")
        self.assertEqual(result["by_stage"]["design"]["covered"], 1)
        self.assertEqual(result["by_stage"]["review"]["missing"], 1)
        self.assertEqual(
            sum(bucket["items"] for bucket in result["by_stage"].values()),
            result["items"],
            "the per-stage buckets must account for the whole scored window",
        )

    def test_empty_score_is_never_a_clean_bill_of_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = scan_pack(Path(tmp))
            self.assertEqual(bare["checklist_total"], 0)
            self.assertTrue(
                any("nothing was checked" in w for w in bare["warnings"]),
                "a pack with no rubric must warn instead of returning a clean empty list",
            )
            # --pack "" resolves to a directory with no rubric: it must surface as nothing-checked
            self.assertTrue(any("nothing was checked" in w for w in bare["warnings"]))
        empty = coverage_report([], "any artifact text")
        self.assertEqual(empty["items"], 0)
        self.assertTrue(empty["warnings"], "a 0-of-0 report must say it checked nothing")

    def test_skill_coverage_scores_a_markdown_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            _make_pack(pack)
            rubric = scan_pack(pack)["checklist"]
            self.assertTrue(rubric)
            draft = Path(tmp) / "paper.md"
            # the draft body quotes one real rubric line: a scored markdown must register as covered
            draft.write_text(
                "# Headline\n\n%s\n" % rubric[0]["text"], encoding="utf-8"
            )
            target = Path(tmp) / "coverage.json"
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                code = main(
                    [
                        "skill", "coverage",
                        "--pack", str(pack),
                        "--file", str(draft),
                        "--output", str(target),
                    ]
                )
            self.assertEqual(code, 0, captured.getvalue())
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertGreater(saved["items"], 0, "the markdown body must be scored, not rejected")
            self.assertTrue(saved["input"].endswith("paper.md"))
            self.assertGreaterEqual(saved["covered"], 1, "quoting a rubric line is coverage")

    def test_skill_coverage_cli_scores_any_json_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            _make_pack(pack)
            design = Path(tmp) / "design.json"
            design.write_text(
                json.dumps(
                    {"question": "does memory help", "statistics": {"seeds": 32},
                     "ablations": ["remove the archive"]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([
                    "skill", "coverage", "--pack", str(pack), "--file", str(design),
                    "--max-items", "3",
                ])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["pack"], "pack")
            self.assertEqual(result["license"]["id"], "MIT")
            self.assertGreaterEqual(result["items"], 1)
            self.assertIn("near_miss", result)
            self.assertIn("lexical coverage only", result["boundary"])
            scope = result["pack_scope"]
            self.assertTrue(scope["truncated"], "a 3-item window must say the pack is bigger")
            self.assertEqual(scope["checklist_items"], 3)
            self.assertGreater(scope["checklist_total"], 3)
            self.assertEqual(scope["max_items"], 3)
            self.assertTrue(any("truncated" in w for w in scope["warnings"]), scope["warnings"])
            self.assertIn("of %d" % scope["checklist_total"], " ".join(scope["warnings"]))
            self.assertIn("partial rubric", result["boundary"])
            # a request above the hard cap must not look like it was honoured
            out2 = io.StringIO()
            with contextlib.redirect_stdout(out2):
                main([
                    "skill", "coverage", "--pack", str(pack), "--file", str(design),
                    "--max-items", "100000",
                ])
            wide = json.loads(out2.getvalue())
            self.assertEqual(wide["pack_scope"]["max_items"], 100000)
            self.assertEqual(wide["pack_scope"]["limit_applied"], 300)
            self.assertIn("capped at 300", " ".join(wide["pack_scope"]["warnings"]))

    def test_window_never_changes_the_rubric_being_scored(self):
        # regression for the defect class behind #28: truncation used to run before the
        # stage/profile filter, so a small --max-items silently changed which items the
        # pack was judged on instead of just how many of them were displayed
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            _make_pack(root)
            for narrowing in (
                {"stage": "reproducibility"},
                {"stages": list(STAGE_PROFILES["design"])},
                {"stages": list(STAGE_PROFILES["submission"])},
                {},
            ):
                wide = scan_pack(root, max_items=300, **narrowing)
                narrow = scan_pack(root, max_items=1, **narrowing)
                self.assertEqual(
                    wide["checklist_total"],
                    narrow["checklist_total"],
                    "the filtered rubric size must not depend on the display window: %s" % narrowing,
                )
                self.assertLessEqual(len(narrow["checklist"]), 1, narrowing)
                self.assertEqual(narrow["limit_applied"], 1)
                self.assertEqual(
                    narrow["truncated"],
                    wide["checklist_total"] > 1,
                    "a one-item window must report truncation exactly when the filtered "
                    "rubric was bigger: %s" % narrowing,
                )

    def test_review_headings_route_to_review_not_writing(self):
        self.assertEqual(_stage_for("指明修改稿中的具体位置", "九、常见答复失误"), "review")
        self.assertEqual(_stage_for("answer each comment separately", "Author Response"), "review")
        self.assertEqual(_stage_for("state the gap in one sentence", "Writing checklist"), "writing")
        self.assertEqual(_stage_for("记录语言与关键库版本", "复现包要求"), "reproducibility")

    def test_actionability_separates_context_from_requirements(self):
        self.assertFalse(
            _actionable("AAS 实行双盲三审制，以稿件本身质量为主要评判依据", "一、现状说明")
        )
        self.assertFalse(_actionable("便于见刊后同行复现，提升影响力", "九、制品与稿件"))
        self.assertTrue(_actionable("制品须匿名：README 不得泄露作者身份", "三、制品组织"))
        self.assertTrue(_actionable("fix random seeds and environment", "Reproducibility"))

    def test_stage_filter_and_unknown_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            _make_pack(root)
            result = scan_pack(root, stage="reproducibility")
            self.assertTrue(result["checklist"])
            self.assertTrue(all(item["stage"] == "reproducibility" for item in result["checklist"]))
            with self.assertRaises(ValueError):
                scan_pack(root, stage="unknown")

    def test_venue_audit_can_attach_a_pack_rubric(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            _make_pack(pack)
            manuscript = Path(tmp) / "manuscript.json"
            manuscript.write_text(
                json.dumps(
                    {
                        "abstract": "Purpose: test. Method: test. Result: test. Conclusion: test.",
                        "keywords": ["a", "b", "c"],
                        "sections": [{"label": "Introduction", "text": "remove author identity and affiliation; references use GB/T 7714; abstract purpose method result conclusion"}],
                        "references": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([
                    "venue", "audit", "--kind", "zh_journal", "--file", str(manuscript),
                    "--skill-pack", str(pack), "--skill-max-items", "5",
                ])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertIn("skill_pack", result)
            self.assertIn("submission", result["skill_pack"]["stage_counts"])
            coverage = result["skill_pack"]["coverage"]
            self.assertGreaterEqual(coverage["covered"], 1)
            self.assertGreaterEqual(coverage["missing"], 1)
            self.assertFalse((pack / "executed.txt").exists())

    def test_stage_profile_filters_the_rubric_and_rejects_double_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack"
            _make_pack(pack)
            manuscript = Path(tmp) / "manuscript.json"
            manuscript.write_text(
                json.dumps(
                    {
                        "abstract": "Purpose: test. Method: test. Result: test. Conclusion: test.",
                        "keywords": ["a", "b", "c"],
                        "sections": [
                            {
                                "label": "Introduction",
                                "text": "remove author identity and affiliation; abstract purpose method result conclusion",
                            }
                        ],
                        "references": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def audit(extra):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = main(
                        ["venue", "audit", "--kind", "zh_journal", "--file", str(manuscript),
                         "--skill-pack", str(pack), "--skill-max-items", "20"] + extra
                    )
                return code, json.loads(out.getvalue())

            code, draft = audit(["--skill-profile", "draft"])
            self.assertEqual(code, 0)
            coverage = draft["skill_pack"]["coverage"]
            self.assertEqual(coverage["profile"], "draft")
            self.assertEqual(
                set(coverage["stages"]), {"idea", "design", "writing", "reproducibility"}
            )
            texts = [row["text"] for row in coverage["rows"]]
            self.assertFalse(any("remove author identity" in text for text in texts))

            code, submission = audit(["--skill-profile", "submission"])
            self.assertEqual(code, 0)
            texts = [row["text"] for row in submission["skill_pack"]["coverage"]["rows"]]
            self.assertTrue(any("remove author identity" in text for text in texts))

            with self.assertRaises(SystemExit):
                audit(["--skill-profile", "draft", "--skill-stage", "writing"])

    def test_cli_outputs_json_and_can_write_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            _make_pack(root)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["skill", "pack", "--path", str(root), "--max-items", "5"])
            self.assertEqual(code, 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["pack"], "pack")
            self.assertLessEqual(len(data["checklist"]), 5)
            target = Path(tmp) / "pack.json"
            with contextlib.redirect_stdout(io.StringIO()):
                code = main([
                    "skill", "pack", "--path", str(root), "--stage", "writing",
                    "--max-items", "3", "--output", str(target),
                ])
            self.assertEqual(code, 0)
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertTrue(all(item["stage"] == "writing" for item in saved["checklist"]))

    def test_coverage_matches_chinese_phrases_and_keeps_unrelated_items_missing(self):
        items = [
            {"text": "删除作者信息与单位", "stage": "submission", "actionable": True},
            {"text": "固定随机种子", "stage": "reproducibility", "actionable": True},
            {"text": "AAS 实行双盲三审制", "stage": "general", "actionable": False},
        ]
        text = "本文不包含作者信息，已匿名处理"
        result = coverage_report(items, text)
        self.assertEqual(result["items"], 2)
        self.assertEqual(result["context_skipped"], 1)
        self.assertEqual(result["covered"], 1)
        self.assertEqual(result["missing"], 1)
        covered = result["rows"][0]
        self.assertEqual(covered["status"], "covered")
        self.assertEqual(covered["matched_phrase"], "作者信")
        self.assertEqual(result["rows"][1]["status"], "missing")
        staged = coverage_report(items, text, stage="submission")
        self.assertEqual(staged["items"], 1)
        self.assertEqual(staged["covered"], 1)





def _make_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    _make_pack(repo / "Demo-Skills")
    index_dir = repo / "shared-resources" / "journal-selection"
    index_dir.mkdir(parents=True)
    with (index_dir / "venue-index.tsv").open("w", encoding="utf-8", newline="") as handle:
        import csv

        writer = csv.writer(handle, delimiter="	")
        writer.writerow(["venue_id", "display_name", "pack_dir", "profile_path", "source_map", "scope_keywords"])
        writer.writerow(["demo-journal", "Demo Journal", "Demo-Skills", "", "", "demo;演示期刊;信息科学;测试"])
    return repo


class SkillVenueRouteTest(unittest.TestCase):
    def test_exact_venue_routes_to_its_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            result = find_venue(repo, "Demo Journal")
            self.assertEqual(result["best"]["venue_id"], "demo-journal")
            self.assertEqual(result["best"]["pack_dir"], "Demo-Skills")
            self.assertTrue(result["best"]["pack_exists"])

    def test_chinese_keyword_and_unknown_venue(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            self.assertEqual(find_venue(repo, "演示期刊")["best"]["venue_id"], "demo-journal")
            self.assertIsNone(find_venue(repo, "nonsense venue")["best"])

    def test_longer_chinese_keyword_beats_generic_competitors(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            index = repo / "shared-resources" / "journal-selection" / "venue-index.tsv"
            import csv

            with index.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="	")
                writer.writerow(["generic-social", "Generic Social", "Demo-Skills", "", "", "科学;信息"])
            result = find_venue(repo, "中国科学:信息科学")
            self.assertEqual(result["best"]["venue_id"], "demo-journal")
            self.assertIn(result["confidence"], ("medium", "high"))
            self.assertGreater(result["best"]["score"], result["matches"][1]["score"])

    def test_route_cli_and_venue_audit_auto_attach(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(Path(tmp))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([
                    "skill", "route", "--root", str(repo), "--venue", "Demo Journal",
                    "--with-checklist", "--max-items", "3",
                ])
            self.assertEqual(code, 0)
            route = json.loads(out.getvalue())
            self.assertEqual(route["best"]["venue_id"], "demo-journal")
            self.assertIn("scan", route)

            manuscript = Path(tmp) / "manuscript.json"
            manuscript.write_text(
                json.dumps(
                    {
                        "abstract": "Purpose: test. Method: test. Result: test. Conclusion: test.",
                        "keywords": ["a", "b", "c"],
                        "sections": [{"label": "Introduction", "text": "text"}],
                        "references": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([
                    "venue", "audit", "--kind", "zh_journal", "--file", str(manuscript),
                    "--skill-pack-root", str(repo), "--venue", "Demo Journal",
                    "--skill-max-items", "3",
                ])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["skill_pack"]["route"]["venue_id"], "demo-journal")


class ScriptShareTest(unittest.TestCase):
    """The mismatch guard must be computed over the same token set the score uses."""

    EN_ITEMS = [
        {
            "text": "keep a mapping from paper claims to commands so users can reproduce results",
            "source": "skills/x/SKILL.md",
            "heading": "Reproducibility",
            "stage": "reproducibility",
            "actionable": True,
            "navigation": False,
        }
    ]
    ZH_ITEMS = [
        {
            "text": "记录语言与关键库版本，并给出可执行的复现命令",
            "source": "skills/x/SKILL.md",
            "heading": "复现包要求",
            "stage": "reproducibility",
            "actionable": True,
            "navigation": False,
        }
    ]
    # a signing brief: Chinese headings, ASCII commands and long numeric tables underneath
    MIXED_DOC = (
        "## 可签署比较\n\n| comparison | mean_diff | 95% CI |\n| --- | --- | --- |\n"
        "| memory_on_gate_on | 0.129167 | [0.016687, 0.241646] |\n"
        "| memory_off_gate_on | 0.260417 | [0.173892, 0.346941] |\n"
        "复现路径：主张 → 命令 → 产物，重建命令由记录参数拼装，包内不存原始调用。\n"
    )
    EN_DOC = (
        "The draft keeps a mapping from paper claims to commands so a reviewer can reproduce "
        "the headline results with the recorded seeds and the same split function.\n"
    )

    def test_mixed_script_artifact_against_english_rubric_is_flagged(self):
        report = coverage_report(self.EN_ITEMS, self.MIXED_DOC)
        self.assertTrue(report["language_mismatch"])
        self.assertEqual(report["coverage_confidence"], "degraded")
        self.assertGreater(report["script_share"]["artifact_cjk_token_share"], 0.5)
        self.assertEqual(report["dominant_scripts"]["artifact"], "zh")
        self.assertEqual(report["dominant_scripts"]["rubric"], "latin")
        self.assertTrue(any("different scripts" in item for item in report["warnings"]))

    def test_chinese_artifact_against_chinese_rubric_still_scores(self):
        report = coverage_report(self.ZH_ITEMS, self.MIXED_DOC + "记录语言与关键库版本并给出可执行的复现命令\n")
        self.assertFalse(report["language_mismatch"])
        self.assertEqual(report["coverage_confidence"], "ok")
        self.assertGreaterEqual(report["covered"], 1)

    def test_english_pair_is_not_degraded(self):
        report = coverage_report(self.EN_ITEMS, self.EN_DOC)
        self.assertFalse(report["language_mismatch"])
        self.assertEqual(report["coverage_confidence"], "ok")
        self.assertGreaterEqual(report["covered"], 1)

    def test_both_sides_mixed_are_flagged_even_with_the_same_dominant_script(self):
        items = [
            {
                "text": "provide metadata 与 license 以及 preservation plan",
                "source": "s",
                "heading": "h",
                "stage": "reproducibility",
                "actionable": True,
                "navigation": False,
            }
        ]
        report = coverage_report(items, "provide metadata 与 license 以及 preservation plan 的说明")
        self.assertTrue(report["language_mismatch"])
        self.assertTrue(any("mixed-script" in item for item in report["warnings"]))

    def test_no_scored_items_is_unusable_not_clean(self):
        report = coverage_report([], self.EN_DOC)
        self.assertEqual(report["coverage_confidence"], "unusable")
        self.assertTrue(any("describes nothing" in item for item in report["warnings"]))


if __name__ == "__main__":
    unittest.main()


class ThinDenominatorTest(unittest.TestCase):
    """A one-item rubric is a routing artefact, not a verdict about the stage."""

    ITEMS = [
        {"id": "a", "text": "report the compute budget", "stage": "design"},
        {"id": "b", "text": "name the baseline", "stage": "design"},
        {"id": "c", "text": "state the stopping rule", "stage": "design"},
        {"id": "d", "text": "report variance across seeds", "stage": "design"},
        {"id": "e", "text": "describe the dataset split", "stage": "design"},
    ]

    def test_a_small_but_scoreable_pack_is_not_flagged_as_thin(self):
        report = coverage_report(self.ITEMS, "we report the compute budget and the baseline", "design")
        self.assertEqual(report["items"], 5)
        self.assertFalse(report["thin_denominator"])
        self.assertEqual(report["items_required_for_verdict"], 5)

    def test_a_thin_pack_reports_its_denominator_instead_of_a_bare_ratio(self):
        # one scored item: the stage filter keeps the row, the denominator is what is thin
        report = coverage_report(self.ITEMS[:1], "anything at all", "design")
        self.assertEqual(report["covered"], 0)
        self.assertTrue(report["thin_denominator"])
        notes = [w for w in report["warnings"] if "thin denominator" in w]
        self.assertEqual(len(notes), 1)
        self.assertIn("only 1 actionable item", notes[0])

    def test_an_empty_pack_stays_unusable_rather_than_thin(self):
        report = coverage_report([], "anything", "idea")
        self.assertEqual(report["coverage_confidence"], "unusable")
        self.assertFalse(report["thin_denominator"])


class BundleInputTest(unittest.TestCase):
    """A package directory is scored as the unit a reviewer reads, with the splice listed."""

    ITEMS = [
        {"text": "state the compute budget and hardware", "stage": "design"},
        {"text": "describe the dataset split", "stage": "design"},
        {"text": "report variance across seeds", "stage": "design"},
        {"text": "name the stopping rule", "stage": "design"},
        {"text": "tie each headline result to a baseline", "stage": "design"},
    ]

    def setUp(self):
        from research_agent.pack_audit import coverage_input

        self.coverage_input = coverage_input
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self) -> Path:
        (self.root / "README.md").write_text(
            "# Study\n- budget: 60 evaluations per arm; hardware windows 10, 16 logical cpus\n"
            "- seeds: 20 paired seeds; variance reported as 95% paired bootstrap intervals\n",
            encoding="utf-8",
        )
        (self.root / "study-preregistration.json").write_text(
            '{"decision_rule": "stop at 20 paired seeds", "baseline": "tuned cv baseline"}',
            encoding="utf-8",
        )
        (self.root / "study-evidence.json").write_text(
            '{"comparison": %s}' % json.dumps([{"mean_diff": 0.01}] * 200), encoding="utf-8"
        )
        (self.root / "study.json").write_text('{"cells": []}', encoding="utf-8")
        (self.root / "figure.png").write_bytes(b"\x89PNG")
        return self.root

    def test_a_directory_is_scored_as_a_bundle_and_lists_what_it_spliced(self):
        text, extra = self.coverage_input(self._package())
        bundle = extra["bundle"]
        self.assertEqual(bundle["unit"], "directory")
        self.assertEqual(bundle["file_count"], len(bundle["files"]))
        self.assertEqual(
            [item["path"] for item in bundle["files"]],
            ["README.md", "study-preregistration.json"],
        )
        self.assertEqual(
            bundle["excluded_numeric_artifacts"],
            ["study-evidence.json", "study.json"],
            "the numeric blobs are excluded by name, and the exclusion is printed",
        )
        self.assertEqual(bundle["skipped_unsupported_suffix"], 1)
        self.assertFalse(bundle["truncated"])
        report = coverage_report(self.ITEMS, text, "design")
        self.assertGreater(report["covered"], 0)

    def test_a_single_file_input_stays_a_single_file_input(self):
        directory = self._package()
        text, extra = self.coverage_input(directory / "README.md")
        self.assertIn("budget", text)
        self.assertEqual(extra, {})

    def test_an_over_long_bundle_reports_truncation_instead_of_scoring_quietly(self):
        directory = self._package()
        (directory / "huge.md").write_text("variance " * 400000, encoding="utf-8")
        text, extra = self.coverage_input(directory)
        bundle = extra["bundle"]
        self.assertTrue(bundle["truncated"])
        self.assertLessEqual(bundle["chars"], bundle["max_chars"])
