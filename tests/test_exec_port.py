import unittest

from research_agent.execport.exec_port import (
    EXEC_PORT_SCHEMA,
    ExecFace,
    ExecPortError,
    describe,
    register_face,
    registered_faces,
    resolve,
)


class ExecPortTest(unittest.TestCase):
    def test_three_real_faces_are_registered(self):
        self.assertEqual(
            registered_faces(), ["bridge", "host_agent", "inprocess"]
        )
        self.assertEqual(resolve("bridge").interpreter, "3.12")
        self.assertEqual(resolve("inprocess").interpreter, "3.8")
        self.assertEqual(resolve("host_agent").interpreter, "host")

    def test_describe_is_a_read_only_projection(self):
        payload = describe()
        self.assertEqual(payload["schema_version"], EXEC_PORT_SCHEMA)
        self.assertEqual(
            [f["kind"] for f in payload["faces"]],
            ["bridge", "host_agent", "inprocess"],
        )
        self.assertTrue(payload["boundary"])
        for face in payload["faces"]:
            self.assertTrue(face["authorization"])
            self.assertTrue(face["entry"])

    def test_unknown_kind_is_rejected_not_guessed(self):
        with self.assertRaises(ExecPortError):
            resolve("docker")

    def test_new_face_can_register_and_duplicate_is_rejected(self):
        face = ExecFace(
            kind="conda-test", name="conda", interpreter="3.10",
            entry="future/conda_runner.py", isolation="conda env process",
            authorization="user-approved env only",
        )
        register_face(face)
        try:
            self.assertIn("conda-test", registered_faces())
            self.assertEqual(resolve("conda-test").interpreter, "3.10")
            with self.assertRaises(ExecPortError):
                register_face(face)
            with self.assertRaises(ExecPortError):
                register_face(ExecFace("", "x", "3.8", "e", "i", "a"))
        finally:
            from research_agent.execport import exec_port
            exec_port._FACES.pop("conda-test", None)


class DispatchTest(unittest.TestCase):
    """路由分派（71-§5 步 5 收口）：分派经端口门禁 + 溯源，未注册面拒绝执行。"""

    def test_begin_dispatch_gates_unknown_face(self):
        from research_agent.execport.exec_port import ExecPortError, begin_dispatch

        with self.assertRaises(ExecPortError):
            begin_dispatch("docker-test", subject="x")

    def test_begin_and_end_update_provenance(self):
        from research_agent.execport import exec_port

        before = exec_port._DISPATCH_COUNTS.get("bridge", 0)
        ticket = exec_port.begin_dispatch("bridge", subject="m2-run")
        self.assertEqual(ticket["face"], "bridge")
        self.assertEqual(ticket["status"], "dispatched")
        exec_port.end_dispatch(ticket, "completed")
        self.assertEqual(ticket["status"], "completed")
        self.assertEqual(exec_port._DISPATCH_COUNTS["bridge"], before + 1)

    def test_describe_includes_dispatch_stats(self):
        from research_agent.execport import exec_port

        exec_port.begin_dispatch("inprocess", subject="pipeline-run")
        payload = exec_port.describe()
        self.assertIn("dispatch_stats", payload)
        self.assertIn("inprocess", payload["dispatch_stats"]["counts"])


if __name__ == "__main__":
    unittest.main()