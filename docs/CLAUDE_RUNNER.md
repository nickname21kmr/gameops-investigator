# Claude runner result handling

The runner requests `--output-format json` and treats process status and Agent result status separately. An exit code of zero alone does not make a response usable.

## Accepted response

The current text-report integration requires a JSON object containing:

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "result": "A non-empty report"
}
```

`is_error` must be a boolean, not `0` or `"false"`; `result` must be a non-whitespace string. Extra metadata is preserved in the successful `payload`. This validates the fields needed by this integration, not every field in the full SDK schema. Bare text, a bare `{"result": "..."}` object, streaming message arrays, and structured-output-only responses are not accepted as successful text reports. No fallback turns malformed output into a report.

## Failure results

| `error_code` | Meaning |
| --- | --- |
| `process_failed` | The Claude process exited with a nonzero code. |
| `invalid_json` | Its stdout could not be parsed as JSON. |
| `invalid_response` | JSON was readable but did not satisfy the supported result contract. |
| `agent_result_error` | The result reports an error or a known incomplete-run subtype, even if the process exit code is zero. |

Known error subtypes are `error_max_turns`, `error_during_execution`, `error_max_budget_usd`, and `error_max_structured_output_retries`. Unknown subtypes are rejected until explicitly supported. Process errors take precedence over interpreting stdout.

These failures return `ok: false`, a fixed diagnostic message, elapsed time, and the subprocess `returncode`; they omit raw stdout, stderr, and `payload`. The GameOps CLI exits with `1` even when the recorded subprocess return code is `0`. The workbench shows an error, and evaluation exports record failure. Existing `timeout` and `launch_failed` handling remains in place. Nothing automatically retries a failed run.

For malformed or unsupported responses, check the local Claude Code version and output format. For an Agent error, inspect the run locally before retrying or changing limits. Raw diagnostics may include prompts, paths, or account details; do not paste them into public issues without review. Successful payloads still include model text and metadata and are **not** sanitized by this validation.

## Verification boundary

Tests simulate process output, including valid success, malformed responses, and failures that accompany exit code zero. They do not spend model credits or establish live model quality. A valid response envelope is not proof of correct analysis, citations, or task completion; human review is still required. Authentication discovery is separate from this output validation.

The expected fields and result subtypes follow the official [programmatic CLI guide](https://code.claude.com/docs/en/headless) and [Agent loop result handling](https://code.claude.com/docs/en/agent-sdk/agent-loop).
