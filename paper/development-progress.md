# Development progress (derived snapshot)

Generated from execution/accounting metadata only. This is not an accuracy result or an instruction to start, retry, or resume a run.

Run: `adaptive-anthropic-paced-development-20261117-001`  
Status: **completed_with_errors**  
Recorded/planned: **270 / 270**  
Finished: **True**

Used-or-reserved figures are admission estimates, not actual billed totals. Unknown actual usage remains unknown. During execution, accounting covers durable job records and excludes the current in-flight job.

```json
{
  "run": "adaptive-anthropic-paced-development-20261117-001",
  "status": "completed_with_errors",
  "recorded": 270,
  "planned": 270,
  "status_counts": {
    "budget_exhausted": 36,
    "completed": 225,
    "error": 9
  },
  "elapsed_minutes": 104.88,
  "elapsed_is_approximate": false,
  "accounting_scope": "final snapshot",
  "known_cost_subtotal_usd": 7.56634852,
  "complete_estimated_cost_usd": null,
  "budget_used_or_reserved": {
    "policy": "reserve",
    "interpretation": "Used-or-reserved admission estimates; not actual billed usage.",
    "usage": {
      "input_tokens": 6826864,
      "output_tokens": 153956
    },
    "estimated_cost_usd": 7.5939195199999965,
    "reserved_unknown_calls": 1,
    "unreserved_unknown_calls": 0,
    "unknown_cost_jobs": 0
  },
  "unknown_usage_calls": 1,
  "last_event": "job_finished",
  "last_error": "token budget cannot admit the next prompt and reserved output",
  "finished": true,
  "read_notes": []
}
```
