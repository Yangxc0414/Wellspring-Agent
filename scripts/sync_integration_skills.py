"""Sync the canonical research-workflow skill to all client skill folders."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".qoder" / "skills" / "research-workflow" / "SKILL.md"
TARGETS = (
    ROOT / ".claude" / "skills" / "research-workflow" / "SKILL.md",
    ROOT / ".zcode" / "skills" / "research-workflow" / "SKILL.md",
)


def main() -> int:
    # normalise so the client copies are byte-identical to the canonical file: a CRLF
    # edit in one folder otherwise shows up as silent per-line drift in every other client
    text = CANONICAL.read_text(encoding="utf-8").replace("\r\n", "\n")
    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(str(target), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        print("synced:", target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
