# Planned methodology

This is a protocol, not a report of findings. Phase 1 provides reproducible
ingestion, typed configuration/data, benchmark validation, and inspection. It does
not run retrieval comparisons, routing experiments, or model calls.

## Hypothesis and questions

The hypothesis is that choosing retrieval using information available before
retrieval can improve answer correctness while reducing inference cost and latency
relative to fixed vector, vectorless, and agentic policies. Correctness, cost, and
latency are separate outcomes; improving one does not establish all three. Report
tradeoffs rather than choosing a favorable composite score after evaluation.

Ask which strategies work for which questions, whether pre-retrieval features
predict useful choices, whether routing outperforms fixed policies, what resources
each system uses, and when escalation helps or fails. Null and negative results
are valid findings. Do not assume adaptive routing is superior.

## Corpus integrity

Use LangChain as the initial case study. Pin URL and full Git commit SHA, preserve
hierarchy, and retain source policy and hashes. Never silently advance the corpus.
Verify commit and evidence before validation and future execution.

Apply recorded exclusions for generated files, binaries, vendored dependencies,
repository metadata, build artifacts, extensions, and file sizes. All systems
receive the same included corpus. Review exclusions for missing documentation or
cross-file dependencies: hierarchy and file selection can favor particular
strategies. Evidence records relative paths, inclusive one-based ranges, and
SHA-256 checksums of UTF-8 lines joined with `\n` without a trailing newline.
Revalidate evidence and answers after corpus changes.

## Pilot and independent review

Construct 30 questions: 10 conceptual, 10 structural, and 10 cross-file. Allocate
five per category to development and five to held-out evaluation before tuning.
Use stable IDs and documented difficulty rationales. Keep near-duplicates and
questions sharing answer facts in the same split.

Each question needs an answer, evidence paths/ranges, commit, hashes, author
provenance, and independent review. Authors verify from source or reproducible
tests. Another reviewer checks answers and evidence at that exact snapshot. An LLM
answer is never accepted as unquestioned ground truth.

Validation checks structure, identity of source excerpts, split balance, and review
metadata. It cannot establish semantic correctness, reviewer identity, independence,
or absence of leakage. Human review must resolve ambiguity and unsupported claims.
The pilot is intentionally absent until authoring and review are complete. Do not
substitute artificial data or outcomes presented as validated evidence.

The pilot supports feasibility and failure discovery, not strong subgroup claims
or population-level generalization. Larger reviewed datasets and more repositories
are needed before broad conclusions.

## Planned comparison systems

All strategies will share an evidence-returning interface. Build useful fixed
baselines before adaptive routing.

| System | Planned behavior |
| --- | --- |
| Vector RAG | Language-aware chunks where feasible, embeddings, FAISS retrieval, source references. |
| Vectorless RAG | Deterministic hierarchy navigation, filename/keyword/symbol search, targeted reading. |
| Agentic RAG | Iterative directory, file, symbol, reading, and reference tools under explicit limits. |
| Rule-based adaptive | Predeclared query features select a strategy within budget. |
| LLM-based adaptive | Query and permitted pre-retrieval metadata guide strategy selection. |
| No retrieval | The same answer model answers without repository evidence. |

The no-retrieval baseline measures benefit beyond model knowledge and helps expose
public-source contamination. Repository code may have appeared in pretraining;
model release dates alone do not eliminate this risk. Record model identifiers
and this limitation. Question text and features must not expose answers or labels.

Routers may access only the query and explicitly permitted pre-retrieval metadata.
Record decisions and their inputs. Do not use held-out outcomes to choose features,
prompts, budgets, rules, or escalation thresholds. A post-hoc oracle may be a labeled
upper bound, but is not a deployable router. Do not train a classifier initially.

## Resource budgets

Use identical answer models and consistent generation settings wherever possible.
Fix generation token caps, prompt policy, retrieval/tool limits, and time limits
before held-out evaluation. Equal generation budgets do not equalize the extra
work of routing and iterative retrieval: measure all of it.

Include routing, failed tools, retries, escalation, and generation in end-to-end
latency, tokens, and query cost. Treat escalation as a separate predeclared
condition. Do not keep only a successful attempt and discard preceding work.
Record indexing/embedding costs separately; state workload size for amortization.
Retain pricing dates, usage, prompt/context sizes, cache behavior, environment, and
concurrency. Missing provider usage is not zero cost.

## Outcomes and scoring

Predeclare a correctness rubric that can credit partial answers and detect
unsupported or contradictory claims. Blind reviewers to system identity where
feasible; retain disagreement and adjudication. Automated graders need versioned
prompts and calibration against manual review, rather than being assumed correct.

Measure correctness, evidence recall, citation correctness, end-to-end latency,
input/output tokens, estimated API cost, tool calls, and selected strategy. Retain
routing errors, failures, retries, and escalation. Define required evidence and a
consistent process for adjudicating valid alternatives. A real citation is not
automatically a supporting citation. Analyze retrieval and generation failures
separately while retaining end-to-end outcomes.

## Execution and analysis

Preregister split, primary outcomes, scoring, budgets, stochastic run count,
comparisons, and exclusion rules before held-out execution. Tune on development
only. Label later protocol changes as new versions or exploratory analysis.

Run conditions on the same questions and replicates. Save seeds where supported
and acknowledge provider nondeterminism. Balance/randomize execution order to
reduce cache, load, and order effects. Preserve unsuccessful and interrupted runs
with explicit status in failure and resource accounting.

Compare paired question outcomes and account for repeated runs within each
question instead of treating generated answers as independent samples. Report
condition values, paired differences, sample sizes, and uncertainty intervals.
Avoid overinterpreting significance tests in a small pilot. Predeclare primary
comparisons and address multiplicity or label exploratory work. Category analyses
need adequate sample sizes before supporting strong claims.

Keep raw JSONL separate from aggregates, figures, and tables. Each analysis names
raw run IDs and code revision. Record framework/repository SHAs, configurations,
prompts, timestamps, model identifiers, manifests, benchmark revision, and
environment. Retain negative and failed experiments. Write conclusions only after
the corresponding evidence exists.

## Validity limits and next step

One small public-repository case study has limits. Source selection, questions,
categories, scoring, reviewers, and budgets can influence outcomes. Pretraining
contamination, correlated questions, model changes, and provider latency variation
are material risks. Provenance and structural validation improve auditability but
do not remove them. Report limitations and protocol departures with failure modes.

Next, author and independently verify the balanced pilot at the pinned snapshot.
Phase 2 requires explicit approval; retrieval, routing, and model integration are
outside the current implementation.
