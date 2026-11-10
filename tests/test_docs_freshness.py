"""Living docs must not carry a stale MCP tool count.

Historical logs (`58-…`, `4x-…`, `5x-…`, module SPEC changelogs) are dated records and are
deliberately not checked: they describe what was true when they were written.
"""

import re
import unittest
from pathlib import Path

from research_agent.mcp_server import TOOL_NAMES

REPO = Path(__file__).resolve().parents[1]
LIVING_DOCS = (
    "README.md",
    "QUICKSTART.md",
    "ARCHITECTURE.md",
    "integrations/README.md",
    "integrations/codex/README.md",
)
COUNT = re.compile(r"([0-9]{2,3})\s*(?:个)?\s*工具")


class DocToolCountTest(unittest.TestCase):
    def test_living_docs_do_not_quote_a_stale_tool_count(self):
        expected = len(TOOL_NAMES)
        stale = []
        for relative in LIVING_DOCS:
            path = REPO / relative
            self.assertTrue(path.is_file(), "missing living doc: " + relative)
            for number in COUNT.findall(path.read_text(encoding="utf-8")):
                if int(number) != expected:
                    stale.append("%s says %s tools, registry has %d" % (relative, number, expected))
        self.assertEqual(stale, [], "stale tool counts in docs:\n" + "\n".join(stale))

    def test_registry_count_is_not_hardcoded_to_zero(self):
        self.assertGreater(len(TOOL_NAMES), 30)
        self.assertEqual(len(set(TOOL_NAMES)), len(TOOL_NAMES))


if __name__ == "__main__":
    unittest.main()
