"""Argument hygiene is enforced once, in the shared dispatch, not per handler by memory.

Measured before these tests existed: 42 of 46 handlers called `_reject_unknown` themselves, one
(`research_host_contract`) did not, and two schemas did not even declare
`additionalProperties: false`. The MCP face looked safe only because the client validated against
the schema; an HTTP or in-process caller reached the handler and got a silently different answer -
a host sending `{"declared": [...]}` instead of `{"capabilities": [...]}` received a contract
computed from no declared capabilities, with no error.

The expectations here are derived from the live registry, so a tool added tomorrow is covered
without anyone remembering to add a case. That is the same reason the runtime's write guard is a
middleware: a check that depends on being remembered per call site does not scale.
"""

import unittest

from research_agent.mcp_server import TOOL_SCHEMAS, dispatch_tool, unknown_argument_problem
from research_agent.mcp_tools import TOOLS


class Tripwire:
    """Stands in for the service: reaching it means a handler ran when it must not have."""

    def __getattr__(self, item):
        raise AssertionError("handler attribute %r was reached despite an unknown argument" % item)


class SchemaConstraintTest(unittest.TestCase):
    def test_every_tool_schema_forbids_additional_properties(self):
        unconstrained = sorted(
            name for name, schema in TOOL_SCHEMAS.items()
            if schema.get("additionalProperties") is not False
        )
        self.assertEqual(
            unconstrained, [],
            "these tools accept undeclared keys at the schema level, so the MCP face and the "
            "dispatch face disagree about what a valid call is",
        )

    def test_the_schema_map_covers_exactly_the_registered_tools(self):
        self.assertEqual(sorted(TOOL_SCHEMAS), sorted(tool["name"] for tool in TOOLS))


class DispatchRefusesBeforeExecutingTest(unittest.TestCase):
    def test_an_unknown_argument_is_refused_for_every_tool_without_running_it(self):
        refused = 0
        for tool in TOOLS:
            name = tool["name"]
            result = dispatch_tool(Tripwire(), name, {"__not_a_declared_argument__": 1})
            self.assertTrue(result.get("isError"), "%s did not refuse an unknown argument" % name)
            text = result["content"][0]["text"]
            self.assertIn("unknown argument", text)
            self.assertIn(name, text)
            refused += 1
        self.assertEqual(refused, len(TOOLS), "the registry shrank; this test is not enumerating")

    def test_the_refusal_names_what_the_tool_actually_declares(self):
        problem = unknown_argument_problem(
            "research_host_contract", {"declared": ["can_call_tools"]}
        )
        self.assertIn("declared", problem)
        self.assertIn("capabilities", problem)

    def test_declared_arguments_are_not_refused_by_the_rule(self):
        self.assertEqual(
            unknown_argument_problem(
                "research_host_contract", {"capabilities": ["can_call_tools"]}
            ),
            "",
        )
        self.assertEqual(unknown_argument_problem("research_host_contract", {}), "")

    def test_a_wrong_payload_type_is_left_to_the_handler(self):
        # this rule is about undeclared keys; type validation stays where the handler can explain it
        self.assertEqual(unknown_argument_problem("research_run", "not-a-dict"), "")
        self.assertEqual(unknown_argument_problem("research_run", None), "")

    def test_an_unknown_tool_is_not_reported_as_an_unknown_argument(self):
        self.assertEqual(unknown_argument_problem("research_made_up", {"x": 1}), "")


if __name__ == "__main__":
    unittest.main()
