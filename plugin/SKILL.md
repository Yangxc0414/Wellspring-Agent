# research-agent plugin skill

Drive the runtime over whichever transport this host actually has. Follow these steps in order and stop where it says to stop.

1. Negotiate first: `python -m research_agent handoff contract --capabilities <can_call_tools,can_write_files,can_serve_model>` (or the `research_host_contract` equivalent over MCP). Read `blocked` and `next_commands` before starting a run.
2. Choose a transport. Tools available -> MCP. Files only -> `handoff export`, answer `outbox/MT-*.answer.json`, `handoff import`, then re-run the deferred step; it replays recorded answers instead of asking again.
3. Run the research task with a project directory inside the user's workspace. Every artifact stays in that directory.
4. Who supplies the model. On a platform host like Qoder, you do: answer each pending turn with your own model, and no API key is needed anywhere. On a plain CLI client with no agent to answer, bind a keyed profile once instead. An answer is capability output: it still passes shape validation, citation whitelists and result-number limits.
5. Stop at the gate. Claim signature, G1/G2 decisions, protocol freeze, closure signature, publishing and export approval are not offered to any transport. Show the CLI command and let the human run it. For a specific run the exact command is `research_status` -> `closure_profiles.canonical_run[].claim_draft.command` (project-relative, already carrying the proposed `--assertion`); it disappears once the run is signed.
6. Only if the human already wrote an autopilot policy, you may run `python -m research_agent autopilot research --project <dir> --topic <topic> --policy <policy.json>` to go from a topic to a sealed bundle, or `autopilot run --project <dir> --run-id <RUN-ID> --policy <policy.json>` to finish an existing run. It can never create or widen a policy, and it refuses out-of-scope runs. Never write a policy on the human's behalf.

The runtime root for this bundle is `<RESEARCH_AGENT_ROOT>`. Verify the bundle after any change with `python -m research_agent plugin verify`.
