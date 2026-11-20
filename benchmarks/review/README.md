# Pilot benchmark: human review

This packet contains 30 **AI-assisted draft annotations** for the pinned LangChain
source. Human review is complete: **30 accepted; none pending**.
The reviewed evaluation dataset is frozen as [pilot.jsonl](../pilot.jsonl), with
its hashes and provenance in the [freeze manifest](../pilot.freeze.json).
These are reference annotations,
not experiment outputs or research results.
Source excerpts are from LangChain, copyright LangChain, Inc., under the
[included MIT license](SOURCE-LICENSE.txt).

Accepted by Shekhar: all 15 held-out annotations and all 15 development
annotations. The final confirmation accepts revised `lc-c-02`, with the direct
`Serializable.to_json()` wording, unchanged answer, and expanded evidence.

The [development questions](development.md) and
[held-out questions](held-out.md) preserve the accepted annotations separately.
Each packet contains 15 questions:
five conceptual, five structural, and five cross-file. Every question includes its
proposed answer, difficulty rationale, verification notes, source links, exact
line-numbered source excerpts, and excerpt hashes.

## Review procedure

1. Read each question and its proposed answer. Check the cited source excerpts;
   use the local or pinned GitHub links when you need surrounding context.
2. Check that the question is unambiguous, the full answer follows from the source,
   and the cited ranges include the evidence needed. Cross-file answers should
   require reasoning across the cited implementation files.
3. Check the category, difficulty, and split. Flag near-duplicates or shared answer
   facts across development and held-out questions. The balance is five questions
   per category in each split, but balance alone does not establish independence.
4. For each ID, record **accept**, **revise**, or **reject**, with a short reason.
   For revisions, give the corrected wording/answer or identify the unsupported
   claim. Tell Codex your decisions in chat, or edit a copy of
   [the optional decision template](decisions.template.jsonl).
5. Supply the reviewer name you want recorded and confirm that you inspected the
   source. An actual timezone-aware review timestamp and verification notes will
   be recorded when your decisions are applied. Codex will not invent your name,
   timestamp, inspection, or approval.

For example, after inspecting the actual excerpt you can reply:

> Reviewer: [your name]. I inspected the cited source for [question IDs].
> Accept: [IDs and verification notes].
> Revise: [ID, issue, and correction].
> Reject: [ID and reason].

You do not need to edit JSON. You can review five questions at a time. Assistant
cross-checks and passing mechanical validation do not count as human review.
If someone else performs the independent review, record their actual identity and
decisions with their authorization.

## AI source cross-check

Shekhar supplied a Claude Code report (reported model `claude-fable-5-2`)
recommending acceptance of all 15 held-out annotations and confirmation of the
revised `lc-c-02`. The [recorded AI report](ai-cross-checks/claude-2026-11-15-01.json)
is bound to the dataset and annotation hashes at the time it was recorded.
That report remains unchanged. Shekhar subsequently attested human source
inspection and adopted the 15 held-out acceptance decisions in the fourth human
review batch. The AI report and the later human acceptance are recorded
separately. The later acceptance metadata changes the full annotation hashes;
question text, answers, and source evidence are unchanged. Shekhar separately
confirmed revised `lc-c-02` in the final human review batch. Human review is
complete: **30 accepted; none pending**.

## Files and current status

- [Final authoring record](../pilot.draft.jsonl): all 30 annotations have
  Shekhar's recorded acceptance and match the frozen evaluation dataset.
  The author is `Codex (AI-assisted draft)`.
- [Review decisions](decisions.jsonl): the actual accept/revise decisions, reviewer
  notes, before/after annotation hashes, and recording timestamps.
- [First review batch](history/shekhar-2026-11-15-01/attestation.json): Shekhar's
  four acceptances and requested correction.
- [Second review batch](history/shekhar-2026-11-15-02/attestation.json): Shekhar's
  five structural acceptances.
- [Third review batch](history/shekhar-2026-11-15-03/attestation.json): Shekhar's
  five cross-file acceptances.
- [Fourth review batch](history/shekhar-2026-11-15-04/attestation.json): Shekhar's
  source-inspection attestation and adoption of all 15 held-out acceptances.
- [Final review batch](history/shekhar-2026-11-16-01/attestation.json): Shekhar's
  acceptance of revised `lc-c-02`. The history folders preserve the prior
  datasets and packets. No separate
  inspection time was supplied; recorded review timestamps identify when each
  attestation was recorded.
- [Authoring validation](validation-authoring.json): checks schema, source pin,
  eligible files, line ranges, hashes, duplicates, and pilot balance, with review
  explicitly not required.
- [Review-required validation](validation-review-required.json): passes with all
  30 independently accepted annotations and no errors.
- [Packet manifest](manifest.json): draft hash, source/corpus identity, counts,
  evidence sizes, annotation hashes, and any overlapping evidence across splits.
- [Decision template](decisions.template.jsonl): empty because no annotations
  remain pending. This is not an evaluation input.

The configured evaluation dataset, `benchmarks/pilot.jsonl`, now contains all 30
accepted annotations. Strict pilot validation passes. Preserve this frozen
dataset and split; later revisions require a new version and renewed review.

## Scope and split discipline

Source commit: `ea17e48f0a4336c920394fd029de99f1568b4c38`.

This is a purposive feasibility pilot drawn from selected source interfaces and
implementation paths, mainly in `langchain_core` with the text-splitter code when
needed. It is not a random or representative sample of all LangChain use cases.
Difficulty labels are author judgments for you to check, not measured difficulty.
Related implementation topics are kept within the same split where possible;
related questions within a split can still be correlated.

The initial domain allocation was chosen before experiment execution: development
covers output parsing, serialization, messages, embeddings, and document loading;
held-out covers tools, retrieval/vector stores, runnable composition, chat-model
caching, and history/rate limiting. No retrieval strategy performance was used to
select questions, set difficulty, or allocate the split.

Held-out answers are visible here only for annotation review. Keep them out of
router development prompts, examples, and tuning decisions. Use development-only
materials in a fresh development context when implementing the routers; this
authoring conversation has seen the held-out annotations. Freeze the approved
benchmark and split before tuning or interpreting held-out results.

No framework provider inference, vector-index construction, answer experiment,
or experiment-output judge was run while preparing this packet. Completed
annotation review establishes the reference dataset; it does not measure
retrieval or answer quality.
