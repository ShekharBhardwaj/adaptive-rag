# Held-out questions: review only

Status: **AI-assisted pilot; 15 accepted, 0 pending independent acceptance in this packet.**

Source commit: `ea17e48f0a4336c920394fd029de99f1568b4c38`. Draft SHA-256: `e4c33c295518876c2b7537eff5fca281dd41b4779564062b41f0672220016a71`.

These are proposed reference answers, not measured experiment outputs. Check the answer against every cited excerpt; correct or reject unsupported claims.

[Review instructions](README.md). Record accept / revise / reject and a reason for each question. You can send decisions and corrections in chat using the IDs; Codex will transcribe only the decisions you actually provide.

Keep these questions and answers out of router prompts, examples, and tuning. Reviewing their annotations does not authorize using them for development.

## Questions

- [lc-c-06](#lc-c-06): In BaseTool.run, how do handle_validation_error and handle_tool_error affect caught errors, and does handle_tool_error=True also suppress an ordinary ValueError raised by the tool implementation? Assume any configured handler returns normally.
- [lc-c-07](#lc-c-07): How does synchronous VectorStoreRetriever._get_relevant_documents select the search operation for similarity, similarity_score_threshold, and mmr, and what happens when a runtime search kwarg conflicts with a configured search_kwargs value?
- [lc-c-08](#lc-c-08): A RunnableWithFallbacks has a nonempty exception_key and dictionary input. Its primary runnable raises a handled error E1, its first fallback raises a handled error E2, and another fallback is about to run. Which error is put in the dictionary for that next fallback, which error is raised if all attempts fail with handled errors, and what happens to an unhandled exception?
- [lc-c-09](#lc-c-09): In synchronous BaseChatModel._generate_with_cache, do otherwise identical messages with different non-null message IDs produce different serialized prompt keys, and does a list-valued cache hit consume the model rate limiter before returning?
- [lc-c-10](#lc-c-10): For a fresh InMemoryRateLimiter with positive finite refill rate/polling interval and finite bucket capacity at least one, does it permit an immediate initial burst? Explain the first nonblocking acquire, later refill/capping, and blocking acquire, assuming no external state changes or competing requests.
- [lc-s-06](#lc-s-06): Which concrete core tool class supports multiple input arguments while keeping both synchronous and asynchronous callables? Locate its implementation and identify the input-schema, sync-callable, and async-callable fields.
- [lc-s-07](#lc-s-07): Which abstract runnable class is the core extension point for a custom document retriever? Locate its definition and identify the required synchronous retrieval hook and the corresponding default asynchronous hook.
- [lc-s-08](#lc-s-08): Which core runnable-composition class stores a pipeline as first, middle, and last steps? Locate the class, give the declared types of those fields, and name the property that reconstructs their ordered list.
- [lc-s-09](#lc-s-09): Inside BaseChatModel, which helper normalizes legacy cached Generation objects into chat-generation objects? Locate the implementation file and give the helper name, input annotation, and return annotation.
- [lc-s-10](#lc-s-10): Which in-memory core chat-history class owns the messages list, and which synchronous methods append a message and reset that list? Locate the class, identify its bases and stored field, and name the two methods.
- [lc-x-06](#lc-x-06): A successful synchronous tool built by create_retriever_tool has response_format='content_and_artifact' and document_separator=' | '. The retriever returns a document list docs whose formatted texts are 'alpha' and 'beta'. What is returned by the internal retrieval callable, and how does BaseTool.run expose the result when tool_call_id='call-1' versus when no tool_call_id is supplied? Trace the call path across the implementations.
- [lc-x-07](#lc-x-07): In this pinned revision, compare InMemoryVectorStore.add_texts called on an empty store with a fresh one-shot generator yielding 'alpha', 'beta' against a list ['alpha', 'beta'], with no metadata or IDs. Assume the embedding helper accepts an empty list and returns one vector per supplied text. What documents/IDs reach storage in each case, and how does the inherited add_texts implementation cause the difference?
- [lc-x-08](#lc-x-08): For RunnablePassthrough.assign(double=lambda d: 2*d['n'], prior=lambda d: d['double']).invoke({'n': 2, 'double': 99}), do the two mapping branches see one another's computed values or the original input? What dictionary results, and which cross-file execution/merge steps establish it?
- [lc-x-09](#lc-x-09): A synchronous BaseChatModel uses InMemoryCache(maxsize=2), fixed model settings, and three distinct normalized prompts A, B, and C. Starting empty, it successfully processes A, then B, then A again as a cache hit, then C. Which prompt entries remain cached, what part of the new ChatResult is stored, and why does accessing A not protect it from eviction?
- [lc-x-10](#lc-x-10): A synchronous RunnableWithMessageHistory uses InMemoryChatMessageHistory containing [H0, A0], has no separate history_messages_key, and receives current input messages [H1]. Its wrapped runnable successfully produces output messages [A1], with no intervening history mutation. Which messages are forwarded to the wrapped runnable, which are appended to the history afterward, and how do the wrapper and history implementation prevent the old messages from being duplicated?

## lc-c-06

**Question:** In BaseTool.run, how do handle_validation_error and handle_tool_error affect caught errors, and does handle_tool_error=True also suppress an ordinary ValueError raised by the tool implementation? Assume any configured handler returns normally.

Category: `conceptual` · Difficulty: `medium` · Split: `held_out`

**Proposed reference answer:** A caught Pydantic ValidationError/ValidationErrorV1 is re-raised when handle_validation_error is falsy; when it is truthy, its handler produces content and the tool status becomes "error". ToolException is treated analogously using handle_tool_error. An ordinary ValueError from the implementation is outside those special branches: it is caught by the BaseException branch, saved for re-raising, reported through run_manager.on_tool_error, and raised regardless of handle_tool_error=True. For the specially handled errors, execution instead formats the error content, reports on_tool_end, and returns the formatted output.

**Authoring notes:** Inspected the complete catch/finalization sequence in synchronous BaseTool.run at lines 1116-1136. Compared validation-error, ToolException, and generic BaseException branches, then followed error_to_raise into on_tool_error/raise versus output formatting/on_tool_end/return. Assumed handlers do not themselves fail as stated in the question. No tool was executed. Difficulty is medium because it requires exception-type discrimination and following two distinct finalization paths.

Annotation SHA-256: `227c17654f5bbac5fe54491c1979cf9194685a46e6eaab55adb63849723a139d`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: tools/base.py 1116-1136. Validation and ToolException branches depend on their flags; a plain ValueError falls to except BaseException (1128-1129), is reported via on_tool_error and raised (1131-1133).
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** tools/base.py 1116-1136. Validation and ToolException branches depend on their flags; a plain ValueError falls to except BaseException (1128-1129), is reported via on_tool_error and raised (1131-1133).

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/tools/base.py:1116–1136](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/tools/base.py:1116) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/tools/base.py#L1116-L1136)).

   Excerpt SHA-256: `6aa51219bbcb04798751b74b7fe2fc3680b96262b9e37179b1003aef6ba324d8`

`````text
 1116 |         except (ValidationError, ValidationErrorV1) as e:
 1117 |             if not self.handle_validation_error:
 1118 |                 error_to_raise = e
 1119 |             else:
 1120 |                 content = _handle_validation_error(e, flag=self.handle_validation_error)
 1121 |                 status = "error"
 1122 |         except ToolException as e:
 1123 |             if not self.handle_tool_error:
 1124 |                 error_to_raise = e
 1125 |             else:
 1126 |                 content = _handle_tool_error(e, flag=self.handle_tool_error)
 1127 |                 status = "error"
 1128 |         except BaseException as e:
 1129 |             error_to_raise = e
 1130 |
 1131 |         if error_to_raise:
 1132 |             run_manager.on_tool_error(error_to_raise, tool_call_id=tool_call_id)
 1133 |             raise error_to_raise
 1134 |         output = _format_output(content, artifact, tool_call_id, self.name, status)
 1135 |         run_manager.on_tool_end(output, color=color, name=self.name, **kwargs)
 1136 |         return output
`````

## lc-c-07

**Question:** How does synchronous VectorStoreRetriever._get_relevant_documents select the search operation for similarity, similarity_score_threshold, and mmr, and what happens when a runtime search kwarg conflicts with a configured search_kwargs value?

Category: `conceptual` · Difficulty: `medium` · Split: `held_out`

**Proposed reference answer:** The method first merges self.search_kwargs | kwargs, so a runtime kwarg wins on a conflicting key. The "similarity" path calls vectorstore.similarity_search; "similarity_score_threshold" calls similarity_search_with_relevance_scores and strips the scores from the returned (document, score) pairs; and "mmr" calls max_marginal_relevance_search. Each receives the query and merged kwargs, and the retriever returns documents rather than scored pairs. An unsupported search_type reaching this method raises ValueError.

**Authoring notes:** Inspected synchronous VectorStoreRetriever._get_relevant_documents at lines 1041-1059. Followed the right-biased dictionary union into all three backend calls and checked the comprehension dropping relevance scores before the final return; also checked the unsupported-type error branch. No vector store or retrieval execution was used. Difficulty is medium because correct behavior requires dispatch, parameter precedence, and output-shape reasoning together.

Annotation SHA-256: `c918a917c7aa87c2559a0f4292e8da242a2cf959927a01e51f7377d50356d691`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: vectorstores/base.py 1044-1059. kwargs_ = self.search_kwargs | kwargs, so runtime kwargs win; one backend call per search type, with scores dropped at 1053.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** vectorstores/base.py 1044-1059. kwargs_ = self.search_kwargs | kwargs, so runtime kwargs win; one backend call per search type, with scores dropped at 1053.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/vectorstores/base.py:1041–1059](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/vectorstores/base.py:1041) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/vectorstores/base.py#L1041-L1059)).

   Excerpt SHA-256: `f4228b47a26d92c05609fc14cc55fd0f54bd499795b6ee50a2809d828a431eac`

`````text
 1041 |     def _get_relevant_documents(
 1042 |         self, query: str, *, run_manager: CallbackManagerForRetrieverRun, **kwargs: Any
 1043 |     ) -> list[Document]:
 1044 |         kwargs_ = self.search_kwargs | kwargs
 1045 |         if self.search_type == "similarity":
 1046 |             docs = self.vectorstore.similarity_search(query, **kwargs_)
 1047 |         elif self.search_type == "similarity_score_threshold":
 1048 |             docs_and_similarities = (
 1049 |                 self.vectorstore.similarity_search_with_relevance_scores(
 1050 |                     query, **kwargs_
 1051 |                 )
 1052 |             )
 1053 |             docs = [doc for doc, _ in docs_and_similarities]
 1054 |         elif self.search_type == "mmr":
 1055 |             docs = self.vectorstore.max_marginal_relevance_search(query, **kwargs_)
 1056 |         else:
 1057 |             msg = f"search_type of {self.search_type} not allowed."
 1058 |             raise ValueError(msg)
 1059 |         return docs
`````

## lc-c-08

**Question:** A RunnableWithFallbacks has a nonempty exception_key and dictionary input. Its primary runnable raises a handled error E1, its first fallback raises a handled error E2, and another fallback is about to run. Which error is put in the dictionary for that next fallback, which error is raised if all attempts fail with handled errors, and what happens to an unhandled exception?

Category: `conceptual` · Difficulty: `hard` · Split: `held_out`

**Proposed reference answer:** The next fallback receives the most recent handled error E2 under exception_key, because last_error is written into the input dictionary before each subsequent attempt. The first handled error E1 is kept separately as first_error and is the one reported and raised if every attempt fails with handled errors. An exception outside exceptions_to_handle is reported immediately and re-raised without proceeding to later fallbacks. The input is mutated in place when the exception key is set; it is not rebuilt as a separate dictionary for each fallback.

**Authoring notes:** Inspected RunnableWithFallbacks.invoke at lines 184-212. Manually traced E1 then E2 through first_error/last_error, the in-place input assignment before the next attempt, the handled versus BaseException catch clauses, and the terminal raise of first_error. The question already supplies a valid dictionary and nonempty key; setup validation is outside its scope. No runnable was executed. Difficulty is hard because the answer distinguishes state propagated to later attempts from the different exception ultimately re-raised and must account for early exit on unhandled errors.

Annotation SHA-256: `f8a33b0ac7e3e42177f652f50ab2d48849a33c0f7f0d80529185f5e9f7c88103`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: runnables/fallbacks.py 184-212. last_error is written into the input dict before each later attempt (188-189); first_error is raised at the end (211-212); unhandled exceptions are re-raised at once (202-204).
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** runnables/fallbacks.py 184-212. last_error is written into the input dict before each later attempt (188-189); first_error is raised at the end (211-212); unhandled exceptions are re-raised at once (202-204).

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/runnables/fallbacks.py:184–212](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/fallbacks.py:184) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/fallbacks.py#L184-L212)).

   Excerpt SHA-256: `c9a8cde3276537912ea27215b6f8b53c24cb05fca780ffc68efb30e5012d8826`

`````text
  184 |         first_error = None
  185 |         last_error = None
  186 |         for runnable in self.runnables:
  187 |             try:
  188 |                 if self.exception_key and last_error is not None:
  189 |                     input[self.exception_key] = last_error  # type: ignore[index]
  190 |                 child_config = patch_config(config, callbacks=run_manager.get_child())
  191 |                 with set_config_context(child_config) as context:
  192 |                     output = context.run(
  193 |                         runnable.invoke,
  194 |                         input,
  195 |                         config,
  196 |                         **kwargs,
  197 |                     )
  198 |             except self.exceptions_to_handle as e:
  199 |                 if first_error is None:
  200 |                     first_error = e
  201 |                 last_error = e
  202 |             except BaseException as e:
  203 |                 run_manager.on_chain_error(e)
  204 |                 raise
  205 |             else:
  206 |                 run_manager.on_chain_end(output)
  207 |                 return output
  208 |         if first_error is None:
  209 |             msg = "No error stored at end of fallbacks."
  210 |             raise ValueError(msg)
  211 |         run_manager.on_chain_error(first_error)
  212 |         raise first_error
`````

## lc-c-09

**Question:** In synchronous BaseChatModel._generate_with_cache, do otherwise identical messages with different non-null message IDs produce different serialized prompt keys, and does a list-valued cache hit consume the model rate limiter before returning?

Category: `conceptual` · Difficulty: `medium` · Split: `held_out`

**Proposed reference answer:** Non-null message IDs are replaced with None in copied messages before the normalized message list is serialized for the prompt portion of the cache key. Thus a difference only in those IDs is removed from that serialized prompt; the model-configuration/stop-parameter llm_string remains the other lookup argument. A list-valued cache hit is converted/replayed and returned before control reaches rate_limiter.acquire(blocking=True), so that hit does not consume the limiter here. Original messages are not changed by the ID-normalization copies.

**Authoring notes:** Inspected cache setup, normalized_messages model_copy(update={"id": None}), dumps, and lookup at lines 1942-1959, then followed the list-hit return at lines 1960-1967 relative to the later rate-limiter acquisition at lines 1974-1978. Only the prompt-key component and this synchronous cache-hit path are claimed; no provider model, cache execution, or clock manipulation was used. Difficulty is medium because it combines normalization/aliasing behavior with an early-return side effect.

Annotation SHA-256: `4cf340ec5426b4211db960b161ff58066387e36d657979e629c803fe88e0e1e2`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: language_models/chat_models.py 1950-1967 and 1977-1978. Non-null IDs are nulled on copies before dumps; a list-valued hit returns before rate_limiter.acquire.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** language_models/chat_models.py 1950-1967 and 1977-1978. Non-null IDs are nulled on copies before dumps; a list-valued hit returns before rate_limiter.acquire.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/language_models/chat_models.py:1942–1978](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/language_models/chat_models.py:1942) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/language_models/chat_models.py#L1942-L1978)).

   Excerpt SHA-256: `9fe07a645e9d51165f4c1a9a483e2b3ad3a94048ed22c6d0c93ff1f7f5275c49`

`````text
 1942 |         llm_cache = self.cache if isinstance(self.cache, BaseCache) else get_llm_cache()
 1943 |         # We should check the cache unless it's explicitly set to False
 1944 |         # A None cache means we should use the default global cache
 1945 |         # if it's configured.
 1946 |         check_cache = self.cache is not False
 1947 |         if check_cache:
 1948 |             if llm_cache is not None:
 1949 |                 llm_string = self._get_llm_string(stop=stop, **kwargs)
 1950 |                 normalized_messages = [
 1951 |                     (
 1952 |                         msg.model_copy(update={"id": None})
 1953 |                         if getattr(msg, "id", None) is not None
 1954 |                         else msg
 1955 |                     )
 1956 |                     for msg in messages
 1957 |                 ]
 1958 |                 prompt = dumps(normalized_messages)
 1959 |                 cache_val = llm_cache.lookup(prompt, llm_string)
 1960 |                 if isinstance(cache_val, list):
 1961 |                     converted_generations = self._convert_cached_generations(cache_val)
 1962 |                     self._replay_v2_events_for_cache_hit(
 1963 |                         converted_generations,
 1964 |                         run_manager=run_manager,
 1965 |                         **kwargs,
 1966 |                     )
 1967 |                     return ChatResult(generations=converted_generations)
 1968 |             elif self.cache is None:
 1969 |                 pass
 1970 |             else:
 1971 |                 msg = "Asked to cache, but no cache found at `langchain.cache`."
 1972 |                 raise ValueError(msg)
 1973 |
 1974 |         # Apply the rate limiter after checking the cache, since
 1975 |         # we usually don't want to rate limit cache lookups, but
 1976 |         # we do want to rate limit API requests.
 1977 |         if self.rate_limiter:
 1978 |             self.rate_limiter.acquire(blocking=True)
`````

## lc-c-10

**Question:** For a fresh InMemoryRateLimiter with positive finite refill rate/polling interval and finite bucket capacity at least one, does it permit an immediate initial burst? Explain the first nonblocking acquire, later refill/capping, and blocking acquire, assuming no external state changes or competing requests.

Category: `conceptual` · Difficulty: `hard` · Split: `held_out`

**Proposed reference answer:** No initial full bucket is granted: available_tokens starts at 0.0 and last starts as None. On the first _consume call, last is set to the current monotonic time, giving zero elapsed time and no token, so acquire(blocking=False) returns False. Later calls add elapsed * requests_per_second only once that accrued amount reaches at least one token, update last, cap available_tokens at max_bucket_size, and consume exactly one token when at least one is available. Consumption/refill is guarded by a lock. A nonblocking acquire makes one consume attempt; a blocking acquire retries _consume and sleeps check_every_n_seconds between failures before returning True.

**Authoring notes:** Inspected initial bucket/time/lock state at lines 146-161 and all _consume branches at lines 163-193; manually traced the first call where now equals newly assigned last, subsequent accumulation, bucket-size cap, and one-token deduction. Compared blocking and nonblocking acquire at lines 212-218. This was direct source inspection with no real waiting or code execution. Difficulty is hard because it requires reasoning about initialization, elapsed-time accounting, bucket capping, synchronization, and polling rather than assuming a conventional initially full token bucket. The question explicitly restricts refill/polling/capacity parameters to a valid finite configuration and excludes competing requests or external state mutation, so the blocking-return description does not assume behavior for pathological constructor inputs.

Annotation SHA-256: `9b5993d38db0410e1e9fb191413d785d69d8411329fdbf19776876b9c22c5799`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: rate_limiters.py 146-193 and 212-218. available_tokens starts at 0.0 and last at None, so the first non-blocking acquire returns False; refill, cap and blocking loop are as stated.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** rate_limiters.py 146-193 and 212-218. available_tokens starts at 0.0 and last at None, so the first non-blocking acquire returns False; refill, cap and blocking loop are as stated.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/rate_limiters.py:146–193](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/rate_limiters.py:146) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/rate_limiters.py#L146-L193)).

   Excerpt SHA-256: `2c2ddd2dcb4bf0b884b1dcd16d32db9b6d41713d76cb8918895d7ea703be26fd`

`````text
  146 |         # Number of requests that we can make per second.
  147 |         self.requests_per_second = requests_per_second
  148 |
  149 |         # Number of tokens in the bucket.
  150 |         self.available_tokens = 0.0
  151 |
  152 |         self.max_bucket_size = max_bucket_size
  153 |
  154 |         # A lock to ensure that tokens can only be consumed by one thread
  155 |         # at a given time.
  156 |         self._consume_lock = threading.Lock()
  157 |
  158 |         # The last time we tried to consume tokens.
  159 |         self.last: float | None = None
  160 |
  161 |         self.check_every_n_seconds = check_every_n_seconds
  162 |
  163 |     def _consume(self) -> bool:
  164 |         """Try to consume a token.
  165 |
  166 |         Returns:
  167 |             True means that the tokens were consumed, and the caller can proceed to
  168 |             make the request. A False means that the tokens were not consumed, and
  169 |             the caller should try again later.
  170 |         """
  171 |         with self._consume_lock:
  172 |             now = time.monotonic()
  173 |
  174 |             # initialize on first call to avoid a burst
  175 |             if self.last is None:
  176 |                 self.last = now
  177 |
  178 |             elapsed = now - self.last
  179 |
  180 |             if elapsed * self.requests_per_second >= 1:
  181 |                 self.available_tokens += elapsed * self.requests_per_second
  182 |                 self.last = now
  183 |
  184 |             # Make sure that we don't exceed the bucket size.
  185 |             # This is used to prevent bursts of requests.
  186 |             self.available_tokens = min(self.available_tokens, self.max_bucket_size)
  187 |
  188 |             # As long as we have at least one token, we can proceed.
  189 |             if self.available_tokens >= 1:
  190 |                 self.available_tokens -= 1
  191 |                 return True
  192 |
  193 |             return False
`````

2. [libs/core/langchain_core/rate_limiters.py:212–218](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/rate_limiters.py:212) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/rate_limiters.py#L212-L218)).

   Excerpt SHA-256: `96e6c55c0948367e83b5851768494f94c19577e2e26fa13780f33d06fa4194c4`

`````text
  212 |         if not blocking:
  213 |             return self._consume()
  214 |
  215 |         while not self._consume():
  216 |             time.sleep(self.check_every_n_seconds)
  217 |
  218 |         return True
`````

## lc-s-06

**Question:** Which concrete core tool class supports multiple input arguments while keeping both synchronous and asynchronous callables? Locate its implementation and identify the input-schema, sync-callable, and async-callable fields.

Category: `structural` · Difficulty: `easy` · Split: `held_out`

**Proposed reference answer:** StructuredTool in libs/core/langchain_core/tools/structured.py subclasses BaseTool and is documented as operating on any number of inputs. Its input-schema field is args_schema; its synchronous callable field is func; and its asynchronous callable field is coroutine. Both callable fields default to None.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: easy: the class header and contiguous schema/callable declarations establish the API structure without requiring tool execution. Verified field names, Callable/Awaitable annotations, and None defaults. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `157fdf740b4b85420466a7e4ad48dfac491a876f2ee75c7d2586738592453a4f`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: tools/structured.py 93-109. StructuredTool(BaseTool) with args_schema, func and coroutine; both callables default to None.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** tools/structured.py 93-109. StructuredTool(BaseTool) with args_schema, func and coroutine; both callables default to None.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/tools/structured.py:93–112](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/tools/structured.py:93) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/tools/structured.py#L93-L112)).

   Excerpt SHA-256: `79d1336c914285a4684b4b7f3856704fa437b60199857e455ae5a9e00aa61cd0`

`````text
   93 | class StructuredTool(BaseTool):
   94 |     """Tool that can operate on any number of inputs."""
   95 |
   96 |     description: str = ""
   97 |
   98 |     args_schema: Annotated[ArgsSchema, SkipValidation(), _JsonSchemaFallback] = Field(
   99 |         ..., description="The tool schema."
  100 |     )
  101 |     """The input arguments' schema."""
  102 |
  103 |     func: Annotated[Callable[..., Any] | None, _JsonCallableFallback] = None
  104 |     """The function to run when the tool is called."""
  105 |
  106 |     coroutine: Annotated[
  107 |         Callable[..., Awaitable[Any]] | None, _JsonCallableFallback
  108 |     ] = None
  109 |     """The asynchronous version of the function."""
  110 |
  111 |     # --- Runnable ---
  112 |
`````

## lc-s-07

**Question:** Which abstract runnable class is the core extension point for a custom document retriever? Locate its definition and identify the required synchronous retrieval hook and the corresponding default asynchronous hook.

Category: `structural` · Difficulty: `medium` · Split: `held_out`

**Proposed reference answer:** BaseRetriever in libs/core/langchain_core/retrievers.py is the extension point; it inherits RunnableSerializable[RetrieverInput, RetrieverOutput] and ABC. The required synchronous hook is @abstractmethod _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]. The corresponding default async hook is _aget_relevant_documents(self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun) -> list[Document], which already has an implementation.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: medium: the class definition and two distant hook declarations must be associated. Verified the synchronous abstractmethod decorator, absence of that decorator on the async hook, callback-manager types, and complete default async body. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `8b3adc2d43336405f6579c8e0515b651048c360f22b2b69424115be6acbcbeb6`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: retrievers.py 55, 297-300 and 311-313. BaseRetriever with abstract _get_relevant_documents and a concrete _aget_relevant_documents.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** retrievers.py 55, 297-300 and 311-313. BaseRetriever with abstract _get_relevant_documents and a concrete _aget_relevant_documents.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/retrievers.py:55–69](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/retrievers.py:55) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/retrievers.py#L55-L69)).

   Excerpt SHA-256: `e9e5c70a5050e2350988f9ed115dbcc4d9055b25dd7c738b816a0ab0cbd34e2e`

`````text
   55 | class BaseRetriever(RunnableSerializable[RetrieverInput, RetrieverOutput], ABC):
   56 |     """Abstract base class for a document retrieval system.
   57 |
   58 |     A retrieval system is defined as something that can take string queries and return
   59 |     the most 'relevant' documents from some source.
   60 |
   61 |     Usage:
   62 |
   63 |     A retriever follows the standard `Runnable` interface, and should be used via the
   64 |     standard `Runnable` methods of `invoke`, `ainvoke`, `batch`, `abatch`.
   65 |
   66 |     Implementation:
   67 |
   68 |     When implementing a custom retriever, the class should implement the
   69 |     `_get_relevant_documents` method to define the logic for retrieving documents.
`````

2. [libs/core/langchain_core/retrievers.py:297–328](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/retrievers.py:297) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/retrievers.py#L297-L328)).

   Excerpt SHA-256: `69b40f3865bbcf4557e80cce63c7341357435159b26d1c12e85de56c7ef4b207`

`````text
  297 |     @abstractmethod
  298 |     def _get_relevant_documents(
  299 |         self, query: str, *, run_manager: CallbackManagerForRetrieverRun
  300 |     ) -> list[Document]:
  301 |         """Get documents relevant to a query.
  302 |
  303 |         Args:
  304 |             query: String to find relevant documents for.
  305 |             run_manager: The callback handler to use.
  306 |
  307 |         Returns:
  308 |             List of relevant documents.
  309 |         """
  310 |
  311 |     async def _aget_relevant_documents(
  312 |         self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
  313 |     ) -> list[Document]:
  314 |         """Asynchronously get documents relevant to a query.
  315 |
  316 |         Args:
  317 |             query: String to find relevant documents for
  318 |             run_manager: The callback handler to use
  319 |
  320 |         Returns:
  321 |             List of relevant documents
  322 |         """
  323 |         return await run_in_executor(
  324 |             None,
  325 |             self._get_relevant_documents,
  326 |             query,
  327 |             run_manager=run_manager.get_sync(),
  328 |         )
`````

## lc-s-08

**Question:** Which core runnable-composition class stores a pipeline as first, middle, and last steps? Locate the class, give the declared types of those fields, and name the property that reconstructs their ordered list.

Category: `structural` · Difficulty: `medium` · Split: `held_out`

**Proposed reference answer:** RunnableSequence in libs/core/langchain_core/runnables/base.py stores first: Runnable[Input, Any], middle: list[Runnable[Any, Any]] with a default empty list, and last: Runnable[Any, Output]. Its steps property returns [self.first, *self.middle, self.last] in order.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: medium: the type-specific step fields and later steps property require combining separate declarations within one class. Checked the generic field annotations, default_factory=list, and complete ordered-list return expression. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `e4e6e723af5ba0ca7c8d12d85941021c3a15f3a1103cd0955f39edabf616b7aa`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: runnables/base.py 3094, 3181-3185 and 3239-3246. RunnableSequence fields first, middle, last and the steps property.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** runnables/base.py 3094, 3181-3185 and 3239-3246. RunnableSequence fields first, middle, last and the steps property.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/runnables/base.py:3094–3098](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/base.py:3094) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/base.py#L3094-L3098)).

   Excerpt SHA-256: `72d1426b53d4654509dc2b12453e1f68972e592c4c8ab9f74e055e36da602b13`

`````text
 3094 | class RunnableSequence(RunnableSerializable[Input, Output]):
 3095 |     """Sequence of `Runnable` objects, where the output of one is the input of the next.
 3096 |
 3097 |     **`RunnableSequence`** is the most important composition operator in LangChain
 3098 |     as it is used in virtually every chain.
`````

2. [libs/core/langchain_core/runnables/base.py:3178–3186](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/base.py:3178) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/base.py#L3178-L3186)).

   Excerpt SHA-256: `d2aa46c50e3fc00095b10a9cf9deecabc7dd4959c81d0c6dd7d6a52895139640`

`````text
 3178 |     # The steps are broken into first, middle and last, solely for type checking
 3179 |     # purposes. It allows specifying the `Input` on the first type, the `Output` of
 3180 |     # the last type.
 3181 |     first: Runnable[Input, Any]
 3182 |     """The first `Runnable` in the sequence."""
 3183 |     middle: list[Runnable[Any, Any]] = Field(default_factory=list)
 3184 |     """The middle `Runnable` in the sequence."""
 3185 |     last: Runnable[Any, Output]
 3186 |     """The last `Runnable` in the sequence."""
`````

3. [libs/core/langchain_core/runnables/base.py:3239–3246](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/base.py:3239) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/base.py#L3239-L3246)).

   Excerpt SHA-256: `ecb2afe592304e3c4f8efa01688df26b74ac392db11753ff92940d62830fe922`

`````text
 3239 |     @property
 3240 |     def steps(self) -> list[Runnable[Any, Any]]:
 3241 |         """All the `Runnable`s that make up the sequence in order.
 3242 |
 3243 |         Returns:
 3244 |             A list of `Runnable`s.
 3245 |         """
 3246 |         return [self.first, *self.middle, self.last]
`````

## lc-s-09

**Question:** Inside BaseChatModel, which helper normalizes legacy cached Generation objects into chat-generation objects? Locate the implementation file and give the helper name, input annotation, and return annotation.

Category: `structural` · Difficulty: `medium` · Split: `held_out`

**Proposed reference answer:** The helper is BaseChatModel._convert_cached_generations in libs/core/langchain_core/language_models/chat_models.py. Its signature is _convert_cached_generations(self, cache_val: list[Generation]) -> list[ChatGeneration]. It is documented as converting cached Generation objects to ChatGeneration objects, including legacy or serialization-related cache data.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: medium: the helper is nested in a large chat-model module and must be distinguished from cache lookup/generation methods. Verified its containing BaseChatModel class, exact signature, conversion documentation, and complete method body. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `52b21a28f10535a6bf5b0b5cd3e0c21885dca3b0642600544ddaa9390c570177`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: language_models/chat_models.py 1448-1450, inside BaseChatModel. Signature and docstring as stated.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** language_models/chat_models.py 1448-1450, inside BaseChatModel. Signature and docstring as stated.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/language_models/chat_models.py:1448–1487](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/language_models/chat_models.py:1448) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/language_models/chat_models.py#L1448-L1487)).

   Excerpt SHA-256: `89931cabea00cada1ef0159f991f012cd135bac2498aa80fdc22e286a57c395f`

`````text
 1448 |     def _convert_cached_generations(
 1449 |         self, cache_val: list[Generation]
 1450 |     ) -> list[ChatGeneration]:
 1451 |         """Convert cached Generation objects to ChatGeneration objects.
 1452 |
 1453 |         Handle case where cache contains Generation objects instead of
 1454 |         ChatGeneration objects. This can happen due to serialization/deserialization
 1455 |         issues or legacy cache data (see #22389).
 1456 |
 1457 |         Args:
 1458 |             cache_val: List of cached generation objects.
 1459 |
 1460 |         Returns:
 1461 |             List of ChatGeneration objects.
 1462 |
 1463 |         """
 1464 |         converted_generations = []
 1465 |         for gen in cache_val:
 1466 |             if isinstance(gen, Generation) and not isinstance(gen, ChatGeneration):
 1467 |                 # Convert Generation to ChatGeneration by creating AIMessage
 1468 |                 # from the text content
 1469 |                 chat_gen = ChatGeneration(
 1470 |                     message=AIMessage(content=gen.text),
 1471 |                     generation_info=gen.generation_info,
 1472 |                 )
 1473 |                 converted_generations.append(chat_gen)
 1474 |             else:
 1475 |                 # Already a ChatGeneration or other expected type
 1476 |                 if hasattr(gen, "message") and isinstance(gen.message, AIMessage):
 1477 |                     # We zero out cost on cache hits
 1478 |                     gen.message = gen.message.model_copy(
 1479 |                         update={
 1480 |                             "usage_metadata": {
 1481 |                                 **(gen.message.usage_metadata or {}),
 1482 |                                 "total_cost": 0,
 1483 |                             }
 1484 |                         }
 1485 |                     )
 1486 |                 converted_generations.append(gen)
 1487 |         return converted_generations
`````

## lc-s-10

**Question:** Which in-memory core chat-history class owns the messages list, and which synchronous methods append a message and reset that list? Locate the class, identify its bases and stored field, and name the two methods.

Category: `structural` · Difficulty: `easy` · Split: `held_out`

**Proposed reference answer:** InMemoryChatMessageHistory in libs/core/langchain_core/chat_history.py inherits BaseChatMessageHistory and BaseModel. Its stored field is messages: list[BaseMessage] = Field(default_factory=list). add_message(self, message: BaseMessage) appends to self.messages; clear(self) resets self.messages to a new empty list.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: easy: one concrete class and two small sync methods establish storage ownership and mutation entry points. Verified the bases, list factory, append statement, and empty-list assignment without assuming any external persistence. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `2186fb63c99b07de59dc4fa56384fad08e4a62fcc8dcae8fa9aa5aaecda631e1`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: chat_history.py 223, 229, 245-251 and 261-263. InMemoryChatMessageHistory(BaseChatMessageHistory, BaseModel); add_message appends, clear assigns a new list.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** chat_history.py 223, 229, 245-251 and 261-263. InMemoryChatMessageHistory(BaseChatMessageHistory, BaseModel); add_message appends, clear assigns a new list.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/chat_history.py:223–230](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/chat_history.py:223) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/chat_history.py#L223-L230)).

   Excerpt SHA-256: `ca5243acc5a783b3f7fc6e87ff253e2ae4951bd2d6c226dc30cc8968dc9cb599`

`````text
  223 | class InMemoryChatMessageHistory(BaseChatMessageHistory, BaseModel):
  224 |     """In memory implementation of chat message history.
  225 |
  226 |     Stores messages in a memory list.
  227 |     """
  228 |
  229 |     messages: list[BaseMessage] = Field(default_factory=list)
  230 |     """A list of messages stored in memory."""
`````

2. [libs/core/langchain_core/chat_history.py:245–251](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/chat_history.py:245) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/chat_history.py#L245-L251)).

   Excerpt SHA-256: `58d206420ce98bbef04520989f5974eed30da7f91f19da67074cdc43d51ebfc9`

`````text
  245 |     def add_message(self, message: BaseMessage) -> None:
  246 |         """Add a self-created message to the store.
  247 |
  248 |         Args:
  249 |             message: The message to add.
  250 |         """
  251 |         self.messages.append(message)
`````

3. [libs/core/langchain_core/chat_history.py:261–263](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/chat_history.py:261) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/chat_history.py#L261-L263)).

   Excerpt SHA-256: `22166555c7c1f961033cf2054399f66e225beca2bfe7e35c120df1fa95ab0cc9`

`````text
  261 |     def clear(self) -> None:
  262 |         """Clear all messages from the store."""
  263 |         self.messages = []
`````

## lc-x-06

**Question:** A successful synchronous tool built by create_retriever_tool has response_format='content_and_artifact' and document_separator=' | '. The retriever returns a document list docs whose formatted texts are 'alpha' and 'beta'. What is returned by the internal retrieval callable, and how does BaseTool.run expose the result when tool_call_id='call-1' versus when no tool_call_id is supplied? Trace the call path across the implementations.

Category: `cross_file` · Difficulty: `hard` · Split: `held_out`

**Proposed reference answer:** The retrieval callable invokes the retriever, joins the formatted documents into 'alpha | beta', and returns ('alpha | beta', docs), retaining the original document list as the artifact. The created StructuredTool is configured with response_format='content_and_artifact'. BaseTool.run unpacks that tuple into content and artifact and passes both to _format_output. With tool_call_id='call-1', the string content is wrapped in a ToolMessage carrying that call ID, the tool's name, status='success', and artifact=docs. With tool_call_id=None, _format_output returns only the content string 'alpha | beta'; it does not return the two-tuple or a ToolMessage/artifact wrapper in that case.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Hard: follows retriever-tool construction, its two-part response, BaseTool tuple handling, and final call-ID-dependent packaging. Verify the supplied formatting premise, content_and_artifact branches and constructor setting, then the successful BaseTool.run path and _format_output's tool_call_id=None early return. This does not test the conceptual tool-error handling policy. Evidence completeness refinement: the BaseTool.run range begins at initialization of content, artifact, and status, directly supporting the success status claimed in the answer. Final source audit: Included the concrete StructuredTool._run bridge that invokes the stored retrieval callable.

Annotation SHA-256: `f8463e6dd7be4b25d75c87d6d14103dfe5e830beffc0c0e07f44ea9d6114f379`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: tools/retriever.py 63-94, tools/base.py 1085-1115, 1131-1136 and 1391-1427, tools/structured.py 147-154. The callable returns ('alpha | beta', docs); run unpacks it (1111); _format_output returns the bare string when tool_call_id is None (1417) and a ToolMessage with artifact otherwise (1421-1427).
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** tools/retriever.py 63-94, tools/base.py 1085-1115, 1131-1136 and 1391-1427, tools/structured.py 147-154. The callable returns ('alpha | beta', docs); run unpacks it (1111); _format_output returns the bare string when tool_call_id is None (1417) and a ToolMessage with artifact otherwise (1421-1427).

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/tools/retriever.py:63–94](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/tools/retriever.py:63) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/tools/retriever.py#L63-L94)).

   Excerpt SHA-256: `1252dae6490e2c7c7ae545f4e3d22feda511f36b39d89d06d5203d1d2245c4cd`

`````text
   63 |     document_prompt_ = document_prompt or PromptTemplate.from_template("{page_content}")
   64 |
   65 |     def func(
   66 |         query: str, callbacks: Callbacks = None
   67 |     ) -> str | tuple[str, list[Document]]:
   68 |         docs = retriever.invoke(query, config={"callbacks": callbacks})
   69 |         content = document_separator.join(
   70 |             format_document(doc, document_prompt_) for doc in docs
   71 |         )
   72 |         if response_format == "content_and_artifact":
   73 |             return (content, docs)
   74 |         return content
   75 |
   76 |     async def afunc(
   77 |         query: str, callbacks: Callbacks = None
   78 |     ) -> str | tuple[str, list[Document]]:
   79 |         docs = await retriever.ainvoke(query, config={"callbacks": callbacks})
   80 |         content = document_separator.join(
   81 |             [await aformat_document(doc, document_prompt_) for doc in docs]
   82 |         )
   83 |         if response_format == "content_and_artifact":
   84 |             return (content, docs)
   85 |         return content
   86 |
   87 |     return StructuredTool(
   88 |         name=name,
   89 |         description=description,
   90 |         func=func,
   91 |         coroutine=afunc,
   92 |         args_schema=RetrieverInput,
   93 |         response_format=response_format,
   94 |     )
`````

2. [libs/core/langchain_core/tools/base.py:1085–1115](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/tools/base.py:1085) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/tools/base.py#L1085-L1115)).

   Excerpt SHA-256: `5da75d8fae37a81fa0331ba4abdff30467913d74e51f8a93ff39bd6662c7af58`

`````text
 1085 |         content = None
 1086 |         artifact = None
 1087 |         status = "success"
 1088 |         error_to_raise: BaseException | None = None
 1089 |         try:
 1090 |             child_config = patch_config(config, callbacks=run_manager.get_child())
 1091 |             with set_config_context(child_config) as context:
 1092 |                 tool_args, tool_kwargs = self._to_args_and_kwargs(
 1093 |                     tool_input, tool_call_id
 1094 |                 )
 1095 |                 if _signature_parameters(self._run).get("run_manager"):
 1096 |                     tool_kwargs |= {"run_manager": run_manager}
 1097 |                 if config_param := _get_runnable_config_param(self._run):
 1098 |                     tool_kwargs |= {config_param: config}
 1099 |                 response = context.run(self._run, *tool_args, **tool_kwargs)
 1100 |             if self.response_format == "content_and_artifact":
 1101 |                 msg = (
 1102 |                     "Since response_format='content_and_artifact' "
 1103 |                     "a two-tuple of the message content and raw tool output is "
 1104 |                     f"expected. Instead, generated response is of type: "
 1105 |                     f"{type(response)}."
 1106 |                 )
 1107 |                 if not isinstance(response, tuple):
 1108 |                     error_to_raise = ValueError(msg)
 1109 |                 else:
 1110 |                     try:
 1111 |                         content, artifact = response
 1112 |                     except ValueError:
 1113 |                         error_to_raise = ValueError(msg)
 1114 |             else:
 1115 |                 content = response
`````

3. [libs/core/langchain_core/tools/base.py:1131–1136](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/tools/base.py:1131) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/tools/base.py#L1131-L1136)).

   Excerpt SHA-256: `1878c7a98dfdb2e5a4c7335b96370d28af29192fc53511e68583922f531302c2`

`````text
 1131 |         if error_to_raise:
 1132 |             run_manager.on_tool_error(error_to_raise, tool_call_id=tool_call_id)
 1133 |             raise error_to_raise
 1134 |         output = _format_output(content, artifact, tool_call_id, self.name, status)
 1135 |         run_manager.on_tool_end(output, color=color, name=self.name, **kwargs)
 1136 |         return output
`````

4. [libs/core/langchain_core/tools/base.py:1391–1427](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/tools/base.py:1391) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/tools/base.py#L1391-L1427)).

   Excerpt SHA-256: `5c191f3909343063b0350d48fe4dfefe883a33128ecef46354203a79d824c941`

`````text
 1391 | def _format_output(
 1392 |     content: Any,
 1393 |     artifact: Any,
 1394 |     tool_call_id: str | None,
 1395 |     name: str,
 1396 |     status: str,
 1397 | ) -> ToolOutputMixin | Any:
 1398 |     """Format tool output as a `ToolMessage` if appropriate.
 1399 |
 1400 |     Args:
 1401 |         content: The main content of the tool output.
 1402 |         artifact: Any artifact data from the tool.
 1403 |         tool_call_id: The ID of the tool call.
 1404 |         name: The name of the tool.
 1405 |         status: The execution status.
 1406 |
 1407 |     Returns:
 1408 |         The formatted output, either as a `ToolMessage`, the original content,
 1409 |         or an unchanged list of `ToolOutputMixin` instances.
 1410 |     """
 1411 |     if (
 1412 |         isinstance(content, list)
 1413 |         and content
 1414 |         and all(isinstance(item, ToolOutputMixin) for item in content)
 1415 |     ):
 1416 |         return content
 1417 |     if isinstance(content, ToolOutputMixin) or tool_call_id is None:
 1418 |         return content
 1419 |     normalized_content = _normalize_message_content(content)
 1420 |     content = _stringify(content) if normalized_content is None else normalized_content
 1421 |     return ToolMessage(
 1422 |         content,
 1423 |         artifact=artifact,
 1424 |         tool_call_id=tool_call_id,
 1425 |         name=name,
 1426 |         status=status,
 1427 |     )
`````

5. [libs/core/langchain_core/tools/structured.py:147–154](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/tools/structured.py:147) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/tools/structured.py#L147-L154)).

   Excerpt SHA-256: `0811300d4fd33d38489fba686c8318582dab3a4ce27f021a0c43430c6407b1dd`

`````text
  147 |         if self.func:
  148 |             if run_manager and _signature_parameters(self.func).get("callbacks"):
  149 |                 kwargs["callbacks"] = run_manager.get_child()
  150 |             if config_param := _get_runnable_config_param(self.func):
  151 |                 kwargs[config_param] = config
  152 |             return self.func(*args, **kwargs)
  153 |         msg = "StructuredTool does not support sync invocation."
  154 |         raise NotImplementedError(msg)
`````

## lc-x-07

**Question:** In this pinned revision, compare InMemoryVectorStore.add_texts called on an empty store with a fresh one-shot generator yielding 'alpha', 'beta' against a list ['alpha', 'beta'], with no metadata or IDs. Assume the embedding helper accepts an empty list and returns one vector per supplied text. What documents/IDs reach storage in each case, and how does the inherited add_texts implementation cause the difference?

Category: `cross_file` · Difficulty: `hard` · Split: `held_out`

**Proposed reference answer:** InMemoryVectorStore inherits VectorStore.add_texts and overrides add_documents. For a generator, add_texts first consumes it with list(texts) to create texts_ for validation, but later builds Documents by zipping the original texts iterator, which is now exhausted. It therefore passes an empty document list to InMemoryVectorStore.add_documents. Under the stated embedding-helper premise, that embeds [], iterates over no document/vector pairs, returns [], and leaves the store empty. For a list, texts_ reuses the original list and the later zip still produces two Documents. add_documents embeds both page contents, generates UUID IDs because the documents have no IDs, and stores two records containing their text, vector, metadata, and generated ID. This describes the actual pinned implementation's iterator-consumption edge case, not its intended API contract.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Hard: identifies an integration edge case by following an exhausted iterable from the base implementation into the concrete store; neither interface declarations nor search dispatch alone establish the outcome. Verify InMemoryVectorStore has no add_texts override, compare texts_ materialization with the later zip(texts,...), and trace add_documents for empty versus two-document input under the explicit embedding premise. No source code or model was executed.

Annotation SHA-256: `128386fa269d8ac92a03dcc8034ddcc6589d38db20fc30d3842698ae38eae5e5`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: vectorstores/base.py 47-98 and vectorstores/in_memory.py 188-221. list(texts) at 78 exhausts a generator and line 90 zips the original texts, so add_documents receives []; a list yields two documents stored under generated UUIDs.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** vectorstores/base.py 47-98 and vectorstores/in_memory.py 188-221. list(texts) at 78 exhausts a generator and line 90 zips the original texts, so add_documents receives []; a list yields two documents stored under generated UUIDs.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/vectorstores/base.py:47–98](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/vectorstores/base.py:47) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/vectorstores/base.py#L47-L98)).

   Excerpt SHA-256: `ebb70b004d42b4a1e1113d3ec6e7bfe0de7f81a5cf3dc4bb130caaf83e39f4e2`

`````text
   47 |     def add_texts(
   48 |         self,
   49 |         texts: Iterable[str],
   50 |         metadatas: list[dict[str, Any]] | None = None,
   51 |         *,
   52 |         ids: list[str] | None = None,
   53 |         **kwargs: Any,
   54 |     ) -> list[str]:
   55 |         """Run more texts through the embeddings and add to the `VectorStore`.
   56 |
   57 |         Args:
   58 |             texts: Iterable of strings to add to the `VectorStore`.
   59 |             metadatas: Optional list of metadatas associated with the texts.
   60 |             ids: Optional list of IDs associated with the texts.
   61 |             **kwargs: `VectorStore` specific parameters.
   62 |
   63 |                 One of the kwargs should be `ids` which is a list of ids
   64 |                 associated with the texts.
   65 |
   66 |         Returns:
   67 |             List of IDs from adding the texts into the `VectorStore`.
   68 |
   69 |         Raises:
   70 |             ValueError: If the number of metadatas does not match the number of texts.
   71 |             ValueError: If the number of IDs does not match the number of texts.
   72 |         """
   73 |         if type(self).add_documents != VectorStore.add_documents:
   74 |             # This condition is triggered if the subclass has provided
   75 |             # an implementation of the upsert method.
   76 |             # The existing add_texts
   77 |             texts_: Sequence[str] = (
   78 |                 texts if isinstance(texts, (list, tuple)) else list(texts)
   79 |             )
   80 |             if metadatas and len(metadatas) != len(texts_):
   81 |                 msg = (
   82 |                     "The number of metadatas must match the number of texts."
   83 |                     f"Got {len(metadatas)} metadatas and {len(texts_)} texts."
   84 |                 )
   85 |                 raise ValueError(msg)
   86 |             metadatas_ = iter(metadatas) if metadatas else cycle([{}])
   87 |             ids_: Iterator[str | None] = iter(ids) if ids else cycle([None])
   88 |             docs = [
   89 |                 Document(id=id_, page_content=text, metadata=metadata_)
   90 |                 for text, metadata_, id_ in zip(texts, metadatas_, ids_, strict=False)
   91 |             ]
   92 |             if ids is not None:
   93 |                 # For backward compatibility
   94 |                 kwargs["ids"] = ids
   95 |
   96 |             return self.add_documents(docs, **kwargs)
   97 |         msg = f"`add_texts` has not been implemented for {self.__class__.__name__} "
   98 |         raise NotImplementedError(msg)
`````

2. [libs/core/langchain_core/vectorstores/in_memory.py:188–221](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/vectorstores/in_memory.py:188) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/vectorstores/in_memory.py#L188-L221)).

   Excerpt SHA-256: `8b367886369c0aa7957ce3754aa4f3a79c0e4b8ce6716edbdc2a2c6b3291ad2e`

`````text
  188 |     def add_documents(
  189 |         self,
  190 |         documents: list[Document],
  191 |         ids: list[str] | None = None,
  192 |         **kwargs: Any,
  193 |     ) -> list[str]:
  194 |         texts = [doc.page_content for doc in documents]
  195 |         vectors = self.embedding.embed_documents(texts)
  196 |
  197 |         if ids and len(ids) != len(texts):
  198 |             msg = (
  199 |                 f"ids must be the same length as texts. "
  200 |                 f"Got {len(ids)} ids and {len(texts)} texts."
  201 |             )
  202 |             raise ValueError(msg)
  203 |
  204 |         id_iterator: Iterator[str | None] = (
  205 |             iter(ids) if ids else iter(doc.id for doc in documents)
  206 |         )
  207 |
  208 |         ids_ = []
  209 |
  210 |         for doc, vector in zip(documents, vectors, strict=False):
  211 |             doc_id = next(id_iterator)
  212 |             doc_id_ = doc_id or str(uuid.uuid4())
  213 |             ids_.append(doc_id_)
  214 |             self.store[doc_id_] = {
  215 |                 "id": doc_id_,
  216 |                 "vector": vector,
  217 |                 "text": doc.page_content,
  218 |                 "metadata": doc.metadata,
  219 |             }
  220 |
  221 |         return ids_
`````

## lc-x-08

**Question:** For RunnablePassthrough.assign(double=lambda d: 2*d['n'], prior=lambda d: d['double']).invoke({'n': 2, 'double': 99}), do the two mapping branches see one another's computed values or the original input? What dictionary results, and which cross-file execution/merge steps establish it?

Category: `cross_file` · Difficulty: `medium` · Split: `held_out`

**Proposed reference answer:** assign creates a RunnableAssign whose mapper is a RunnableParallel over the provided mappings. RunnableParallel.invoke submits each mapping step with the same original input dictionary and collects their results by key. Thus double computes 4 and prior reads the original double value 99, rather than double's newly computed 4. RunnableAssign._invoke merges **value first and **self.mapper.invoke(value,...) second, so computed keys overwrite same-named input keys while other input keys survive. The result is {'n': 2, 'double': 4, 'prior': 99}.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Medium: combines the assign wrapper's merge order with RunnableParallel's independent use of the original input; one file alone leaves the mapper's data flow unspecified. Verify assign's RunnableAssign/RunnableParallel construction, the same input passed to each executor submission, and the order of the dictionary expansions. Treat lambdas as the explicit supplied inputs and make no timing claim about their scheduling.

Annotation SHA-256: `e413a8bfa933e789bff13f5ebceafc630e7c866a4816f208d92e3772f421f6cb`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: runnables/passthrough.py 205-223 and 484-511, runnables/base.py 4180-4215. Every step is submitted with the same input (4202); _invoke merges input first, mapper output second (495-502). Result {'n': 2, 'double': 4, 'prior': 99}.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** runnables/passthrough.py 205-223 and 484-511, runnables/base.py 4180-4215. Every step is submitted with the same input (4202); _invoke merges input first, mapper output second (495-502). Result {'n': 2, 'double': 4, 'prior': 99}.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/runnables/passthrough.py:205–223](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/passthrough.py:205) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/passthrough.py#L205-L223)).

   Excerpt SHA-256: `4a507f5daf0cd1019a106699a42c16a647a3992bac17079ec4eec0c38024c5fa`

`````text
  205 |     @classmethod
  206 |     @override
  207 |     def assign(
  208 |         cls,
  209 |         **kwargs: Runnable[dict[str, Any], Any]
  210 |         | Callable[[dict[str, Any]], Any]
  211 |         | Mapping[str, Runnable[dict[str, Any], Any] | Callable[[dict[str, Any]], Any]],
  212 |     ) -> RunnableAssign:
  213 |         """Merge the Dict input with the output produced by the mapping argument.
  214 |
  215 |         Args:
  216 |             **kwargs: `Runnable`, `Callable` or a `Mapping` from keys to `Runnable`
  217 |                 objects or `Callable`s.
  218 |
  219 |         Returns:
  220 |             A `Runnable` that merges the `dict` input with the output produced by the
  221 |             mapping argument.
  222 |         """
  223 |         return RunnableAssign(RunnableParallel[dict[str, Any]](kwargs))
`````

2. [libs/core/langchain_core/runnables/passthrough.py:484–511](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/passthrough.py:484) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/passthrough.py#L484-L511)).

   Excerpt SHA-256: `a028bf206e071d7abc76e32dca5346568a1e954ae98cff93b45633a8bbb55a0a`

`````text
  484 |     def _invoke(
  485 |         self,
  486 |         value: dict[str, Any],
  487 |         run_manager: CallbackManagerForChainRun,
  488 |         config: RunnableConfig,
  489 |         **kwargs: Any,
  490 |     ) -> dict[str, Any]:
  491 |         if not isinstance(value, dict):
  492 |             msg = "The input to RunnablePassthrough.assign() must be a dict."  # type: ignore[unreachable]
  493 |             raise ValueError(msg)  # noqa: TRY004
  494 |
  495 |         return {
  496 |             **value,
  497 |             **self.mapper.invoke(
  498 |                 value,
  499 |                 patch_config(config, callbacks=run_manager.get_child()),
  500 |                 **kwargs,
  501 |             ),
  502 |         }
  503 |
  504 |     @override
  505 |     def invoke(
  506 |         self,
  507 |         input: dict[str, Any],
  508 |         config: RunnableConfig | None = None,
  509 |         **kwargs: Any,
  510 |     ) -> dict[str, Any]:
  511 |         return self._call_with_config(self._invoke, input, config, **kwargs)
`````

3. [libs/core/langchain_core/runnables/base.py:4180–4215](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/base.py:4180) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/base.py#L4180-L4215)).

   Excerpt SHA-256: `14fbe99febb77db0da6b05d654ca8b07ead6d3f4f5bdfe5c7dd3275040400871`

`````text
 4180 |         def _invoke_step(
 4181 |             step: Runnable[Input, Any], input_: Input, config: RunnableConfig, key: str
 4182 |         ) -> Any:
 4183 |             child_config = patch_config(
 4184 |                 config,
 4185 |                 # mark each step as a child run
 4186 |                 callbacks=run_manager.get_child(f"map:key:{key}"),
 4187 |             )
 4188 |             with set_config_context(child_config) as context:
 4189 |                 return context.run(
 4190 |                     step.invoke,
 4191 |                     input_,
 4192 |                     child_config,
 4193 |                 )
 4194 |
 4195 |         # gather results from all steps
 4196 |         try:
 4197 |             # copy to avoid issues from the caller mutating the steps during invoke()
 4198 |             steps = dict(self.steps__)
 4199 |
 4200 |             with get_executor_for_config(config) as executor:
 4201 |                 futures = [
 4202 |                     executor.submit(_invoke_step, step, input, config, key)
 4203 |                     for key, step in steps.items()
 4204 |                 ]
 4205 |                 output = {
 4206 |                     key: future.result()
 4207 |                     for key, future in zip(steps, futures, strict=False)
 4208 |                 }
 4209 |         # finish the root run
 4210 |         except BaseException as e:
 4211 |             run_manager.on_chain_error(e)
 4212 |             raise
 4213 |         else:
 4214 |             run_manager.on_chain_end(output)
 4215 |             return output
`````

## lc-x-09

**Question:** A synchronous BaseChatModel uses InMemoryCache(maxsize=2), fixed model settings, and three distinct normalized prompts A, B, and C. Starting empty, it successfully processes A, then B, then A again as a cache hit, then C. Which prompt entries remain cached, what part of the new ChatResult is stored, and why does accessing A not protect it from eviction?

Category: `cross_file` · Difficulty: `hard` · Split: `held_out`

**Proposed reference answer:** BaseChatModel returns a cached list via its cache-hit path and, after an uncached successful generation, updates the cache using (prompt, llm_string, result.generations). Thus it stores the generations list, not the whole ChatResult. InMemoryCache.lookup only calls dict.get on the (prompt, llm_string) key and does not refresh insertion order. After storing A then B, the lookup of A leaves the order A,B. On storing C at capacity, update deletes next(iter(self._cache)), namely A, before inserting C. The surviving entries are B and C; this is insertion-order eviction rather than access-based LRU behavior.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Hard: connects the chat-model integration payload and cache-hit behavior with the concrete cache's eviction algorithm. Verify lookup's lack of reordering, the deletion before insertion in InMemoryCache.update, and BaseChatModel's hit return and update payload. Prompts are explicitly distinct after normalization, so the question does not depend on the separate message-ID normalization or rate-limiter policy.

Annotation SHA-256: `30530454609984611bdc20c207cd2238ac28af32b4250117144255e0523afee2`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: language_models/chat_models.py 1958-1967 and 2090-2092, caches.py 201-231. result.generations is stored; lookup is a plain dict get; update deletes the first-inserted key at capacity, so B and C remain.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** language_models/chat_models.py 1958-1967 and 2090-2092, caches.py 201-231. result.generations is stored; lookup is a plain dict get; update deletes the first-inserted key at capacity, so B and C remain.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/language_models/chat_models.py:1958–1967](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/language_models/chat_models.py:1958) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/language_models/chat_models.py#L1958-L1967)).

   Excerpt SHA-256: `1f69eaef2589cebf0ebf7122ce251088f089df2b3220ba588d9673eab249678d`

`````text
 1958 |                 prompt = dumps(normalized_messages)
 1959 |                 cache_val = llm_cache.lookup(prompt, llm_string)
 1960 |                 if isinstance(cache_val, list):
 1961 |                     converted_generations = self._convert_cached_generations(cache_val)
 1962 |                     self._replay_v2_events_for_cache_hit(
 1963 |                         converted_generations,
 1964 |                         run_manager=run_manager,
 1965 |                         **kwargs,
 1966 |                     )
 1967 |                     return ChatResult(generations=converted_generations)
`````

2. [libs/core/langchain_core/language_models/chat_models.py:2090–2092](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/language_models/chat_models.py:2090) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/language_models/chat_models.py#L2090-L2092)).

   Excerpt SHA-256: `612ddfa1262549d09a08e69abeb6cae003b0ecfce4bbe54f5c6ad73ff6456d33`

`````text
 2090 |         if check_cache and llm_cache is not None:
 2091 |             llm_cache.update(prompt, llm_string, result.generations)
 2092 |         return result
`````

3. [libs/core/langchain_core/caches.py:201–231](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/caches.py:201) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/caches.py#L201-L231)).

   Excerpt SHA-256: `1eeccf3b8c4c73826412481955f5d46a5a3f79bf0134f87d87e9c5f552d415a5`

`````text
  201 |     def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
  202 |         """Look up based on `prompt` and `llm_string`.
  203 |
  204 |         Args:
  205 |             prompt: A string representation of the prompt.
  206 |
  207 |                 In the case of a chat model, the prompt is a non-trivial
  208 |                 serialization of the prompt into the language model.
  209 |             llm_string: A string representation of the LLM configuration.
  210 |
  211 |         Returns:
  212 |             On a cache miss, return `None`. On a cache hit, return the cached value.
  213 |         """
  214 |         return self._cache.get((prompt, llm_string), None)
  215 |
  216 |     def update(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
  217 |         """Update cache based on `prompt` and `llm_string`.
  218 |
  219 |         Args:
  220 |             prompt: A string representation of the prompt.
  221 |
  222 |                 In the case of a chat model, the prompt is a non-trivial
  223 |                 serialization of the prompt into the language model.
  224 |             llm_string: A string representation of the LLM configuration.
  225 |             return_val: The value to be cached.
  226 |
  227 |                 The value is a list of `Generation` (or subclasses).
  228 |         """
  229 |         if self._maxsize is not None and len(self._cache) == self._maxsize:
  230 |             del self._cache[next(iter(self._cache))]
  231 |         self._cache[prompt, llm_string] = return_val
`````

## lc-x-10

**Question:** A synchronous RunnableWithMessageHistory uses InMemoryChatMessageHistory containing [H0, A0], has no separate history_messages_key, and receives current input messages [H1]. Its wrapped runnable successfully produces output messages [A1], with no intervening history mutation. Which messages are forwarded to the wrapped runnable, which are appended to the history afterward, and how do the wrapper and history implementation prevent the old messages from being duplicated?

Category: `cross_file` · Difficulty: `hard` · Split: `held_out`

**Proposed reference answer:** On entry, _enter_history copies the stored history and appends the current input messages when history_messages_key is unset, so the wrapped runnable sees [H0, A0, H1]. On successful exit, _exit_history reads the recorded input messages, removes the prefix whose length equals the current stored history length, and combines the remaining [H1] with output messages [A1]. It calls hist.add_messages([H1, A1]). InMemoryChatMessageHistory inherits the synchronous BaseChatMessageHistory.add_messages loop, which calls its overridden add_message for each message; that method appends to the in-memory list. The resulting stored history is [H0, A0, H1, A1], with H0 and A0 retained once rather than appended again.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Hard: combines history injection, successful-exit prefix stripping, inherited bulk addition, and the concrete per-message append behavior. Verify the synchronous entry/exit helpers, follow hist.add_messages to the base loop, and then InMemoryChatMessageHistory.add_message. H0/A0/H1/A1 denote message objects; concurrent mutation is explicitly excluded, and the question does not claim durable storage beyond this process's in-memory history. Final source audit: Included the concrete InMemoryChatMessageHistory inheritance and messages field anchoring the inherited bulk-add and concrete append methods.

Annotation SHA-256: `5ff1f58fe1c15c66858b4d401ec6025ce6ffa5e4a4434644db509880f09a4bb6`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T23:58:13.291074+00:00.

**Review notes:** Adopted verification notes from the preceding Claude AI cross-check: runnables/history.py 522-532 and 548-563, chat_history.py 182-192, 223-230 and 245-251. [H0, A0, H1] is forwarded; the stored prefix is stripped (556-558); [H1, A1] is added one message at a time.
Recorded from Shekhar's explicit human source-inspection and decision-adoption attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **accept**.

**AI cross-check notes:** runnables/history.py 522-532 and 548-563, chat_history.py 182-192, 223-230 and 245-251. [H0, A0, H1] is forwarded; the stored prefix is stripped (556-558); [H1, A1] is added one message at a time.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/runnables/history.py:522–532](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/history.py:522) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/history.py#L522-L532)).

   Excerpt SHA-256: `3b40b664268952ee57c6406b852b44a672d6bf19a150cd05bf50827ff7e3cac2`

`````text
  522 |     def _enter_history(self, value: Any, config: RunnableConfig) -> list[BaseMessage]:
  523 |         hist: BaseChatMessageHistory = config["configurable"]["message_history"]
  524 |         messages = hist.messages.copy()
  525 |
  526 |         if not self.history_messages_key:
  527 |             # return all messages
  528 |             input_val = (
  529 |                 value if not self.input_messages_key else value[self.input_messages_key]
  530 |             )
  531 |             messages += self._get_input_messages(input_val)
  532 |         return messages
`````

2. [libs/core/langchain_core/runnables/history.py:548–563](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/history.py:548) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/history.py#L548-L563)).

   Excerpt SHA-256: `7dc40da6a4dc3e8d84a100f046033c7a68adcccf2a6a3fe21b18358707fc4252`

`````text
  548 |     def _exit_history(self, run: Run, config: RunnableConfig) -> None:
  549 |         hist: BaseChatMessageHistory = config["configurable"]["message_history"]
  550 |
  551 |         # Get the input messages
  552 |         inputs = load(run.inputs, allowed_objects="messages")
  553 |         input_messages = self._get_input_messages(inputs)
  554 |         # If historic messages were prepended to the input messages, remove them to
  555 |         # avoid adding duplicate messages to history.
  556 |         if not self.history_messages_key:
  557 |             historic_messages = config["configurable"]["message_history"].messages
  558 |             input_messages = input_messages[len(historic_messages) :]
  559 |
  560 |         # Get the output messages
  561 |         output_val = load(run.outputs, allowed_objects="messages")
  562 |         output_messages = self._get_output_messages(output_val)
  563 |         hist.add_messages(input_messages + output_messages)
`````

3. [libs/core/langchain_core/chat_history.py:182–192](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/chat_history.py:182) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/chat_history.py#L182-L192)).

   Excerpt SHA-256: `41954ac74d9421613bf22b73d42944bf82b5a816e58a428ab432543e6a58d183`

`````text
  182 |     def add_messages(self, messages: Sequence[BaseMessage]) -> None:
  183 |         """Add a list of messages.
  184 |
  185 |         Implementations should over-ride this method to handle bulk addition of messages
  186 |         in an efficient manner to avoid unnecessary round-trips to the underlying store.
  187 |
  188 |         Args:
  189 |             messages: A sequence of `BaseMessage` objects to store.
  190 |         """
  191 |         for message in messages:
  192 |             self.add_message(message)
`````

4. [libs/core/langchain_core/chat_history.py:245–251](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/chat_history.py:245) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/chat_history.py#L245-L251)).

   Excerpt SHA-256: `58d206420ce98bbef04520989f5974eed30da7f91f19da67074cdc43d51ebfc9`

`````text
  245 |     def add_message(self, message: BaseMessage) -> None:
  246 |         """Add a self-created message to the store.
  247 |
  248 |         Args:
  249 |             message: The message to add.
  250 |         """
  251 |         self.messages.append(message)
`````

5. [libs/core/langchain_core/chat_history.py:223–230](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/chat_history.py:223) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/chat_history.py#L223-L230)).

   Excerpt SHA-256: `ca5243acc5a783b3f7fc6e87ff253e2ae4951bd2d6c226dc30cc8968dc9cb599`

`````text
  223 | class InMemoryChatMessageHistory(BaseChatMessageHistory, BaseModel):
  224 |     """In memory implementation of chat message history.
  225 |
  226 |     Stores messages in a memory list.
  227 |     """
  228 |
  229 |     messages: list[BaseMessage] = Field(default_factory=list)
  230 |     """A list of messages stored in memory."""
`````

