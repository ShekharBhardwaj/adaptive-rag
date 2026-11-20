# Review packet 008: items 106–120

Order follows the shuffled template; no condition or strategy labels are added.

Template SHA-256: `8518b2ff60d2aff50a140755917ef33950edd3e1fae305653b0b73f5735dc1fa`

Only an actual human may fill the blank ratings. Preserve all bindings; transfer completed judgments to the matching nested score objects.

Correctness rubric: 0 = incorrect; 0.5 = partially correct; 1 = fully correct. Intermediate scores require justification in notes.

Citation rubric: 0 to 1 semantic support of answer claims by cited source; null when not applicable. Inspect the source, not just citation IDs.

## Item 106

### Immutable review bindings

```
{
  "review_id": "8bb3976b91f874b450b996b938dcb9dd9aeb850cc0b6474ae56ca1fdb761c258",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "e122366acc2729be39530916b5e2c7f991ceed9fa1812add3dbc7c2fe6b13456",
  "output_sha256": "8ea09f15681dfd2712816687fe81b0be37f7f8316ef2ebec0ec536cd9cbd9406",
  "rubric_version": "manual-v1"
}
```

### Question

```
How does synchronous VectorStoreRetriever._get_relevant_documents select the search operation for similarity, similarity_score_threshold, and mmr, and what happens when a runtime search kwarg conflicts with a configured search_kwargs value?
```

### Reference answer

```
The method first merges self.search_kwargs | kwargs, so a runtime kwarg wins on a conflicting key. The "similarity" path calls vectorstore.similarity_search; "similarity_score_threshold" calls similarity_search_with_relevance_scores and strips the scores from the returned (document, score) pairs; and "mmr" calls max_marginal_relevance_search. Each receives the query and merged kwargs, and the retriever returns documents rather than scored pairs. An unsupported search_type reaching this method raises ValueError.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/vectorstores/base.py",
    "start_line": 1041,
    "end_line": 1059,
    "excerpt_sha256": "f4228b47a26d92c05609fc14cc55fd0f54bd499795b6ee50a2809d828a431eac"
  }
]
```

### Generated answer

```
Without access to the VectorStoreRetriever source code, I cannot provide a definitive answer about how it selects between similarity, similarity_score_threshold, and mmr search operations, or how it resolves conflicts between runtime search kwargs and configured search_kwargs values. To answer this question accurately, I would need to examine the actual implementation of the synchronous VectorStoreRetriever._get_relevant_documents method, which typically involves: (1) checking the search_type parameter to determine which operation to use, (2) merging or prioritizing runtime kwargs against configured search_kwargs, and (3) applying the selected search strategy with the resolved parameters. The conflict resolution behavior depends on the specific implementation—it could prioritize runtime kwargs, configured kwargs, or raise an error. I recommend consulting the LangChain documentation or source code repository directly for the authoritative implementation details.
```

### Citations

```
[]
```

### Claimed evidence IDs

```
[]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 107

### Immutable review bindings

```
{
  "review_id": "76211712d8e83bbae35d82ba7664a78ff1bd612a24229a38ba6d68f63549d8e4",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "b60e174b8254ad21473ff385f1769613563584c335bb6e27a547fedb854a86b6",
  "output_sha256": "47bde6590ec38aae6f2bae3e8c52bba04e4887033510e8a351a3ccfacd5cd514",
  "rubric_version": "manual-v1"
}
```

### Question

```
Which concrete core tool class supports multiple input arguments while keeping both synchronous and asynchronous callables? Locate its implementation and identify the input-schema, sync-callable, and async-callable fields.
```

### Reference answer

```
StructuredTool in libs/core/langchain_core/tools/structured.py subclasses BaseTool and is documented as operating on any number of inputs. Its input-schema field is args_schema; its synchronous callable field is func; and its asynchronous callable field is coroutine. Both callable fields default to None.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/tools/structured.py",
    "start_line": 93,
    "end_line": 112,
    "excerpt_sha256": "79d1336c914285a4684b4b7f3856704fa437b60199857e455ae5a9e00aa61cd0"
  }
]
```

### Generated answer

```
StructuredTool is the concrete core tool class that supports multiple input arguments while maintaining both synchronous and asynchronous callables. Its implementation is located in `libs/core/langchain_core/tools/structured.py`. The key fields are: (1) `args_schema` - an Annotated field of type ArgsSchema that defines the tool's input schema; (2) `func` - an Annotated Callable that represents the synchronous function to run when the tool is called; (3) `coroutine` - an Annotated Callable returning Awaitable that represents the asynchronous version of the function. The class implements both `_run()` for synchronous execution and `_arun()` for asynchronous execution, with fallback behavior in `ainvoke()` that delegates to the synchronous implementation via `run_in_executor` if no coroutine is provided.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/tools/structured.py",
    "start_line": 93,
    "end_line": 172,
    "excerpt_sha256": "c5b01fb1de2baf2530b6d68d52522ae7c9e6160a4e8bfc12be31154e2370c31f",
    "evidence_id": "eb515aece5320c78a88a66def18ab03620565b1c7d0e8e5af200050b8ea3edd6",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "eb515aece5320c78a88a66def18ab03620565b1c7d0e8e5af200050b8ea3edd6"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 108

### Immutable review bindings

```
{
  "review_id": "04c0342246c25c44d318ebeab38c6d378e899bf56e7046439f49d953cc605621",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "4bd55c473ff07b158b0826704b77f06fe03a91968df298f5eb3424f85aa37d6f",
  "output_sha256": "b9fab4a910d55dfe4c482f93d11f7fbd9584df6089233fc9d1470d6ee87c8421",
  "rubric_version": "manual-v1"
}
```

### Question

```
In this pinned revision, compare InMemoryVectorStore.add_texts called on an empty store with a fresh one-shot generator yielding 'alpha', 'beta' against a list ['alpha', 'beta'], with no metadata or IDs. Assume the embedding helper accepts an empty list and returns one vector per supplied text. What documents/IDs reach storage in each case, and how does the inherited add_texts implementation cause the difference?
```

### Reference answer

```
InMemoryVectorStore inherits VectorStore.add_texts and overrides add_documents. For a generator, add_texts first consumes it with list(texts) to create texts_ for validation, but later builds Documents by zipping the original texts iterator, which is now exhausted. It therefore passes an empty document list to InMemoryVectorStore.add_documents. Under the stated embedding-helper premise, that embeds [], iterates over no document/vector pairs, returns [], and leaves the store empty. For a list, texts_ reuses the original list and the later zip still produces two Documents. add_documents embeds both page contents, generates UUID IDs because the documents have no IDs, and stores two records containing their text, vector, metadata, and generated ID. This describes the actual pinned implementation's iterator-consumption edge case, not its intended API contract.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/vectorstores/base.py",
    "start_line": 47,
    "end_line": 98,
    "excerpt_sha256": "ebb70b004d42b4a1e1113d3ec6e7bfe0de7f81a5cf3dc4bb130caaf83e39f4e2"
  },
  {
    "path": "libs/core/langchain_core/vectorstores/in_memory.py",
    "start_line": 188,
    "end_line": 221,
    "excerpt_sha256": "8b367886369c0aa7957ce3754aa4f3a79c0e4b8ce6716edbdc2a2c6b3291ad2e"
  }
]
```

### Generated answer

```
Without access to the specific pinned revision of InMemoryVectorStore's implementation, I cannot reliably answer this question. The behavior depends on critical implementation details: (1) how the inherited add_texts method handles generator vs. list inputs, (2) whether the generator is consumed correctly or exhausted prematurely, (3) how document IDs are generated when none are supplied, and (4) the exact state management during the add operation. The question suggests there is a meaningful difference between passing a generator and a list to the same method, which would indicate a bug or design issue in the inherited implementation—but determining what documents/IDs actually reach storage and why requires examining the actual source code of that specific revision.
```

### Citations

```
[]
```

### Claimed evidence IDs

```
[]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 109

### Immutable review bindings

```
{
  "review_id": "c3beaec0e365e07ecae16f2e57b346efea1382cee5e9e32a75e0398c1a30f750",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "5aab4e939fd04988bcd157e512c27ba22c0ae1534d016cf66b3fc3d322189b95",
  "output_sha256": "4cd25e4c9b9c118f436fa54fc5c9c4e8e666133fa1dc6554dacaeedb6fa845b6",
  "rubric_version": "manual-v1"
}
```

### Question

```
A RunnableWithFallbacks has a nonempty exception_key and dictionary input. Its primary runnable raises a handled error E1, its first fallback raises a handled error E2, and another fallback is about to run. Which error is put in the dictionary for that next fallback, which error is raised if all attempts fail with handled errors, and what happens to an unhandled exception?
```

### Reference answer

```
The next fallback receives the most recent handled error E2 under exception_key, because last_error is written into the input dictionary before each subsequent attempt. The first handled error E1 is kept separately as first_error and is the one reported and raised if every attempt fails with handled errors. An exception outside exceptions_to_handle is reported immediately and re-raised without proceeding to later fallbacks. The input is mutated in place when the exception key is set; it is not rebuilt as a separate dictionary for each fallback.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/runnables/fallbacks.py",
    "start_line": 184,
    "end_line": 212,
    "excerpt_sha256": "c9a8cde3276537912ea27215b6f8b53c24cb05fca780ffc68efb30e5012d8826"
  }
]
```

### Generated answer

```
I cannot reliably answer this question because no evidence excerpts were supplied, and the specific behavior of RunnableWithFallbacks regarding exception handling, exception_key population, and fallback sequencing requires consulting the actual implementation or authoritative documentation. The question asks about three specific behaviors: (1) which error is placed in the dictionary for the next fallback when prior fallbacks have failed, (2) which error is raised when all attempts fail with handled errors, and (3) how unhandled exceptions are treated. Without access to the source code or documentation for RunnableWithFallbacks, I cannot provide accurate answers to these implementation-specific details.
```

### Citations

```
[]
```

### Claimed evidence IDs

```
[]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 110

### Immutable review bindings

```
{
  "review_id": "cea775875b1d3ca11748fa447178e06f3f52a8ae5ce662e15575e07f517f1b00",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "3d1fd925ee4af31972f13c5e5b8205d739c1ae2e080e2943a986f88e72a5a3b1",
  "output_sha256": "dc1824c7ee0d7b2189dcd9187a58e9725b0b9c03426af9f707ba5bced3085b85",
  "rubric_version": "manual-v1"
}
```

### Question

```
For a fresh InMemoryRateLimiter with positive finite refill rate/polling interval and finite bucket capacity at least one, does it permit an immediate initial burst? Explain the first nonblocking acquire, later refill/capping, and blocking acquire, assuming no external state changes or competing requests.
```

### Reference answer

```
No initial full bucket is granted: available_tokens starts at 0.0 and last starts as None. On the first _consume call, last is set to the current monotonic time, giving zero elapsed time and no token, so acquire(blocking=False) returns False. Later calls add elapsed * requests_per_second only once that accrued amount reaches at least one token, update last, cap available_tokens at max_bucket_size, and consume exactly one token when at least one is available. Consumption/refill is guarded by a lock. A nonblocking acquire makes one consume attempt; a blocking acquire retries _consume and sleeps check_every_n_seconds between failures before returning True.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/rate_limiters.py",
    "start_line": 146,
    "end_line": 193,
    "excerpt_sha256": "2c2ddd2dcb4bf0b884b1dcd16d32db9b6d41713d76cb8918895d7ea703be26fd"
  },
  {
    "path": "libs/core/langchain_core/rate_limiters.py",
    "start_line": 212,
    "end_line": 218,
    "excerpt_sha256": "96e6c55c0948367e83b5851768494f94c19577e2e26fa13780f33d06fa4194c4"
  }
]
```

### Generated answer

```
No, a fresh InMemoryRateLimiter does not permit an immediate initial burst. On the first nonblocking acquire call, it returns False because available_tokens starts at 0.0. The _consume() method initializes self.last to the current time on first call, but since no time has elapsed yet, no tokens are added. The condition `elapsed * self.requests_per_second >= 1` is false (elapsed is ~0), so available_tokens remains 0.0, and the check `if self.available_tokens >= 1` fails, returning False.

Later, after sufficient time passes (at least 1/requests_per_second seconds), the refill mechanism adds tokens: `self.available_tokens += elapsed * self.requests_per_second`. The capping mechanism then enforces the maximum: `self.available_tokens = min(self.available_tokens, self.max_bucket_size)`, preventing the bucket from exceeding max_bucket_size even if many seconds elapse.

Once tokens are available, a blocking acquire will succeed. The blocking acquire loops, calling _consume() repeatedly with time.sleep(check_every_n_seconds) between attempts, until _consume() returns True (when available_tokens >= 1). It then returns True immediately without further blocking.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/rate_limiters.py",
    "start_line": 67,
    "end_line": 146,
    "excerpt_sha256": "321ff8e326439cdb2cbb04d47324a88e586ee3ecda5463b651cfd22ab8b042e3",
    "evidence_id": "c27706dd131435df846947c509eba7c5a65ff1ba9b94ad52955d18a219aef82c",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/rate_limiters.py",
    "start_line": 139,
    "end_line": 218,
    "excerpt_sha256": "76d09d2bfe9c13dd13b873b637c6884d11dd7ef7b2d4e7541aacd110cb3d69c9",
    "evidence_id": "8b62ba551bd94ef6a1a28b5424469ce094687809983727fd4d724aa316b15b25",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/tests/unit_tests/rate_limiters/test_in_memory_rate_limiter.py",
    "start_line": 1,
    "end_line": 74,
    "excerpt_sha256": "cbe3128e0593838e012c6d583ba1ad0a43c18da49251fd8df2f650a1922020e0",
    "evidence_id": "5a3bd9f0512bae21c3ce14ab1205c3cda7eae192753b1c441bb50db245ab6772",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "c27706dd131435df846947c509eba7c5a65ff1ba9b94ad52955d18a219aef82c",
  "8b62ba551bd94ef6a1a28b5424469ce094687809983727fd4d724aa316b15b25",
  "5a3bd9f0512bae21c3ce14ab1205c3cda7eae192753b1c441bb50db245ab6772"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 111

### Immutable review bindings

```
{
  "review_id": "f994e04ed7fd8396e65caa205953794c90dab764d2f3f5c4192a63f8e39141b6",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "a997fbb5d7b324b4658e17a3232bead8d620ebdbcb784e73ab02c24cbdec77c0",
  "output_sha256": "7a1416c6c2411408bdfa0acac359da3f7fcd735b514d90a6bb5015419235ac3e",
  "rubric_version": "manual-v1"
}
```

### Question

```
For RunnablePassthrough.assign(double=lambda d: 2*d['n'], prior=lambda d: d['double']).invoke({'n': 2, 'double': 99}), do the two mapping branches see one another's computed values or the original input? What dictionary results, and which cross-file execution/merge steps establish it?
```

### Reference answer

```
assign creates a RunnableAssign whose mapper is a RunnableParallel over the provided mappings. RunnableParallel.invoke submits each mapping step with the same original input dictionary and collects their results by key. Thus double computes 4 and prior reads the original double value 99, rather than double's newly computed 4. RunnableAssign._invoke merges **value first and **self.mapper.invoke(value,...) second, so computed keys overwrite same-named input keys while other input keys survive. The result is {'n': 2, 'double': 4, 'prior': 99}.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/runnables/passthrough.py",
    "start_line": 205,
    "end_line": 223,
    "excerpt_sha256": "4a507f5daf0cd1019a106699a42c16a647a3992bac17079ec4eec0c38024c5fa"
  },
  {
    "path": "libs/core/langchain_core/runnables/passthrough.py",
    "start_line": 484,
    "end_line": 511,
    "excerpt_sha256": "a028bf206e071d7abc76e32dca5346568a1e954ae98cff93b45633a8bbb55a0a"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 4180,
    "end_line": 4215,
    "excerpt_sha256": "14fbe99febb77db0da6b05d654ca8b07ead6d3f4f5bdfe5c7dd3275040400871"
  }
]
```

### Generated answer

```
Based on LangChain's RunnablePassthrough.assign() implementation, the two mapping branches see the original input dictionary, not each other's computed values. Each lambda receives the original {'n': 2, 'double': 99}. The execution proceeds as follows: (1) The assign() method creates a RunnableParallel that runs both branches concurrently against the input; (2) 'double' branch computes 2*2=4; (3) 'prior' branch computes d['double']=99 (from original input); (4) Results are merged back into the original input via dict.update(), producing {'n': 2, 'double': 4, 'prior': 99}. The key point is that assign() does not chain the branches sequentially—it runs them in parallel against the same input snapshot, then merges outputs. The 'prior' key gets 99 (the original value), not 4 (the newly computed value), because the lambda sees the input state before the 'double' assignment is applied.
```

### Citations

```
[]
```

### Claimed evidence IDs

```
[]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 112

### Immutable review bindings

```
{
  "review_id": "d2d6e2e0d2fad434033b42fa19f47343e724293c7aeef9dc8834427067238df0",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "dd35b88e6a8f07df260b81262dcef0edfa3b79326b18df9a42751f2f4d26c2aa",
  "output_sha256": "8a6a21024ec6f82acf0847e09ad7bd19a268cbac3a982d5d6c25f410d2880947",
  "rubric_version": "manual-v1"
}
```

### Question

```
In this pinned revision, compare InMemoryVectorStore.add_texts called on an empty store with a fresh one-shot generator yielding 'alpha', 'beta' against a list ['alpha', 'beta'], with no metadata or IDs. Assume the embedding helper accepts an empty list and returns one vector per supplied text. What documents/IDs reach storage in each case, and how does the inherited add_texts implementation cause the difference?
```

### Reference answer

```
InMemoryVectorStore inherits VectorStore.add_texts and overrides add_documents. For a generator, add_texts first consumes it with list(texts) to create texts_ for validation, but later builds Documents by zipping the original texts iterator, which is now exhausted. It therefore passes an empty document list to InMemoryVectorStore.add_documents. Under the stated embedding-helper premise, that embeds [], iterates over no document/vector pairs, returns [], and leaves the store empty. For a list, texts_ reuses the original list and the later zip still produces two Documents. add_documents embeds both page contents, generates UUID IDs because the documents have no IDs, and stores two records containing their text, vector, metadata, and generated ID. This describes the actual pinned implementation's iterator-consumption edge case, not its intended API contract.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/vectorstores/base.py",
    "start_line": 47,
    "end_line": 98,
    "excerpt_sha256": "ebb70b004d42b4a1e1113d3ec6e7bfe0de7f81a5cf3dc4bb130caaf83e39f4e2"
  },
  {
    "path": "libs/core/langchain_core/vectorstores/in_memory.py",
    "start_line": 188,
    "end_line": 221,
    "excerpt_sha256": "8b367886369c0aa7957ce3754aa4f3a79c0e4b8ce6716edbdc2a2c6b3291ad2e"
  }
]
```

### Generated answer

```
Looking at the InMemoryVectorStore implementation, calling add_texts on an empty store with either a generator or list ['alpha', 'beta'] will produce different results. With a generator, add_texts raises NotImplementedError because InMemoryVectorStore.add_texts explicitly raises NotImplementedError('This is not implemented yet.'). With a list, the same NotImplementedError is raised. However, the inherited add_texts implementation from VectorStore (evidence f3c1974ad0da18cedd0084c9ecd4f14c4bc697cd) converts the iterable to a list and then delegates to add_documents if add_documents is overridden. Since InMemoryVectorStore overrides add_documents but requires ids to be provided, and no ids are supplied in either case, add_documents will raise NotImplementedError('This is not implemented yet.') at line 68 of the test file. Therefore, in both cases (generator and list), no documents reach storage—both fail with NotImplementedError. The difference is not in what reaches storage, but in how the inherited implementation processes the input: it converts iterables to lists before delegation, but since ids are required and not provided, the add_documents method raises NotImplementedError before any storage occurs.
```

### Citations

```
[
  {
    "path": "libs/langchain/tests/unit_tests/indexes/test_indexing.py",
    "start_line": 40,
    "end_line": 119,
    "excerpt_sha256": "f0bde002584d07a6cc6630e4fa2a0b7d2a8b82de6a0ef486eb4d9d0111a75b7e",
    "evidence_id": "320356675e7977f028c0b3f8b1475cf8edb48f03abe99e0350ccdee426315658",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/vectorstores/base.py",
    "start_line": 44,
    "end_line": 123,
    "excerpt_sha256": "059d9456af89c5cee38f21846e7dbdc239a06da081e7811c633ed6b0296895db",
    "evidence_id": "075bb4bf1d361f0ea43debbc71b01b7832d4cf2c82b81beb1e04a2669cc3cac2",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/vectorstores/base.py",
    "start_line": 188,
    "end_line": 267,
    "excerpt_sha256": "2c18f956154ab779f5406160fd84291ad8698281d8edc7ad0782309896c43c8a",
    "evidence_id": "f3c1974ad0da18cedd0084c9ecd4f14c4bc697cd36c1bc5cc9bb3d4ab61cf446",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "320356675e7977f028c0b3f8b1475cf8edb48f03abe99e0350ccdee426315658",
  "075bb4bf1d361f0ea43debbc71b01b7832d4cf2c82b81beb1e04a2669cc3cac2",
  "f3c1974ad0da18cedd0084c9ecd4f14c4bc697cd36c1bc5cc9bb3d4ab61cf446"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 113

### Immutable review bindings

```
{
  "review_id": "ed5d02bc59982a242fefd137c4692d5ddd71e739fac7dfaa3e4474088755efaa",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "eef098c2062ae998183b0156c94a1c4f9ed4c26ff4f5f97376ac9500c23a3969",
  "output_sha256": "7b844760faf55b638346273d7990343ad4d0ecb0779cadca7e1629834093a003",
  "rubric_version": "manual-v1"
}
```

### Question

```
For RunnablePassthrough.assign(double=lambda d: 2*d['n'], prior=lambda d: d['double']).invoke({'n': 2, 'double': 99}), do the two mapping branches see one another's computed values or the original input? What dictionary results, and which cross-file execution/merge steps establish it?
```

### Reference answer

```
assign creates a RunnableAssign whose mapper is a RunnableParallel over the provided mappings. RunnableParallel.invoke submits each mapping step with the same original input dictionary and collects their results by key. Thus double computes 4 and prior reads the original double value 99, rather than double's newly computed 4. RunnableAssign._invoke merges **value first and **self.mapper.invoke(value,...) second, so computed keys overwrite same-named input keys while other input keys survive. The result is {'n': 2, 'double': 4, 'prior': 99}.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/runnables/passthrough.py",
    "start_line": 205,
    "end_line": 223,
    "excerpt_sha256": "4a507f5daf0cd1019a106699a42c16a647a3992bac17079ec4eec0c38024c5fa"
  },
  {
    "path": "libs/core/langchain_core/runnables/passthrough.py",
    "start_line": 484,
    "end_line": 511,
    "excerpt_sha256": "a028bf206e071d7abc76e32dca5346568a1e954ae98cff93b45633a8bbb55a0a"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 4180,
    "end_line": 4215,
    "excerpt_sha256": "14fbe99febb77db0da6b05d654ca8b07ead6d3f4f5bdfe5c7dd3275040400871"
  }
]
```

### Generated answer

```
The two mapping branches in RunnablePassthrough.assign() do NOT see one another's computed values; each branch receives the original input dictionary. For the invocation assign(double=lambda d: 2*d['n'], prior=lambda d: d['double']).invoke({'n': 2, 'double': 99}), the result is {'n': 2, 'double': 99, 'double': 4, 'prior': 99}. The execution flow is: (1) RunnablePassthrough.assign() creates a RunnableAssign with a RunnableParallel mapper containing the two branches; (2) RunnableAssign._invoke() calls self.mapper.invoke(value, ...) where value is the original input {'n': 2, 'double': 99}; (3) RunnableParallel processes both branches in parallel, each receiving the same original input; (4) the 'double' branch computes 2*2=4, and the 'prior' branch computes d['double']=99 from the original input; (5) RunnableAssign._invoke() merges results using {**value, **mapper_output}, producing the final dictionary with both original keys and new computed keys.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/runnables/passthrough.py",
    "start_line": 205,
    "end_line": 264,
    "excerpt_sha256": "0b1e19eee37b76f42193b2cd264ad8849d2240b3247b8329a10aa8c3d89873f5",
    "evidence_id": "eb2c71774721ed9ea69a038edd907234b5f042fd4130379d6966f75baf3e3dcf",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/runnables/passthrough.py",
    "start_line": 350,
    "end_line": 449,
    "excerpt_sha256": "fd4d066b1161ad4177b4d617a4e4062e8435ab0dd9d3888708e19adcab5be0ab",
    "evidence_id": "c92f077cfc98d0e91be645687be9efda561a9e20af9971807e1eea9f3aa6b6bc",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/runnables/passthrough.py",
    "start_line": 449,
    "end_line": 548,
    "excerpt_sha256": "0e031a4a1553dd7761ec8cfd9c5d5062bdbb662a8d701d3296c1d097dffd0c0c",
    "evidence_id": "0e443231a5ea57c73e5dc5172d129bd1a010232e4004f509ea860b1a5187d696",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "eb2c71774721ed9ea69a038edd907234b5f042fd4130379d6966f75baf3e3dcf",
  "c92f077cfc98d0e91be645687be9efda561a9e20af9971807e1eea9f3aa6b6bc",
  "0e443231a5ea57c73e5dc5172d129bd1a010232e4004f509ea860b1a5187d696"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 114

### Immutable review bindings

```
{
  "review_id": "29e889f6bada99fe29df8665e5e5512c1fc7e8b69053e3a5a49d4f539dcd415f",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "0fcdb8a2b5e7b772e0b664b0a3ac6f463df81ca04f108da2503e810bef9774c7",
  "output_sha256": "a3248320e8b1459fab50558221bddbccc8db7d1a2b6d72ead83b8f6269d56f6f",
  "rubric_version": "manual-v1"
}
```

### Question

```
Which core runnable-composition class stores a pipeline as first, middle, and last steps? Locate the class, give the declared types of those fields, and name the property that reconstructs their ordered list.
```

### Reference answer

```
RunnableSequence in libs/core/langchain_core/runnables/base.py stores first: Runnable[Input, Any], middle: list[Runnable[Any, Any]] with a default empty list, and last: Runnable[Any, Output]. Its steps property returns [self.first, *self.middle, self.last] in order.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3094,
    "end_line": 3098,
    "excerpt_sha256": "72d1426b53d4654509dc2b12453e1f68972e592c4c8ab9f74e055e36da602b13"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3178,
    "end_line": 3186,
    "excerpt_sha256": "d2aa46c50e3fc00095b10a9cf9deecabc7dd4959c81d0c6dd7d6a52895139640"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3239,
    "end_line": 3246,
    "excerpt_sha256": "ecb2afe592304e3c4f8efa01688df26b74ac392db11753ff92940d62830fe922"
  }
]
```

### Generated answer

```
The `RunnableSequence` class stores a pipeline as first, middle, and last steps. The declared types of these fields are: `first: Runnable[Input, Any]`, `middle: list[Runnable[Any, Any]]`, and `last: Runnable[Any, Output]`. The property that reconstructs their ordered list is `steps`, which returns `list[Runnable[Any, Any]]` and is implemented as `[self.first, *self.middle, self.last]`.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3166,
    "end_line": 3245,
    "excerpt_sha256": "66441de92f042b2fef1ea8be1de4be900825aa73263ba7899174c5b38be99dda",
    "evidence_id": "aae4c08fe1f32b6ca9af7cd73b6e2e0c299494ede5edaaff3bd0c7f0312f0160",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3238,
    "end_line": 3317,
    "excerpt_sha256": "99e1fb66252673a0436fc6444e0945842f9c248958b0143876b0c766ea378287",
    "evidence_id": "dddd8967b971f6878d47cf6649cf5c4cc3ce56475d8a98bad34037c3e69d42ac",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "aae4c08fe1f32b6ca9af7cd73b6e2e0c299494ede5edaaff3bd0c7f0312f0160",
  "dddd8967b971f6878d47cf6649cf5c4cc3ce56475d8a98bad34037c3e69d42ac"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 115

### Immutable review bindings

```
{
  "review_id": "c00167268f5ff8e9042ae30da303c1df37becb4e69c8f664262169b847491bb9",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "4984315d273524a84f4692f284e49443df2d0776f1cfe0c44266ba0fcf5c37e2",
  "output_sha256": "2f253bed2414ddd60add2643766edbe2158544272ab0eb7b08e39ba55e92ec89",
  "rubric_version": "manual-v1"
}
```

### Question

```
In synchronous BaseChatModel._generate_with_cache, do otherwise identical messages with different non-null message IDs produce different serialized prompt keys, and does a list-valued cache hit consume the model rate limiter before returning?
```

### Reference answer

```
Non-null message IDs are replaced with None in copied messages before the normalized message list is serialized for the prompt portion of the cache key. Thus a difference only in those IDs is removed from that serialized prompt; the model-configuration/stop-parameter llm_string remains the other lookup argument. A list-valued cache hit is converted/replayed and returned before control reaches rate_limiter.acquire(blocking=True), so that hit does not consume the limiter here. Original messages are not changed by the ID-normalization copies.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1942,
    "end_line": 1978,
    "excerpt_sha256": "9fe07a645e9d51165f4c1a9a483e2b3ad3a94048ed22c6d0c93ff1f7f5275c49"
  }
]
```

### Generated answer

```
Based on the evidence, messages with different non-null IDs do NOT produce different serialized prompt keys. The code normalizes messages by setting their `id` to `None` before serialization: `msg.model_copy(update={"id": None}) if getattr(msg, "id", None) is not None else msg`. This ensures that otherwise identical messages with different non-null IDs will serialize to the same prompt key. Regarding the rate limiter: a cache hit returns early (line 1968 in the evidence) via `return ChatResult(generations=converted_generations)`, which occurs BEFORE the rate limiter is acquired (lines 1978-1979). Therefore, a list-valued cache hit does NOT consume the model rate limiter before returning.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1950,
    "end_line": 1975,
    "excerpt_sha256": "9c462b2f8d9a0af3add652b57b7c7a5044136cb86a69b3f749e7d1a049b995a3",
    "evidence_id": "7a14e620b01522d13661f5c3d416c48b4f0a5ed8fc2ad9c50c923d33a3d58f27",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1975,
    "end_line": 1985,
    "excerpt_sha256": "f41de94dc1629268560b762e257fa9c509fb8da1c063650578d1125b57e77bf8",
    "evidence_id": "26f853ae86eb6d5dd9f2b81768ed5aa1bf24d442ddba9cfe90bdccfef89cf47b",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "7a14e620b01522d13661f5c3d416c48b4f0a5ed8fc2ad9c50c923d33a3d58f27",
  "26f853ae86eb6d5dd9f2b81768ed5aa1bf24d442ddba9cfe90bdccfef89cf47b"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 116

### Immutable review bindings

```
{
  "review_id": "7ee03fc6d2e50d6ce779d23dbffa805f8a5b182b1a0dfbbe3fd6b5035e46d0a0",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "fd8ce6856cd09bef28131884ce53a8f23d6d0593fb90143e31bd46205705f945",
  "output_sha256": "7d7ce5b6dad2b2e04be27b5f4f77321a01a44ec95f4735a6acfb6bd30a42e301",
  "rubric_version": "manual-v1"
}
```

### Question

```
Which concrete core tool class supports multiple input arguments while keeping both synchronous and asynchronous callables? Locate its implementation and identify the input-schema, sync-callable, and async-callable fields.
```

### Reference answer

```
StructuredTool in libs/core/langchain_core/tools/structured.py subclasses BaseTool and is documented as operating on any number of inputs. Its input-schema field is args_schema; its synchronous callable field is func; and its asynchronous callable field is coroutine. Both callable fields default to None.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/tools/structured.py",
    "start_line": 93,
    "end_line": 112,
    "excerpt_sha256": "79d1336c914285a4684b4b7f3856704fa437b60199857e455ae5a9e00aa61cd0"
  }
]
```

### Generated answer

```
The StructuredTool class is the concrete core tool class that supports multiple input arguments while keeping both synchronous and asynchronous callables. Its implementation includes three key fields: (1) args_schema - an Annotated field of type ArgsSchema that describes the tool's input arguments schema, (2) func - an Annotated field of type Callable[..., Any] | None that holds the synchronous callable function to run when the tool is called, and (3) coroutine - an Annotated field of type Callable[..., Awaitable[Any]] | None that holds the asynchronous version of the function.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/tools/structured.py",
    "start_line": 85,
    "end_line": 115,
    "excerpt_sha256": "1e5dd15c81afb53a4b50321d6c720e5e261491a109792eddef486e9ffcc99f3d",
    "evidence_id": "c9000318c1b8e98978f08e86f9cf0a057550ae3a8656fac7e98fc1eaa442253d",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "c9000318c1b8e98978f08e86f9cf0a057550ae3a8656fac7e98fc1eaa442253d"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 117

### Immutable review bindings

```
{
  "review_id": "df0d5b819bc9a062f812a990e4319a633ccdeb33757fd573927e0540688f8a27",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "945561661b195f815230433ef3a6e176cc7f4d3ad8e62b7300183871da7b6ef4",
  "output_sha256": "614d54994f24c87c957c77cb22e2885e72372f792a1bab9e018cca8124037c1a",
  "rubric_version": "manual-v1"
}
```

### Question

```
In synchronous BaseChatModel._generate_with_cache, do otherwise identical messages with different non-null message IDs produce different serialized prompt keys, and does a list-valued cache hit consume the model rate limiter before returning?
```

### Reference answer

```
Non-null message IDs are replaced with None in copied messages before the normalized message list is serialized for the prompt portion of the cache key. Thus a difference only in those IDs is removed from that serialized prompt; the model-configuration/stop-parameter llm_string remains the other lookup argument. A list-valued cache hit is converted/replayed and returned before control reaches rate_limiter.acquire(blocking=True), so that hit does not consume the limiter here. Original messages are not changed by the ID-normalization copies.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1942,
    "end_line": 1978,
    "excerpt_sha256": "9fe07a645e9d51165f4c1a9a483e2b3ad3a94048ed22c6d0c93ff1f7f5275c49"
  }
]
```

### Generated answer

```
Based on the evidence, messages with different non-null IDs do NOT produce different serialized prompt keys. The code explicitly normalizes messages by setting their IDs to None before serialization: `msg.model_copy(update={"id": None}) if getattr(msg, "id", None) is not None else msg`. This ensures that only the message content matters for the cache key, not the ID.

Regarding the rate limiter: A list-valued cache hit does NOT consume the model rate limiter before returning. The rate limiter is acquired only after the cache check completes (line 1975-1976: "Apply the rate limiter after checking the cache"). When a cache hit occurs and `ChatResult(generations=converted_generations)` is returned (line 1970), the rate limiter has not yet been acquired.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1935,
    "end_line": 1984,
    "excerpt_sha256": "df8adec8da90edc45a0230717182cbb85ec5fa0d647295a76a9b4ff54d70876d",
    "evidence_id": "e5afae5fd2725bcd9e81128d1776a8f32522e5262b33d3a32e73912073666df5",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "e5afae5fd2725bcd9e81128d1776a8f32522e5262b33d3a32e73912073666df5"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 118

### Immutable review bindings

```
{
  "review_id": "3fcf27c3a0966289989fac56090b268913bd39e23090974cf2c6f99e287e2a22",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "c3b86809eb3270ad2c89fb1d4ede61063a1ed5fa866e174a6e1af16a0b7fa8c6",
  "output_sha256": "f8a421e31c6159fd5a1484c615e351712c1aa554c017646c67c9f48fb0a086c8",
  "rubric_version": "manual-v1"
}
```

### Question

```
Which core runnable-composition class stores a pipeline as first, middle, and last steps? Locate the class, give the declared types of those fields, and name the property that reconstructs their ordered list.
```

### Reference answer

```
RunnableSequence in libs/core/langchain_core/runnables/base.py stores first: Runnable[Input, Any], middle: list[Runnable[Any, Any]] with a default empty list, and last: Runnable[Any, Output]. Its steps property returns [self.first, *self.middle, self.last] in order.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3094,
    "end_line": 3098,
    "excerpt_sha256": "72d1426b53d4654509dc2b12453e1f68972e592c4c8ab9f74e055e36da602b13"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3178,
    "end_line": 3186,
    "excerpt_sha256": "d2aa46c50e3fc00095b10a9cf9deecabc7dd4959c81d0c6dd7d6a52895139640"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3239,
    "end_line": 3246,
    "excerpt_sha256": "ecb2afe592304e3c4f8efa01688df26b74ac392db11753ff92940d62830fe922"
  }
]
```

### Generated answer

```
The `RunnableSequence` class stores a pipeline as first, middle, and last steps. The declared types of these fields are: `first: Runnable[Input, Any]`, `middle: list[Runnable[Any, Any]]`, and `last: Runnable[Any, Output]`. The property that reconstructs their ordered list is `steps`, which returns `[self.first, *self.middle, self.last]`.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3177,
    "end_line": 3190,
    "excerpt_sha256": "47101fba14d780aa4b5256d5206ec77b39f0d331a36545e6c508405909f6287e",
    "evidence_id": "5f7a93c2135fc51ecfa571e6c626b20fef9fe7f0e5ba14ea982df7ab08c27c62",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/runnables/base.py",
    "start_line": 3238,
    "end_line": 3257,
    "excerpt_sha256": "766b9c331c4e4a82ef4eb468538ccf3c84e911256582555b7e27dd52ec4e3c93",
    "evidence_id": "87ba04676b1f998d7fdc61869aaead1495d19710ba1131e312c3005ca4384971",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "5f7a93c2135fc51ecfa571e6c626b20fef9fe7f0e5ba14ea982df7ab08c27c62",
  "87ba04676b1f998d7fdc61869aaead1495d19710ba1131e312c3005ca4384971"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 119

### Immutable review bindings

```
{
  "review_id": "10079e5884a8dc1862ab0788eab7c17360baaf43e3f9c1067f32938e4e8d461a",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "34ce9219a68ffb282dfb5963d1f30dc11dd037483936df98940fec93039e150a",
  "output_sha256": "3c3fb60be8ce959567858fc27c41fa6c049566a7f9b4e6aed3f0dd1ba8f07684",
  "rubric_version": "manual-v1"
}
```

### Question

```
Inside BaseChatModel, which helper normalizes legacy cached Generation objects into chat-generation objects? Locate the implementation file and give the helper name, input annotation, and return annotation.
```

### Reference answer

```
The helper is BaseChatModel._convert_cached_generations in libs/core/langchain_core/language_models/chat_models.py. Its signature is _convert_cached_generations(self, cache_val: list[Generation]) -> list[ChatGeneration]. It is documented as converting cached Generation objects to ChatGeneration objects, including legacy or serialization-related cache data.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1448,
    "end_line": 1487,
    "excerpt_sha256": "89931cabea00cada1ef0159f991f012cd135bac2498aa80fdc22e286a57c395f"
  }
]
```

### Generated answer

```
Inside BaseChatModel, the helper that normalizes legacy cached Generation objects into chat-generation objects is `_convert_cached_generations`. It is located in `libs/core/langchain_core/language_models/chat_models.py`. The input annotation is `cache_val: list[Generation]` and the return annotation is `list[ChatGeneration]`.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1446,
    "end_line": 1485,
    "excerpt_sha256": "ffbf26ac860bdc43dbfa6ab0cf17bf8259434f3d43bbd3df5e67e63cfaebc1e4",
    "evidence_id": "9e248c9f25eb16a8e67d5a27d8075c87ba10aead9eacfa7a19e456efa096cad1",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "9e248c9f25eb16a8e67d5a27d8075c87ba10aead9eacfa7a19e456efa096cad1"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:



---

## Item 120

### Immutable review bindings

```
{
  "review_id": "7e563779a151766e2e5b96fde0bfe73c0236f31b6ba7ff84148c53ae527c993d",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "1a578c0cf1d55e9b61723176f0bfc73e830df3eeaad78be8a25e2f88ec2336ed",
  "output_sha256": "e488b6127daf94a47dd7a3b6b79b3d3fedd6abbfbba93d96cdd8f5b63f9e21ec",
  "rubric_version": "manual-v1"
}
```

### Question

```
A synchronous BaseChatModel uses InMemoryCache(maxsize=2), fixed model settings, and three distinct normalized prompts A, B, and C. Starting empty, it successfully processes A, then B, then A again as a cache hit, then C. Which prompt entries remain cached, what part of the new ChatResult is stored, and why does accessing A not protect it from eviction?
```

### Reference answer

```
BaseChatModel returns a cached list via its cache-hit path and, after an uncached successful generation, updates the cache using (prompt, llm_string, result.generations). Thus it stores the generations list, not the whole ChatResult. InMemoryCache.lookup only calls dict.get on the (prompt, llm_string) key and does not refresh insertion order. After storing A then B, the lookup of A leaves the order A,B. On storing C at capacity, update deletes next(iter(self._cache)), namely A, before inserting C. The surviving entries are B and C; this is insertion-order eviction rather than access-based LRU behavior.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 1958,
    "end_line": 1967,
    "excerpt_sha256": "1f69eaef2589cebf0ebf7122ce251088f089df2b3220ba588d9673eab249678d"
  },
  {
    "path": "libs/core/langchain_core/language_models/chat_models.py",
    "start_line": 2090,
    "end_line": 2092,
    "excerpt_sha256": "612ddfa1262549d09a08e69abeb6cae003b0ecfce4bbe54f5c6ad73ff6456d33"
  },
  {
    "path": "libs/core/langchain_core/caches.py",
    "start_line": 201,
    "end_line": 231,
    "excerpt_sha256": "1eeccf3b8c4c73826412481955f5d46a5a3f79bf0134f87d87e9c5f552d415a5"
  }
]
```

### Generated answer

```
Based on the InMemoryCache implementation, after processing prompts A, B, A (cache hit), and C with maxsize=2: prompts B and C remain cached. Only the return value (list of Generation/ChatGeneration objects) is stored, not the full ChatResult. Accessing A as a cache hit does not protect it from eviction because the lookup operation is read-only and does not update the cache's internal ordering. InMemoryCache uses a simple dict without LRU tracking—when maxsize is exceeded, it removes the oldest entry by insertion order (next(iter(self._cache))), not by access recency. Therefore, A is evicted when C is added because A was inserted first, even though it was accessed again as a cache hit.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/caches.py",
    "start_line": 153,
    "end_line": 252,
    "excerpt_sha256": "e744ff51add87ba8bc5fa0aae8c42344dd5a5a9826e39924e901e86321e65543",
    "evidence_id": "17a8317dfa1d320e2dc70539b3523d07f95158a0b103c8020f221c6adf093619",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "17a8317dfa1d320e2dc70539b3523d07f95158a0b103c8020f221c6adf093619"
]
```

### Source commit

```
ea17e48f0a4336c920394fd029de99f1568b4c38
```

### Human review

Reviewer: 

Reviewed at (with timezone): 

Correctness: 

Citation support (or not applicable): 

Notes:


