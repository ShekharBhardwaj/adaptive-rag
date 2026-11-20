# Human review: paced Anthropic development run

Execution has finished for
[`adaptive-anthropic-paced-development-20261117-001`](../../raw/adaptive-anthropic-paced-development-20261117-001/).
All 270 planned jobs were recorded: 225 completed, 36 exhausted a budget, and
9 ended in error. No jobs are missing. **227 answer texts are available**:
the 225 completed jobs and two answers rejected for unknown citation IDs.
**All 16 packets are complete: 227 user-submitted ratings from Shekhar are
validated, with zero answer reviews pending.** The final batch for Packets 15
and 16 was written on **November 17, 2026 at 9:53:44 PM New York time (EST)**.
At Shekhar's request, all 227 active `reviewed_at` values now use the original
packet score-file write times. Packet 1 has no standalone score file, so its
accepted submission-file write time is used as a documented proxy. These are
recording timestamps; human review-completion times were not independently
measured. The [timestamp correction](corrections/write-times-001/correction.json)
records each source file and original write time. The original supplied times,
score bytes, and [submission records](submissions/) remain preserved as history.

The final 17 proposed score pairs were checked against the frozen answers and
pinned source by AI before being recorded unchanged; this check is separate
from the submitted reviewer judgments. Grades, notes, and output bindings are
unchanged by the timestamp correction.

The submitted totals are **100 fully correct, 31 partial, 84 abstentions and
12 incorrect attempted answers**. Citation support is N/A for 84 answers and
scored independently for 143. See [review progress](review-progress.json), the
[final review summary](final-review-summary.json), and the
[reviewed development report](../../../paper/phase5-paced-development-run.md#reviewed-development-results).
The [final aggregate](../../aggregates/adaptive-anthropic-paced-development-20261117-001-reviewed-write-times-001.json)
counts all failed attempts as zero in its primary correctness comparison.
No further answer-review packet is pending; held-out evaluation has not started.
The [shuffled template](answers.review-template.jsonl) uses review seed 0.
The 16 packets preserve that order: fifteen packets of 15 items and a final
packet of two items.

| Packet | Items | Packet | Items |
| --- | --- | --- | --- |
| [1](review-packets/packet-001.md) | 1–15 | [9](review-packets/packet-009.md) | 121–135 |
| [2](review-packets/packet-002.md) | 16–30 | [10](review-packets/packet-010.md) | 136–150 |
| [3](review-packets/packet-003.md) | 31–45 | [11](review-packets/packet-011.md) | 151–165 |
| [4](review-packets/packet-004.md) | 46–60 | [12](review-packets/packet-012.md) | 166–180 |
| [5](review-packets/packet-005.md) | 61–75 | [13](review-packets/packet-013.md) | 181–195 |
| [6](review-packets/packet-006.md) | 76–90 | [14](review-packets/packet-014.md) | 196–210 |
| [7](review-packets/packet-007.md) | 91–105 | [15](review-packets/packet-015.md) | 211–225 |
| [8](review-packets/packet-008.md) | 106–120 | [16](review-packets/packet-016.md) | 226–227 |

The setup uses direct Anthropic Claude Haiku 4.5 chat for routing, navigation,
and answers, with Qwen query embeddings and the existing compatible vector
index. The single fresh development plan has 270 jobs, a two-hour run cap,
12 million budgeted tokens, 2,000 model attempts, and a $9.90 estimated admission
allocation. At most $0.10 is allocated separately to synthetic preflight.
The gate was configured for six seconds between starts and ten starts per
rolling minute. Recorded chat wall timestamps include one 5.945952-second gap
and a rolling-minute peak of 11; the execution report documents that audit
exception separately. No automatic retries or reruns are scheduled.

The opt-in `reserve` accounting policy can admit later jobs using a separate
serialized-input-byte/full-output reservation when provider usage is missing.
The affected job stays failed, its actual missing usage and complete cost remain
unknown, and no replacement request is made. Review available text on its
content; execution status and correctness are assessed separately.

## Review procedure

1. Open Packet 1 and continue in packet order, or use the shuffled template.
   Packets are already generated. To create another working copy, use a fresh
   output directory from the repository root:

   ```sh
   python3 experiments/reviews/adaptive-anthropic-paced-development-20261117-001/render_review_packets.py \
     --output-dir /path/to/a/fresh/review-packets-copy
   ```

   The helper reads only this directory's template, preserves its shuffled order
   and opaque bindings, and adds blank human-rating fields. It refuses to
   overwrite an existing packet directory.
2. Work through the template or packets in order. Keep conditions and selected
   strategies hidden: do not inspect raw results, traces, routing decisions,
   summaries, or job-ID mappings while scoring. Answer style may still reveal a
   condition, so this blinding has limits.
3. Compare each answer with its question and reference answer, then check its
   claims against the cited and gold source ranges in the
   [pinned checkout](../../../datasets/repos/langchain/) at the item's
   `repo_commit`. Agreement with the reference or a valid citation ID alone does
   not prove correctness or semantic support. Explain source disagreements in
   your notes.
4. An actual human reviewer completes the nested `score` object using their real
   identity and review time. Packet notes are a working aid; transfer completed
   judgments to the matching score object. Never invent reviews or label an
   automated judgment as human review. Leave unfinished items pending.
5. Save only nested `score` objects with completed human judgments as
   `answers.scores.jsonl` here, one JSON object per line. Exclude outer template
   fields and pending items.
   Preserve the filled template as a working copy and leave raw artifacts intact.

| Editable field | Required value |
| --- | --- |
| `reviewer` | Nonempty human reviewer identity. |
| `reviewed_at` | Timezone-aware ISO 8601 timestamp, not earlier than the output. For this completed run, corrected to original packet-file write time at user request; see the timestamp correction above. |
| `correctness` | Finite number in [0, 1]: `0` incorrect, `0.5` partly correct, `1` fully correct; justify other values in `notes`. |
| `citation_support` | Finite number in [0, 1] for semantic source support, or `null` when not applicable. |
| `notes` | Nonempty justification, including source checks and limitations. |

Preserve `schema_version: "1"`, `rubric_version: "manual-v1"`, `run_id`, `job_id`,
and `output_sha256` exactly. These bindings identify the exact frozen output;
do not recompute them. Use JSON numbers, not strings or booleans. Editable nulls
mean pending, except that `citation_support` may remain null when not applicable.
Pending judgments are not zero scores. Missing answer text cannot receive a
score; available partial text may be reviewed without erasing its execution
failure.

The final aggregate is already saved. For a later offline reanalysis, summarize
from the repository root with a fresh output path:

```sh
uv run adaptive-rag experiment summarize \
  experiments/raw/adaptive-anthropic-paced-development-20261117-001 \
  --reviews experiments/reviews/adaptive-anthropic-paced-development-20261117-001/answers.scores.jsonl \
  --bootstrap-samples 2000 --seed 0 \
  --output experiments/aggregates/adaptive-anthropic-paced-development-20261117-001-reviewed-reanalysis-001.json
```

Validation rejects stale hashes, duplicate or unknown jobs, invalid scores, and
scores without answer text. Report missing reviews and review coverage alongside
any correctness result. See the
[scoring workflow](../../README.md#independent-answer-review).
The [execution report](../../../paper/phase5-paced-development-run.md) includes
condition labels and aggregate outcomes; leave it closed until scoring is
complete to preserve blinding. After development review, freeze any protocol
decisions before beginning held-out evaluation.
