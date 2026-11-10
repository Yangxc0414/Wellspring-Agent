import assert from "node:assert/strict";
import test from "node:test";

import {
  authHeaders,
  clearRuntimeToken,
  describeAuthRefusal,
  runtimeToken,
  setRuntimeToken
} from "../src/adapters/runtimeAuth.ts";

test("no token means no Authorization header at all", () => {
  clearRuntimeToken();
  const headers = authHeaders();
  assert.deepEqual(headers, {});
  // an empty "Bearer " would be worse than none: the server compares digests and would 401
  assert.equal("Authorization" in headers, false);
  assert.equal(runtimeToken(), "");
});

test("a token is sent as a Bearer credential and trimmed", () => {
  setRuntimeToken("  s3cret  ");
  assert.deepEqual(authHeaders(), { Authorization: "Bearer s3cret" });
  assert.equal(runtimeToken(), "s3cret");
  clearRuntimeToken();
  assert.deepEqual(authHeaders(), {});
});

test("a 401 keeps the server's own words and adds the remedy", () => {
  const body = JSON.stringify({
    detail: "invalid research API token",
    boundary: "every mutating route on this runtime needs the same credential"
  });
  const message = describeAuthRefusal(401, body);
  assert.ok(message.includes("invalid research API token"), message);
  assert.ok(message.includes("researchRuntimeAuth.setToken"), message);
});

test("a 403 points at the loopback rule, not at a token paste", () => {
  const message = describeAuthRefusal(403, "research API is loopback-only");
  assert.ok(message.includes("loopback"), message);
  assert.ok(message.includes("RESEARCH_AGENT_API_TOKEN"), message);
});

test("other statuses are not auth refusals", () => {
  assert.equal(describeAuthRefusal(500, "boom"), "");
  assert.equal(describeAuthRefusal(404, "missing"), "");
  assert.equal(describeAuthRefusal(422, "payload"), "");
});
