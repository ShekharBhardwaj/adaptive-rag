# Review packet 014: items 196–202

Order follows the shuffled template; no condition or strategy labels are added.

Template SHA-256: `8518b2ff60d2aff50a140755917ef33950edd3e1fae305653b0b73f5735dc1fa`

Only an actual human may fill the blank ratings. Preserve all bindings; transfer completed judgments to the matching nested score objects.

Correctness rubric: 0 = incorrect; 0.5 = partially correct; 1 = fully correct. Intermediate scores require justification in notes.

Citation rubric: 0 to 1 semantic support of answer claims by cited source; null when not applicable. Inspect the source, not just citation IDs.

## Item 196

### Immutable review bindings

```
{
  "review_id": "b753a22dab5ac9fad615f3e2e7e9ae1d1e8943f456077e5ffd3cab495f2a4bb7",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "fcf169e7c428ddf30604bb70834f136017b9396109163b11ae1c27b4210e5ef9",
  "output_sha256": "0be76070413216bb0492c3e6553ff3d14922f17628d80a064029628bdf4f2e41",
  "rubric_version": "manual-v1"
}
```

### Question

```
Which in-memory core chat-history class owns the messages list, and which synchronous methods append a message and reset that list? Locate the class, identify its bases and stored field, and name the two methods.
```

### Reference answer

```
InMemoryChatMessageHistory in libs/core/langchain_core/chat_history.py inherits BaseChatMessageHistory and BaseModel. Its stored field is messages: list[BaseMessage] = Field(default_factory=list). add_message(self, message: BaseMessage) appends to self.messages; clear(self) resets self.messages to a new empty list.
```

### Gold source references

```
[
  {
    "path": "libs/core/langchain_core/chat_history.py",
    "start_line": 223,
    "end_line": 230,
    "excerpt_sha256": "ca5243acc5a783b3f7fc6e87ff253e2ae4951bd2d6c226dc30cc8968dc9cb599"
  },
  {
    "path": "libs/core/langchain_core/chat_history.py",
    "start_line": 245,
    "end_line": 251,
    "excerpt_sha256": "58d206420ce98bbef04520989f5974eed30da7f91f19da67074cdc43d51ebfc9"
  },
  {
    "path": "libs/core/langchain_core/chat_history.py",
    "start_line": 261,
    "end_line": 263,
    "excerpt_sha256": "22166555c7c1f961033cf2054399f66e225beca2bfe7e35c120df1fa95ab0cc9"
  }
]
```

### Generated answer

```
The `InMemoryChatMessageHistory` class owns the messages list. It inherits from `BaseChatMessageHistory` and `BaseModel`, and stores messages in a `messages` field defined as `messages: list[BaseMessage] = Field(default_factory=list)`. The two synchronous methods are: (1) `add_message(self, message: BaseMessage)` which appends a message to the list, and (2) `clear(self)` which resets the list by setting `self.messages = []`.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/chat_history.py",
    "start_line": 215,
    "end_line": 267,
    "excerpt_sha256": "9227e9aa9d7b5293d51f422ed9a5f199fece90168dc6970acd9135e434a4b107",
    "evidence_id": "836547218213f32db150af83a864732017e3681f0ba740664b68452ac1140dc1",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "836547218213f32db150af83a864732017e3681f0ba740664b68452ac1140dc1"
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

## Item 197

### Immutable review bindings

```
{
  "review_id": "f28452f59093b48ad15ad3ffc9810f81f49281c3159d17206e78ab7b4c662085",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "4a00fb522b71f25e236d4aa8ff9806d2c759252f7c3e0707b5892aa6b444b767",
  "output_sha256": "8957184fa4272fe3451347d664e5e9c145af68d11f743b3747f272b4e722f839",
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
Without access to the repository evidence, I cannot reliably identify which concrete core tool class supports multiple input arguments while maintaining both synchronous and asynchronous callables, nor can I locate its implementation or identify the specific fields (input-schema, sync-callable, and async-callable). This question requires examining the actual codebase to determine the correct class and its field definitions. To answer this accurately, I would need access to the repository's source code, particularly files related to tool definitions and their implementations.
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

## Item 198

### Immutable review bindings

```
{
  "review_id": "a31a9c2753da6f4c2c15ccca1327db14c73070802ef4d318d79da2b2fe6da5a8",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "5da61a8054a22cb1d97df20751c2b413ba005ec97e0fb82990791048a4b2de78",
  "output_sha256": "39465c7b3a1dc67ba9846173df883072b8f54a1ff7e7df876f556461c54efe70",
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
Based on the code, when a RunnableWithFallbacks has a nonempty exception_key and dictionary input: (1) The error put in the dictionary for the next fallback is the most recent handled error (last_error). In your scenario, E2 from the first fallback would be placed in the dictionary for the next fallback attempt. (2) If all attempts fail with handled errors, the first error encountered (first_error) is raised. In your scenario, E1 would be raised. (3) For unhandled exceptions (BaseException that is not in exceptions_to_handle), the code calls run_manager.on_chain_error(e) and immediately re-raises the exception without attempting further fallbacks.
```

### Citations

```
[
  {
    "path": "libs/core/langchain_core/runnables/fallbacks.py",
    "start_line": 189,
    "end_line": 228,
    "excerpt_sha256": "e96f144f7c1468d94be29f6bd8e93d9710b92da173e48dac56f526085312684d",
    "evidence_id": "e4346ac2cfb0cbad91a0abf68a44f5dacebeabf8f94f420dd5239d59b20a738f",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/runnables/fallbacks.py",
    "start_line": 228,
    "end_line": 267,
    "excerpt_sha256": "db128a04b22ff6c001f5d04781bc6978280e75bb7add1b1c72888830a245afb3",
    "evidence_id": "9022910b50b92fcdcaad46fc7a967571f26aab283edb8807f29ae4e43b9bfb58",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "e4346ac2cfb0cbad91a0abf68a44f5dacebeabf8f94f420dd5239d59b20a738f",
  "9022910b50b92fcdcaad46fc7a967571f26aab283edb8807f29ae4e43b9bfb58"
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

## Item 199

### Immutable review bindings

```
{
  "review_id": "dcefccd59007396939d7e798c6c31c7ce73910400dbd7ce3be1b31abe4ef4db3",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "78eed3de7d27569dc5f76bc4405597c378944ead44930a0bca7c38125c132f7a",
  "output_sha256": "668efc791d2b2bd2376090cb3e7c13fe9749554cdec21f2d3d8aa5741ace6612",
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
Based on the evidence provided, synchronous BaseChatModel._generate_with_cache does NOT produce different serialized prompt keys for otherwise identical messages with different non-null message IDs. The test evidence shows that message IDs are stripped from cache keys, so functionally identical messages with different IDs produce the same cache key and result in cache hits. Regarding rate limiting: the evidence states that rate limiting is applied AFTER the cache check to avoid throttling cache hits, meaning a list-valued cache hit does NOT consume the model rate limiter before returning.
```

### Citations

```
[
  {
    "path": "openwiki/.claims/reference/chat-models.json",
    "start_line": 1,
    "end_line": 80,
    "excerpt_sha256": "9d432c45ef663fc537814a9070ca5a68dbc933d22c515c900aa15c6113c62bda",
    "evidence_id": "1e1a4c47387f89094afe9402b573d09b93b0cd02aa17d3c977b5f256e39d013a",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/tests/unit_tests/language_models/chat_models/test_cache.py",
    "start_line": 464,
    "end_line": 539,
    "excerpt_sha256": "ee4885a8846bf40c89130893cc6752ae8c8ce85e19f1d61212d98838bc808d88",
    "evidence_id": "dd7e3acce2926c000e109888c8bbae177e17134260c8fd501b3db97c0d08fa6a",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "1e1a4c47387f89094afe9402b573d09b93b0cd02aa17d3c977b5f256e39d013a",
  "dd7e3acce2926c000e109888c8bbae177e17134260c8fd501b3db97c0d08fa6a"
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

## Item 200

### Immutable review bindings

```
{
  "review_id": "4f56c550059e1bf3521ae65d96f0fd96496f23b1d5c75214c4cc542ad7476f5d",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "4156a42f63897c1c82109acf416637ca5722bcbdcf8c27218ab73704fbf98658",
  "output_sha256": "25f879b0a4c869eb32464b0e57529efafee65f66579bc1137a8ac5babbcc8df5",
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

## Item 201

### Immutable review bindings

```
{
  "review_id": "735ea8341324298b43f5765444c04851a394069c332bd7b862c5a50e90907bdc",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "5c92f077e6287dfb6e544cdba8dadf9f8fa7e06b41c61dbb2975bd2722a6bbe1",
  "output_sha256": "33253804f84c2d436c2c8508326d4846a60923a1ccf54d532fcdb8d29f954834",
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
Based on the evidence provided, I cannot reliably answer this question. The evidence shows that LangChain has a BaseCache interface with lookup() and update() methods, and demonstrates an InMemoryCache implementation in tests that uses a simple dictionary-based cache without size limits. However, the evidence does not contain information about: (1) an InMemoryCache with maxsize=2 parameter or LRU eviction behavior, (2) what specific parts of ChatResult are stored in the cache, or (3) eviction semantics when cache capacity is exceeded. The test evidence shows that cached values are lists of Generation objects (specifically ChatGeneration for chat models), but does not demonstrate or document maxsize-based eviction or explain why accessing a cached entry would not protect it from eviction. Without documentation of the specific caching implementation's eviction policy, I cannot determine which entries remain cached after the sequence A→B→A→C.
```

### Citations

```
[
  {
    "path": "libs/core/tests/unit_tests/language_models/chat_models/test_cache.py",
    "start_line": 1,
    "end_line": 76,
    "excerpt_sha256": "d65740a46e7bf02a87c95252cb9884707a60da38aa56989991123bad3e8c7937",
    "evidence_id": "a69bf58333b8f223545a62671ecff76031ccb4171d1091a8024c3b995148cb92",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  },
  {
    "path": "libs/core/langchain_core/caches.py",
    "start_line": 32,
    "end_line": 111,
    "excerpt_sha256": "26bbfc41396b0720933040ae19bacf9fd662272c8702a9da0218f1c28cefb55c",
    "evidence_id": "2b1266cc7e388aa14b1be9f96071dc4db3c26fd4f588312b123bdb4ea04f4474",
    "repo_commit": "ea17e48f0a4336c920394fd029de99f1568b4c38"
  }
]
```

### Claimed evidence IDs

```
[
  "a69bf58333b8f223545a62671ecff76031ccb4171d1091a8024c3b995148cb92",
  "2b1266cc7e388aa14b1be9f96071dc4db3c26fd4f588312b123bdb4ea04f4474"
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

## Item 202

### Immutable review bindings

```
{
  "review_id": "6025c71825c9a692071311b977a8dff9f7d5371f42d4acb361a266ad87d8a10e",
  "schema_version": "1",
  "run_id": "eb914cf0-4437-4d25-bfd3-2b4253f990a6",
  "job_id": "c04f732d28e66cfa5bec356fd1885ae0a800226b4d89d9af77f326011167ef01",
  "output_sha256": "7f4890d342647af96cb63cf3fcd4a20281c961badfba75ff55187cf985a716b9",
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
StructuredTool is the concrete core tool class that supports multiple input arguments while maintaining both synchronous and asynchronous callables. Its implementation is located in libs/core/langchain_core/tools/structured.py. The key fields are: (1) args_schema - an Annotated field of type ArgsSchema that defines the tool's input schema; (2) func - an Annotated Callable[..., Any] | None field for the synchronous function to run when the tool is called; (3) coroutine - an Annotated Callable[..., Awaitable[Any]] | None field for the asynchronous version of the function.
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


