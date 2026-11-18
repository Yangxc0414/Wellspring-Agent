"""Fetch a frontier ESE corpus (arXiv cs.SE) into a local directory for the pipeline.

The corpus stays in runtime_data/ (gitignored): arXiv licenses vary, so nothing is
committed and the license note is recorded per paper. The pipeline consumes the downloaded
PDFs through --corpus-dir and parses them locally; abstracts never become evidence.

Frontier mode (2026-11):
    python scripts/fetch_se_corpus.py --topics "flaky test,test co-change,bug-fix commit" \
        --months 6 --max-papers 24 --target-dir runtime_data/se-corpus-frontier/pdfs

The months window filters by arXiv published date; multiple topics are deduplicated by
arXiv id. Larger source counts matter: with 8 papers the pipeline declared coverage
saturated and produced only 3 candidates; the idea stage needs more frontier coverage.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.adapters.arxiv_fetcher import ArxivFetchError, ArxivFetcher  # noqa: E402


def _published_cutoff(months):
    if not months:
        return ""
    today = datetime.date.today()
    # 30-day months are enough for a retrieval window; the manifest records the exact cutoff.
    return (today - datetime.timedelta(days=30 * months)).isoformat()


def main(argv=None):
    parser = argparse.ArgumentParser(description="fetch arXiv cs.SE papers into a local corpus")
    parser.add_argument("--topic", default="flaky test")
    parser.add_argument("--topics", default="", help="comma-separated topics; overrides --topic")
    parser.add_argument("--months", type=int, default=0, help="only keep papers published in the last N months")
    parser.add_argument("--max-papers", type=int, default=8)
    parser.add_argument("--target-dir", default="runtime_data/se-corpus/pdfs")
    parser.add_argument("--max-results", type=int, default=40)
    args = parser.parse_args(argv)

    topics = [item.strip() for item in (args.topics or args.topic).split(",") if item.strip()]
    cutoff = _published_cutoff(args.months)
    fetcher = ArxivFetcher()
    target = Path(args.target_dir)
    target.mkdir(parents=True, exist_ok=True)
    downloaded = []
    seen = set()
    per_query = {}
    queries = []
    for topic in topics:
        query = 'cat:cs.SE AND all:"%s"' % topic.replace('"', "")
        queries.append({"topic": topic, "query": query})
        try:
            results = fetcher.search_query(query, max_results=args.max_results, sort_by="submittedDate")
        except ArxivFetchError as exc:
            print("search failed for %s: %s" % (topic, exc))
            per_query[topic] = 0
            continue
        kept = 0
        for result in results:
            if cutoff and str(result.get("published") or "")[:10] < cutoff:
                continue
            arxiv_id = str(result.get("arxiv_id") or "")
            if not arxiv_id or arxiv_id in seen:
                continue
            if len(downloaded) >= max(1, min(args.max_papers, 40)):
                break
            try:
                saved = fetcher.download(result, target)
            except ArxivFetchError as exc:
                print("skip %s: %s" % (arxiv_id, exc))
                continue
            seen.add(arxiv_id)
            downloaded.append({
                "arxiv_id": arxiv_id,
                "title": result.get("title"),
                "year": result.get("year"),
                "published": result.get("published"),
                "comment": result.get("comment"),
                "url": result.get("url"),
                "pdf": saved.get("pdf_path") or saved.get("path"),
                "sha256": saved.get("sha256"),
                "license_note": result.get("license_note"),
                "topic": topic,
            })
            kept += 1
            print("[{0}/{1}] {2}".format(len(downloaded), args.max_papers, result.get("title")))
        per_query[topic] = kept
        if len(downloaded) >= max(1, min(args.max_papers, 40)):
            break

    manifest = target.parent / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps({
            "schema": "se-corpus-0.2",
            "queries": queries,
            "topics": topics,
            "months": args.months,
            "published_cutoff": cutoff,
            "per_query_counts": per_query,
            "count": len(downloaded),
            "papers": downloaded,
            "boundary": (
                "local research use only; arXiv licenses vary, do not redistribute the PDFs; "
                "a preprint corpus is not a peer-reviewed benchmark"
            ),
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("corpus: %d papers -> %s" % (len(downloaded), target))
    print("manifest: %s" % manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
