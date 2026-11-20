# Development questions

Status: **AI-assisted pilot; 15 accepted, 0 pending independent acceptance in this packet.**

Source commit: `ea17e48f0a4336c920394fd029de99f1568b4c38`. Draft SHA-256: `e4c33c295518876c2b7537eff5fca281dd41b4779564062b41f0672220016a71`.

These are proposed reference answers, not measured experiment outputs. Check the answer against every cited excerpt; correct or reject unsupported claims.

[Review instructions](README.md). Record accept / revise / reject and a reason for each question. You can send decisions and corrections in chat using the IDs; Codex will transcribe only the decisions you actually provide.

## Questions

- [lc-c-01](#lc-c-01): When JsonOutputParser.parse_result encounters a JSONDecodeError while parsing model text, how does partial=True differ from partial=False, and which version of the text is attached to the non-partial error?
- [lc-c-02](#lc-c-02): For a serializable object whose lc_secrets maps credentials.api_key to API_KEY, with that nested dictionary and key present in its constructor kwargs, how does Serializable.to_json() represent the secret in the kwargs of the constructor dict it returns, and does the replacement modify the original nested dictionary?
- [lc-c-03](#lc-c-03): In convert_to_openai_messages, how is purely textual message content represented under text_format="string" versus text_format="block" when the original content is either one string or a list of strings/text blocks?
- [lc-c-04](#lc-c-04): If an Embeddings subclass intentionally implements different synchronous document and query encoders but inherits both asynchronous methods, do the asynchronous calls preserve that distinction, and how are they delegated?
- [lc-c-05](#lc-c-05): A legacy BaseLoader subclass overrides load() to return a document list but leaves lazy_load() inherited. How does inherited lazy_load() behave, and what happens for a subclass that overrides neither loading method?
- [lc-s-01](#lc-s-01): In the core JSON output-parser implementation, which class backs the backward-compatible SimpleJsonOutputParser name, and what parser-type identifier does that implementation report? Give the implementation file and relevant symbols.
- [lc-s-02](#lc-s-02): Which two functions implement the core load package's JSON-string and dictionary-style serialization entry points? Locate their implementation file, give their signatures, and distinguish their declared return types.
- [lc-s-03](#lc-s-03): Which core output class represents a single chat-model generation while retaining its structured message? Locate its definition, identify its parent class, and name the message field type and serialization discriminator.
- [lc-s-04](#lc-s-04): Locate the two fake embedding-model implementations provided by langchain_core for testing. What are their exact class names, and which two base classes does each declare?
- [lc-s-05](#lc-s-05): In the core document-loading interfaces, which abstract class defines parsing a Blob into a lazy stream of Documents? Locate the class and the exact abstract method signature a subclass must implement.
- [lc-x-01](#lc-x-01): In synchronous streaming, JsonOutputParser(diff=True) receives chunks whose accumulated parses are None, then an object A, then the same object A again, and then a different object B. Which stages emit output, what representation is emitted, and how is the previous value used? Trace the streaming base class and the JSON-specific implementation.
- [lc-x-02](#lc-x-02): Trace an ordinary user dictionary containing an 'lc' key and a nested constructor-shaped dictionary through _serialize_value and then load. What serialization wrapper is produced, and why are neither that dictionary nor its nested constructor-shaped data instantiated as LangChain objects during this round trip?
- [lc-x-03](#lc-x-03): Consider two ChatGenerationChunk values whose messages are BaseMessageChunk(type='ai'): the left message has content='A', and the right has content=[{'text': 'B'}] (a legacy text block without a type field). With no other metadata, what are the merged message content and the merged generation's text after left + right, and which implementations determine them?
- [lc-x-04](#lc-x-04): A custom Embeddings subclass inherits aembed_documents and its synchronous embed_documents raises StopIteration. What exception should awaiting aembed_documents surface through LangChain's executor helper, and how are executor selection and context propagation determined?
- [lc-x-05](#lc-x-05): A BaseLoader subclass yields one Document with page_content='abcdef' and metadata={'source': 'demo', 'start_index': 99}. Its load_and_split receives an explicit TextSplitter configured with add_start_index=True and chunk_overlap=2; assume that splitter's split_text returns ['abcd', 'cdef']. What page contents and metadata are returned, is the original metadata changed, and how does the loader-to-splitter call path determine this?

## lc-c-01

**Question:** When JsonOutputParser.parse_result encounters a JSONDecodeError while parsing model text, how does partial=True differ from partial=False, and which version of the text is attached to the non-partial error?

Category: `conceptual` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** The parser takes the first generation text and strips surrounding whitespace before parsing. With partial=True, a JSONDecodeError from parse_json_markdown is caught and the method returns None. With partial=False, the same decoding failure is wrapped in OutputParserException with a message beginning "Invalid json output:" followed by the stripped text, and llm_output is also that stripped text. This describes JSON-decoding failures; other failure types are not caught by those JSONDecodeError handlers.

**Authoring notes:** Inspected JsonOutputParser.parse_result at lines 81-95. Traced text extraction and strip before the partial branch, then compared the two JSONDecodeError handlers and the llm_output argument. No LangChain code or model was executed. Difficulty is medium because the answer requires comparing exception/control-flow branches and distinguishing stripped model text from raw input, rather than locating the class.

Annotation SHA-256: `a595f2d39386ad5ac26ba7f6773cfe50a5d2f1404a767077b79ea92c86d10a15`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:23:53.327293+00:00.

**Review notes:** json.py 81-95 supports every claim. The text is result[0].text, stripped (83-84); the partial branch returns None on JSONDecodeError (88-89); the non-partial branch raises OutputParserException with the stripped text in both the message and llm_output (93-95).
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/output_parsers/json.py:81–95](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/output_parsers/json.py:81) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/output_parsers/json.py#L81-L95)).

   Excerpt SHA-256: `e5ea2012de5b5baea5930d6c5ed1af47161e07660ce1c16e7cb8da8ab793a481`

`````text
   81 |         if isinstance(result[0], ChatGeneration):
   82 |             raise_if_refused(result[0].message)
   83 |         text = result[0].text
   84 |         text = text.strip()
   85 |         if partial:
   86 |             try:
   87 |                 return parse_json_markdown(text)
   88 |             except JSONDecodeError:
   89 |                 return None
   90 |         else:
   91 |             try:
   92 |                 return parse_json_markdown(text)
   93 |             except JSONDecodeError as e:
   94 |                 msg = f"Invalid json output: {text}"
   95 |                 raise OutputParserException(msg, llm_output=text) from e
`````

## lc-c-02

**Question:** For a serializable object whose lc_secrets maps credentials.api_key to API_KEY, with that nested dictionary and key present in its constructor kwargs, how does Serializable.to_json() represent the secret in the kwargs of the constructor dict it returns, and does the replacement modify the original nested dictionary?

Category: `conceptual` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** Serializable.to_json routes constructor kwargs through _replace_secrets when secret mappings exist. The mapped credentials.api_key leaf becomes {"lc": 1, "type": "secret", "id": ["API_KEY"]}, rather than the raw secret value. The replacement helper first shallow-copies the root and then copies each dictionary traversed along the dotted path before assigning the replacement leaf. For this existing nested path it therefore leaves the original root and nested credentials dictionary unchanged; this is path-wise copying, not a deep copy of all unrelated values.

**Authoring notes:** Inspected Serializable.to_json constructor-dict assembly and lc_secrets collection at lines 274-304 and the complete _replace_secrets implementation at lines 360-378. Manually followed the existing dotted path credentials.api_key, the root.copy call, the copy at each intermediate dictionary, and the secret-marker assignment. No environment secret was read and no code was executed. Difficulty is medium because it requires reasoning about aliasing/copy-on-path and nested replacement, not repeating a secret-redaction docstring. Revision requested by Shekhar: scope the question to the dict returned directly by Serializable.to_json(), excluding additional escaping performed by dumpd/dumps. The answer text is unchanged; the first evidence range now includes secrets.update(this.lc_secrets) at line 277. The revised annotation remains pending explicit acceptance.

Annotation SHA-256: `783a15312571d894f7db301188e65ecb1fd564dc3f388fca040ce7b982dd0abe`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-16T20:26:38.537917+00:00.

**Review notes:** I confirm the revised lc-c-02 at commit ea17e48f: the question names Serializable.to_json(), the answer is unchanged, and serializable.py 274-304 and 360-378 support it. Accept.
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

**AI source cross-check:** [Claude / Claude Code (claude-fable-5-2)](ai-cross-checks/claude-2026-11-15-01.json) recommends **confirm revised annotation**.

**AI cross-check notes:** the revised question matches the requested wording, the answer is unchanged, and evidence 274-304 and 360-378 supports it. Recommend confirming.

This AI recommendation preceded the recorded human acceptance above. The AI report remains a separate historical record.

**AI report binding:** The report annotation hash matches the human acceptance ledger’s before-hash. Adding human review metadata changed the current full annotation hash; the question, answer, evidence, and other authoring metadata remain identical to the cross-checked annotation.

### Source evidence

1. [libs/core/langchain_core/load/serializable.py:274–304](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/serializable.py:274) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/serializable.py#L274-L304)).

   Excerpt SHA-256: `7a92d56958104b03c5d0dce3357768568e5f05bb832c8790310da8a4323d593c`

`````text
  274 |             # Get a reference to self bound to each class in the MRO
  275 |             this = cast("Serializable", self if cls is None else super(cls, self))
  276 |
  277 |             secrets.update(this.lc_secrets)
  278 |             # Now also add the aliases for the secrets
  279 |             # This ensures known secret aliases are hidden.
  280 |             # Note: this does NOT hide any other extra kwargs
  281 |             # that are not present in the fields.
  282 |             for key in list(secrets):
  283 |                 value = secrets[key]
  284 |                 if (key in model_fields) and (
  285 |                     alias := model_fields[key].alias
  286 |                 ) is not None:
  287 |                     secrets[alias] = value
  288 |             lc_kwargs.update(this.lc_attributes)
  289 |
  290 |         # include all secrets, even if not specified in kwargs
  291 |         # as these secrets may be passed as an environment variable instead
  292 |         for key in secrets:
  293 |             secret_value = getattr(self, key, None) or lc_kwargs.get(key)
  294 |             if secret_value is not None:
  295 |                 lc_kwargs.update({key: secret_value})
  296 |
  297 |         return {
  298 |             "lc": 1,
  299 |             "type": "constructor",
  300 |             "id": self.lc_id(),
  301 |             "kwargs": lc_kwargs
  302 |             if not secrets
  303 |             else _replace_secrets(lc_kwargs, secrets),
  304 |         }
`````

2. [libs/core/langchain_core/load/serializable.py:360–378](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/serializable.py:360) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/serializable.py#L360-L378)).

   Excerpt SHA-256: `5e7b337c2c0cdc169f0b855e70e51c665ac812eb9b2aab76391f9166642307d3`

`````text
  360 | def _replace_secrets(
  361 |     root: dict[Any, Any], secrets_map: dict[str, str]
  362 | ) -> dict[Any, Any]:
  363 |     result = root.copy()
  364 |     for path, secret_id in secrets_map.items():
  365 |         [*parts, last] = path.split(".")
  366 |         current = result
  367 |         for part in parts:
  368 |             if part not in current:
  369 |                 break
  370 |             current[part] = current[part].copy()
  371 |             current = current[part]
  372 |         if last in current:
  373 |             current[last] = {
  374 |                 "lc": 1,
  375 |                 "type": "secret",
  376 |                 "id": [secret_id],
  377 |             }
  378 |     return result
`````

## lc-c-03

**Question:** In convert_to_openai_messages, how is purely textual message content represented under text_format="string" versus text_format="block" when the original content is either one string or a list of strings/text blocks?

Category: `conceptual` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** With text_format="string", a nonempty string stays a string, and a list containing only strings or {"type": "text", "text": ...} blocks is joined into a single string with newline separators. With text_format="block", a nonempty string is wrapped as one {"type": "text", "text": ...} block; list strings are similarly converted to text blocks, and text blocks contribute their type/text fields. The computed content is assigned to the outgoing message. Empty content becomes "" for string format and [] for block format. These statements concern purely textual content, not the other multimodal conversion branches.

**Authoring notes:** Inspected content-format branching at lines 1681-1711 and assignment/return at lines 1973-1985 of convert_to_openai_messages. Traced nonempty string, text-only list, and empty content inputs through the string and block format paths; excluded multimodal branches from the question. No external API or LangChain execution was used. Difficulty is medium because multiple input representations and branch conditions must be compared to predict output shape. Rechecked the inclusive evidence boundary: source line 1711 itself contains the successful content.append for an existing text block; no image_url branch is needed.

Annotation SHA-256: `e39d31fdfb01aad579c566a3c009bb1daca072ac9613645abf4f7787723f298a`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:23:53.327293+00:00.

**Review notes:** messages/utils.py 1681-1711 and 1977 support all four string/block cases and the empty-content case.
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/messages/utils.py:1681–1711](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/messages/utils.py:1681) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/messages/utils.py#L1681-L1711)).

   Excerpt SHA-256: `484092cca1ce2e64a23f299f6f6edbd8127cda1025b5044cf96ad34e6ddfbb42`

`````text
 1681 |         if not message.content:
 1682 |             content = "" if text_format == "string" else []
 1683 |         elif isinstance(message.content, str):
 1684 |             if text_format == "string":
 1685 |                 content = message.content
 1686 |             else:
 1687 |                 content = [{"type": "text", "text": message.content}]
 1688 |         elif text_format == "string" and all(
 1689 |             isinstance(block, str) or block.get("type") == "text"
 1690 |             for block in message.content
 1691 |         ):
 1692 |             content = "\n".join(
 1693 |                 block if isinstance(block, str) else block["text"]
 1694 |                 for block in message.content
 1695 |             )
 1696 |         else:
 1697 |             content = []
 1698 |             for j, block in enumerate(message.content):
 1699 |                 # OpenAI format
 1700 |                 if isinstance(block, str):
 1701 |                     content.append({"type": "text", "text": block})
 1702 |                 elif block.get("type") == "text":
 1703 |                     if missing := [k for k in ("text",) if k not in block]:
 1704 |                         err = (
 1705 |                             f"Unrecognized content block at "
 1706 |                             f"messages[{i}].content[{j}] has 'type': 'text' "
 1707 |                             f"but is missing expected key(s) "
 1708 |                             f"{missing}. Full content block:\n\n{block}"
 1709 |                         )
 1710 |                         raise ValueError(err)
 1711 |                     content.append({"type": block["type"], "text": block["text"]})
`````

2. [libs/core/langchain_core/messages/utils.py:1973–1985](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/messages/utils.py:1973) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/messages/utils.py#L1973-L1985)).

   Excerpt SHA-256: `2b0104d9a53462ffc478102bdb48542fe29d1d5946575e531cd4ee3b51d1af05`

`````text
 1973 |             if text_format == "string" and not any(
 1974 |                 block["type"] != "text" for block in content
 1975 |             ):
 1976 |                 content = "\n".join(block["text"] for block in content)
 1977 |         oai_msg["content"] = content
 1978 |         if message.content and not oai_msg["content"] and tool_messages:
 1979 |             oai_messages.extend(tool_messages)
 1980 |         else:
 1981 |             oai_messages.extend([oai_msg, *tool_messages])
 1982 |
 1983 |     if is_single:
 1984 |         return oai_messages[0]
 1985 |     return oai_messages
`````

## lc-c-04

**Question:** If an Embeddings subclass intentionally implements different synchronous document and query encoders but inherits both asynchronous methods, do the asynchronous calls preserve that distinction, and how are they delegated?

Category: `conceptual` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** They preserve the distinction. The inherited aembed_documents awaits run_in_executor(None, self.embed_documents, texts), passing the whole document-text list to the subclass document method. The inherited aembed_query separately awaits run_in_executor(None, self.embed_query, text), passing the query string to the subclass query method. Neither inherited method routes both tasks through one encoder or performs its own vector transformation; each returns the delegated result.

**Authoring notes:** Inspected both concrete inherited async methods at lines 58-78 and compared their bound-method arguments and return statements. Verified that each delegates to its respective overridable synchronous method with the corresponding original input. No embedding model or async execution was invoked. Difficulty is medium because it asks about subclass dispatch and preservation of different encoding behavior across async wrappers, not an abstract-method name lookup.

Annotation SHA-256: `0821796370a635cebcbadb3c421d8dc1817e5d2940151f946526cc3cec2a1c79`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:23:53.327293+00:00.

**Review notes:** embeddings.py 67 and 78 delegate to self.embed_documents and self.embed_query through run_in_executor(None, ...), so the subclass overrides run.
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/embeddings/embeddings.py:58–78](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/embeddings/embeddings.py:58) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/embeddings/embeddings.py#L58-L78)).

   Excerpt SHA-256: `3d8fa41198a127f6d3e5d36ffcce12e14e1c528504885e36cf5554cafc592a58`

`````text
   58 |     async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
   59 |         """Asynchronous Embed search docs.
   60 |
   61 |         Args:
   62 |             texts: List of text to embed.
   63 |
   64 |         Returns:
   65 |             List of embeddings.
   66 |         """
   67 |         return await run_in_executor(None, self.embed_documents, texts)
   68 |
   69 |     async def aembed_query(self, text: str) -> list[float]:
   70 |         """Asynchronous Embed query text.
   71 |
   72 |         Args:
   73 |             text: Text to embed.
   74 |
   75 |         Returns:
   76 |             Embedding.
   77 |         """
   78 |         return await run_in_executor(None, self.embed_query, text)
`````

## lc-c-05

**Question:** A legacy BaseLoader subclass overrides load() to return a document list but leaves lazy_load() inherited. How does inherited lazy_load() behave, and what happens for a subclass that overrides neither loading method?

Category: `conceptual` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** For the legacy subclass, BaseLoader.lazy_load checks that type(self).load differs from BaseLoader.load and returns iter(self.load()), so it exposes an iterator over the eagerly produced list; it does not make that legacy loading work intrinsically lazy. If neither method is overridden, that check is false and lazy_load raises NotImplementedError naming the class. BaseLoader.load itself calls list(self.lazy_load()), so the guard prevents the base implementations from endlessly delegating to one another.

**Authoring notes:** Inspected BaseLoader.load at lines 37-43 and lazy_load at lines 91-100. Compared the runtime type(self).load guard for an overriding legacy subclass versus the unchanged base implementation and followed the list/iter conversions. This is source inspection only; no files were loaded. Difficulty is medium because it requires understanding backward-compatible delegation and why eager list production is not converted into streaming work.

Annotation SHA-256: `dec52ed30e16dca790c9fa3b28fb79c9dc28e146b88a61a69b3bb30eb5bb3394`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:23:53.327293+00:00.

**Review notes:** document_loaders/base.py 97-100 and 43 support the guard, the NotImplementedError and the non-recursion claim.
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/document_loaders/base.py:37–43](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/document_loaders/base.py:37) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/document_loaders/base.py#L37-L43)).

   Excerpt SHA-256: `cdc49b3ab8c2ddb275e4abb101a048b65a2fab26f03b32f271312fa1a4709f9c`

`````text
   37 |     def load(self) -> list[Document]:
   38 |         """Load data into `Document` objects.
   39 |
   40 |         Returns:
   41 |             The documents.
   42 |         """
   43 |         return list(self.lazy_load())
`````

2. [libs/core/langchain_core/document_loaders/base.py:91–100](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/document_loaders/base.py:91) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/document_loaders/base.py#L91-L100)).

   Excerpt SHA-256: `074afd7007fc181dace3f7590fb70856c5ce03a9b7f0915e9b06494226ee6be7`

`````text
   91 |     def lazy_load(self) -> Iterator[Document]:
   92 |         """A lazy loader for `Document`.
   93 |
   94 |         Yields:
   95 |             The `Document` objects.
   96 |         """
   97 |         if type(self).load != BaseLoader.load:
   98 |             return iter(self.load())
   99 |         msg = f"{self.__class__.__name__} does not implement lazy_load()"
  100 |         raise NotImplementedError(msg)
`````

## lc-s-01

**Question:** In the core JSON output-parser implementation, which class backs the backward-compatible SimpleJsonOutputParser name, and what parser-type identifier does that implementation report? Give the implementation file and relevant symbols.

Category: `structural` · Difficulty: `easy` · Split: `development`

**Proposed reference answer:** In libs/core/langchain_core/output_parsers/json.py, SimpleJsonOutputParser is an alias assigned directly to JsonOutputParser. JsonOutputParser._type is a property returning the literal "simple_json_output_parser"; the alias does not define a separate parser class.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: easy: one short property and adjacent alias assignment establish both requested structural facts. Verified the alias assignment target and JsonOutputParser._type return literal. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `8f36e0feee07a2eb4da7dd5143cb04476b6405744c828af20e3ec27da01e0552`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:30:55.937801+00:00.

**Review notes:** output_parsers/json.py 32, 129-131 and 134-135. SimpleJsonOutputParser is a module-level alias of JsonOutputParser, whose _type property returns "simple_json_output_parser".
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/output_parsers/json.py:32–33](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/output_parsers/json.py:32) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/output_parsers/json.py#L32-L33)).

   Excerpt SHA-256: `b745d63cb160e8361d4e1f87949099806f996d51aecbaba6e8a756882d9c229f`

`````text
   32 | class JsonOutputParser(BaseCumulativeTransformOutputParser[Any]):
   33 |     """Parse the output of an LLM call to a JSON object.
`````

2. [libs/core/langchain_core/output_parsers/json.py:129–135](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/output_parsers/json.py:129) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/output_parsers/json.py#L129-L135)).

   Excerpt SHA-256: `679502c8cf83c5d5a32b6ded74681d778c2c619bc816429403a28a4f1dd7251a`

`````text
  129 |     @property
  130 |     def _type(self) -> str:
  131 |         return "simple_json_output_parser"
  132 |
  133 |
  134 | # For backwards compatibility
  135 | SimpleJsonOutputParser = JsonOutputParser
`````

## lc-s-02

**Question:** Which two functions implement the core load package's JSON-string and dictionary-style serialization entry points? Locate their implementation file, give their signatures, and distinguish their declared return types.

Category: `structural` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** Both are defined in libs/core/langchain_core/load/dump.py. dumps(obj: Any, *, pretty: bool = False, **kwargs: Any) -> str is the JSON-string entry point. dumpd(obj: Any) -> Any is documented as the dict-representation entry point; its annotation is Any, not dict. dumps returns json.dumps output after normalization/serialization, whereas dumpd returns the normalized _serialize_value result directly.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: medium: two similarly named functions must be distinguished, including the difference between documentation and the Any return annotation. Read each complete body and checked that dumpd directly returns _serialize_value rather than decoding dumps. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `b3e93f80812ed0753829ca21b28c6d689e20fc89548fe955d7b9ac89183d39a7`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:30:55.937801+00:00.

**Review notes:** load/dump.py 70 and 105. Signatures and return annotations (str, Any) are as stated; dumps ends in json.dumps (96-102) and dumpd returns _serialize_value(obj) directly (119-120).
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/load/dump.py:70–102](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/dump.py:70) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/dump.py#L70-L102)).

   Excerpt SHA-256: `6f5d45980d79e6d15e5d6d5647a8c05404e042f7ee817c27b31f470271aa455f`

`````text
   70 | def dumps(obj: Any, *, pretty: bool = False, **kwargs: Any) -> str:
   71 |     """Return a JSON string representation of an object.
   72 |
   73 |     Note:
   74 |         Plain dicts containing an `'lc'` key are automatically escaped to prevent
   75 |         confusion with LC serialization format. The escape marker is removed during
   76 |         deserialization.
   77 |
   78 |     Args:
   79 |         obj: The object to dump.
   80 |         pretty: Whether to pretty print the json.
   81 |
   82 |             If `True`, the json will be indented by either 2 spaces or the amount
   83 |             provided in the `indent` kwarg.
   84 |         **kwargs: Additional arguments to pass to `json.dumps`
   85 |
   86 |     Returns:
   87 |         A JSON string representation of the object.
   88 |
   89 |     Raises:
   90 |         ValueError: If `default` is passed as a kwarg.
   91 |     """
   92 |     if "default" in kwargs:
   93 |         msg = "`default` should not be passed to dumps"
   94 |         raise ValueError(msg)
   95 |
   96 |     obj = _dump_pydantic_models(obj)
   97 |     serialized = _serialize_value(obj)
   98 |
   99 |     if pretty:
  100 |         indent = kwargs.pop("indent", 2)
  101 |         return json.dumps(serialized, indent=indent, **kwargs)
  102 |     return json.dumps(serialized, **kwargs)
`````

2. [libs/core/langchain_core/load/dump.py:105–120](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/dump.py:105) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/dump.py#L105-L120)).

   Excerpt SHA-256: `4143c5e9121a129c37cbe9c73352317f8adfa6d76e85f4cfdddf49f8dfdcf25b`

`````text
  105 | def dumpd(obj: Any) -> Any:
  106 |     """Return a dict representation of an object.
  107 |
  108 |     Note:
  109 |         Plain dicts containing an `'lc'` key are automatically escaped to prevent
  110 |         confusion with LC serialization format. The escape marker is removed during
  111 |         deserialization.
  112 |
  113 |     Args:
  114 |         obj: The object to dump.
  115 |
  116 |     Returns:
  117 |         Dictionary that can be serialized to json using `json.dumps`.
  118 |     """
  119 |     obj = _dump_pydantic_models(obj)
  120 |     return _serialize_value(obj)
`````

## lc-s-03

**Question:** Which core output class represents a single chat-model generation while retaining its structured message? Locate its definition, identify its parent class, and name the message field type and serialization discriminator.

Category: `structural` · Difficulty: `easy` · Split: `development`

**Proposed reference answer:** ChatGeneration in libs/core/langchain_core/outputs/chat_generation.py subclasses Generation. It declares message: BaseMessage and a type field annotated Literal["ChatGeneration"] with default "ChatGeneration". The message field is the structured chat-model output; the type field is used for serialization.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: easy: the class header and adjacent field declarations provide the requested parent, payload, and discriminator. Checked the actual BaseMessage annotation rather than assuming every message is necessarily AIMessage. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `61b5e64866c467b8155bf14ed64cc9a5822710257644ae5f06dac232873c5859`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:30:55.937801+00:00.

**Review notes:** outputs/chat_generation.py 17, 37 and 41-42. ChatGeneration subclasses Generation and declares message: BaseMessage and type: Literal["ChatGeneration"] = "ChatGeneration".
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/outputs/chat_generation.py:17–42](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/outputs/chat_generation.py:17) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/outputs/chat_generation.py#L17-L42)).

   Excerpt SHA-256: `c90d89cd628f075f8aac09e6e8d0e7e255a5d6a796cdc1003f8bbfd493bd08ae`

`````text
   17 | class ChatGeneration(Generation):
   18 |     """A single chat generation output.
   19 |
   20 |     A subclass of `Generation` that represents the response from a chat model that
   21 |     generates chat messages.
   22 |
   23 |     The `message` attribute is a structured representation of the chat message. Most of
   24 |     the time, the message will be of type `AIMessage`.
   25 |
   26 |     Users working with chat models will usually access information via either
   27 |     `AIMessage` (returned from runnable interfaces) or `LLMResult` (available via
   28 |     callbacks).
   29 |     """
   30 |
   31 |     text: str = ""
   32 |     """The text contents of the output message.
   33 |
   34 |     !!! warning "SHOULD NOT BE SET DIRECTLY!"
   35 |
   36 |     """
   37 |     message: BaseMessage
   38 |     """The message output by the chat model."""
   39 |
   40 |     # Override type to be ChatGeneration, ignore mypy error as this is intentional
   41 |     type: Literal["ChatGeneration"] = "ChatGeneration"  # type: ignore[assignment]
   42 |     """Type is used exclusively for serialization purposes."""
`````

## lc-s-04

**Question:** Locate the two fake embedding-model implementations provided by langchain_core for testing. What are their exact class names, and which two base classes does each declare?

Category: `structural` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** The implementations are FakeEmbeddings and DeterministicFakeEmbedding, both in libs/core/langchain_core/embeddings/fake.py. Each class explicitly inherits from Embeddings and pydantic.BaseModel. These are testing implementations, not production embedding models.

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: medium: two nearby implementation classes share the same bases but have different exact names. Checked both class headers and their testing-only warning paragraphs; verified Embeddings and pydantic.BaseModel import bindings. Gold excerpts retain only those declarations/imports/warnings. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `438327b71e4792a7f7fb7e1a1bb81f4a767eb3fab9ccbbe7a5133e726c61b571`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:30:55.937801+00:00.

**Review notes:** embeddings/fake.py 16 and 70, with imports at 7 and 10. FakeEmbeddings and DeterministicFakeEmbedding each declare (Embeddings, BaseModel).
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/embeddings/fake.py:7–10](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/embeddings/fake.py:7) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/embeddings/fake.py#L7-L10)).

   Excerpt SHA-256: `d548ad91ee9fb6acda66ce26e724e04fc7d1e690f03b1656cbe669c22099e20a`

`````text
    7 | from pydantic import BaseModel
    8 | from typing_extensions import override
    9 |
   10 | from langchain_core.embeddings import Embeddings
`````

2. [libs/core/langchain_core/embeddings/fake.py:16–22](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/embeddings/fake.py:16) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/embeddings/fake.py#L16-L22)).

   Excerpt SHA-256: `f6273d7197b2fb988ec8d5b5588dbc02e0aefc3ae6cc45207e76a4bf09934d83`

`````text
   16 | class FakeEmbeddings(Embeddings, BaseModel):
   17 |     """Fake embedding model for unit testing purposes.
   18 |
   19 |     This embedding model creates embeddings by sampling from a normal distribution.
   20 |
   21 |     !!! danger "Toy model"
   22 |         Do not use this outside of testing, as it is not a real embedding model.
`````

3. [libs/core/langchain_core/embeddings/fake.py:70–77](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/embeddings/fake.py:70) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/embeddings/fake.py#L70-L77)).

   Excerpt SHA-256: `611639cd272a0cf6fbc901409694dcfc1f0b189ab834ae2f968b00bfea4b7297`

`````text
   70 | class DeterministicFakeEmbedding(Embeddings, BaseModel):
   71 |     """Deterministic fake embedding model for unit testing purposes.
   72 |
   73 |     This embedding model creates embeddings by sampling from a normal distribution
   74 |     with a seed based on the hash of the text.
   75 |
   76 |     !!! danger "Toy model"
   77 |         Do not use this outside of testing, as it is not a real embedding model.
`````

## lc-s-05

**Question:** In the core document-loading interfaces, which abstract class defines parsing a Blob into a lazy stream of Documents? Locate the class and the exact abstract method signature a subclass must implement.

Category: `structural` · Difficulty: `easy` · Split: `development`

**Proposed reference answer:** BaseBlobParser in libs/core/langchain_core/document_loaders/base.py is the abstract blob-parser interface. Its required method is @abstractmethod lazy_parse(self, blob: Blob) -> Iterator[Document].

**Authoring notes:** AI-assisted draft; independent human review is pending. Difficulty rationale: easy: a single abstract interface and method declaration identify the extension point. Checked the BaseBlobParser class header, abstractmethod decorator, Blob parameter, and Iterator[Document] return annotation. Verification: inspected the cited complete declarations/method bodies from pinned Git source, checked containing classes and signatures with the Python AST, and recomputed each SHA-256 over inclusive source lines joined with LF and no terminal newline. Repository code was not imported or executed.

Annotation SHA-256: `e721fd5627da8718381a3ca9e6312841472f88932bb1047758e3152ba33a8c07`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:30:55.937801+00:00.

**Review notes:** document_loaders/base.py 117 and 127-128. BaseBlobParser(ABC) with @abstractmethod lazy_parse(self, blob: Blob) -> Iterator[Document].
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/document_loaders/base.py:117–138](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/document_loaders/base.py:117) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/document_loaders/base.py#L117-L138)).

   Excerpt SHA-256: `e7da32ebb93c1bfdf563e2b6bd6de839f4525c5df09aba4b757c098d7334682d`

`````text
  117 | class BaseBlobParser(ABC):
  118 |     """Abstract interface for blob parsers.
  119 |
  120 |     A blob parser provides a way to parse raw data stored in a blob into one or more
  121 |     `Document` objects.
  122 |
  123 |     The parser can be composed with blob loaders, making it easy to reuse a parser
  124 |     independent of how the blob was originally loaded.
  125 |     """
  126 |
  127 |     @abstractmethod
  128 |     def lazy_parse(self, blob: Blob) -> Iterator[Document]:
  129 |         """Lazy parsing interface.
  130 |
  131 |         Subclasses are required to implement this method.
  132 |
  133 |         Args:
  134 |             blob: `Blob` instance
  135 |
  136 |         Returns:
  137 |             Generator of `Document` objects
  138 |         """
`````

## lc-x-01

**Question:** In synchronous streaming, JsonOutputParser(diff=True) receives chunks whose accumulated parses are None, then an object A, then the same object A again, and then a different object B. Which stages emit output, what representation is emitted, and how is the previous value used? Trace the streaming base class and the JSON-specific implementation.

Category: `cross_file` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** The cumulative transform accumulates Generation/ChatGeneration chunks and calls parse_result(..., partial=True). It emits nothing for None or a parsed value equal to the last emitted parsed value. The first A emits _diff(None, A); the repeated A emits nothing; B emits _diff(A, B). JsonOutputParser implements _diff with jsonpatch.make_patch(prev, next).patch, so emitted values are JSONPatch operation lists rather than whole parsed objects. prev_parsed is updated only after a changed non-None result is emitted.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Medium: combines stateful emission conditions with a subclass-specific diff representation. Verify the synchronous _transform loop, its initial prev_parsed=None and post-yield assignment, then follow JsonOutputParser._diff; distinguish accumulated chunks from emitted parsed values.

Annotation SHA-256: `908895591e6210ca780f862542735d33e032fef97506b86d42588aed129763f5`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:41:33.797320+00:00.

**Review notes:** output_parsers/transform.py 125-148 and json.py 51-53. Output is yielded only for a non-None parse that differs from prev_parsed (143), as self._diff(prev_parsed, parsed) (145), which JsonOutputParser implements with jsonpatch.make_patch(prev, next).patch; prev_parsed is updated after the yield (148).
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/output_parsers/transform.py:125–148](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/output_parsers/transform.py:125) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/output_parsers/transform.py#L125-L148)).

   Excerpt SHA-256: `e4e95a78f9eed33cba6da9d43f87391764e2d9afee1e3e8518de40e952c1363b`

`````text
  125 |     @override
  126 |     def _transform(self, input: Iterator[str | BaseMessage]) -> Iterator[Any]:
  127 |         prev_parsed = None
  128 |         acc_gen: GenerationChunk | ChatGenerationChunk | None = None
  129 |         for chunk in input:
  130 |             chunk_gen: GenerationChunk | ChatGenerationChunk
  131 |             if isinstance(chunk, BaseMessageChunk):
  132 |                 chunk_gen = ChatGenerationChunk(message=chunk)
  133 |             elif isinstance(chunk, BaseMessage):
  134 |                 chunk_gen = ChatGenerationChunk(
  135 |                     message=BaseMessageChunk(**chunk.model_dump())
  136 |                 )
  137 |             else:
  138 |                 chunk_gen = GenerationChunk(text=chunk)
  139 |
  140 |             acc_gen = chunk_gen if acc_gen is None else acc_gen + chunk_gen  # type: ignore[operator]
  141 |
  142 |             parsed = self.parse_result([acc_gen], partial=True)
  143 |             if parsed is not None and parsed != prev_parsed:
  144 |                 if self.diff:
  145 |                     yield self._diff(prev_parsed, parsed)
  146 |                 else:
  147 |                     yield parsed
  148 |                 prev_parsed = parsed
`````

2. [libs/core/langchain_core/output_parsers/json.py:51–53](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/output_parsers/json.py:51) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/output_parsers/json.py#L51-L53)).

   Excerpt SHA-256: `b15d5bdbcc4ca51550f7e17f0a293fbd02eac71864f47c8fbddc0097b4b23e5a`

`````text
   51 |     @override
   52 |     def _diff(self, prev: Any | None, next: Any) -> Any:
   53 |         return jsonpatch.make_patch(prev, next).patch
`````

## lc-x-02

**Question:** Trace an ordinary user dictionary containing an 'lc' key and a nested constructor-shaped dictionary through _serialize_value and then load. What serialization wrapper is produced, and why are neither that dictionary nor its nested constructor-shaped data instantiated as LangChain objects during this round trip?

Category: `cross_file` · Difficulty: `hard` · Split: `development`

**Proposed reference answer:** _needs_escaping returns true for a plain dictionary containing 'lc'. _serialize_value checks this before descending into its values and _escape_dict wraps the original dictionary as {'__lc_escaped__': original_dictionary}. The contents are not recursively serialized on that branch. In load's recursive helper, an escaped dictionary is detected before child traversal or Reviver invocation and is passed to _unescape_value. That helper returns the escaped wrapper's inner dictionary as-is, without further unescaping/traversal. Consequently both the outer lc-shaped dictionary and nested constructor-shaped data remain ordinary user data; they are not constructor-revived through this path.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Hard: follows two recursion boundaries and the ordering of escaping versus child traversal across serialization and loading. Verify _needs_escaping/_escape_dict, the early escaping branch in _serialize_value, the escaped-first branch in load._load, and _unescape_value's immediate inner-value return; do not assume that arbitrary unescaped constructor payloads have the same behavior. Evidence completeness refinement: the first range includes the actual _LC_ESCAPED_KEY constant and the escaped-dictionary recognizer, so the wrapper literal and load-side recognition are supported by implementation rather than documentation alone.

Annotation SHA-256: `8e0b5ffee66d7c59cd6b798ffd42ecb6e406bb517f74920fd7c869d267d36e2e`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:41:33.797320+00:00.

**Review notes:** load/_validation.py 28-66, 69-102, 165-191 and load/load.py 819-836. _serialize_value escapes before recursing (92-93); _load checks for the escape wrapper before child traversal or the reviver (826-831); _unescape_value returns the inner dict as-is (181-185).
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/load/_validation.py:28–66](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/_validation.py:28) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/_validation.py#L28-L66)).

   Excerpt SHA-256: `8ae19fa78b4fe35450acbe835e967128fa58662d9fb2bdbc94c66b8a2542fb27`

`````text
   28 | _LC_ESCAPED_KEY = "__lc_escaped__"
   29 | """Sentinel key used to mark escaped user dicts during serialization.
   30 |
   31 | When a plain dict contains 'lc' key (which could be confused with LC objects),
   32 | we wrap it as {"__lc_escaped__": {...original...}}.
   33 | """
   34 |
   35 |
   36 | def _needs_escaping(obj: dict[str, Any]) -> bool:
   37 |     """Check if a dict needs escaping to prevent confusion with LC objects.
   38 |
   39 |     A dict needs escaping if:
   40 |
   41 |     1. It has an `'lc'` key (could be confused with LC serialization format)
   42 |     2. It has only the escape key (would be mistaken for an escaped dict)
   43 |     """
   44 |     return "lc" in obj or (len(obj) == 1 and _LC_ESCAPED_KEY in obj)
   45 |
   46 |
   47 | def _escape_dict(obj: dict[str, Any]) -> dict[str, Any]:
   48 |     """Wrap a dict in the escape marker.
   49 |
   50 |     Example:
   51 |         ```python
   52 |         {"key": "value"}  # becomes {"__lc_escaped__": {"key": "value"}}
   53 |         ```
   54 |     """
   55 |     return {_LC_ESCAPED_KEY: obj}
   56 |
   57 |
   58 | def _is_escaped_dict(obj: dict[str, Any]) -> bool:
   59 |     """Check if a dict is an escaped user dict.
   60 |
   61 |     Example:
   62 |         ```python
   63 |         {"__lc_escaped__": {...}}  # is an escaped dict
   64 |         ```
   65 |     """
   66 |     return len(obj) == 1 and _LC_ESCAPED_KEY in obj
`````

2. [libs/core/langchain_core/load/_validation.py:69–102](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/_validation.py:69) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/_validation.py#L69-L102)).

   Excerpt SHA-256: `2d0aeab9a38aef4f223f7d6cae5db3488cb3ac9f6504875306c19d7c2f65413b`

`````text
   69 | def _serialize_value(obj: Any) -> Any:
   70 |     """Serialize a value with escaping of user dicts.
   71 |
   72 |     Called recursively on kwarg values to escape any plain dicts that could be confused
   73 |     with LC objects.
   74 |
   75 |     Args:
   76 |         obj: The value to serialize.
   77 |
   78 |     Returns:
   79 |         The serialized value with user dicts escaped as needed.
   80 |     """
   81 |     if isinstance(obj, Serializable):
   82 |         # This is an LC object - serialize it properly (not escaped)
   83 |         return _serialize_lc_object(obj)
   84 |     if isinstance(obj, dict):
   85 |         if not all(isinstance(k, (str, int, float, bool, type(None))) for k in obj):
   86 |             # if keys are not json serializable
   87 |             return to_json_not_implemented(obj)
   88 |         # Check if dict needs escaping BEFORE recursing into values.
   89 |         # If it needs escaping, wrap it as-is - the contents are user data that
   90 |         # will be returned as-is during deserialization (no instantiation).
   91 |         # This prevents re-escaping of already-escaped nested content.
   92 |         if _needs_escaping(obj):
   93 |             return _escape_dict(obj)
   94 |         # Safe dict (no 'lc' key) - recurse into values
   95 |         return {k: _serialize_value(v) for k, v in obj.items()}
   96 |     if isinstance(obj, (list, tuple)):
   97 |         return [_serialize_value(item) for item in obj]
   98 |     if isinstance(obj, (str, int, float, bool, type(None))):
   99 |         return obj
  100 |
  101 |     # Non-JSON-serializable object (datetime, custom objects, etc.)
  102 |     return to_json_not_implemented(obj)
`````

3. [libs/core/langchain_core/load/_validation.py:165–191](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/_validation.py:165) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/_validation.py#L165-L191)).

   Excerpt SHA-256: `db6dd10f5ea0b603adac350a692715e28cb93b0656c8e831cb17db6b314d76ed`

`````text
  165 | def _unescape_value(obj: Any) -> Any:
  166 |     """Unescape a value, processing escape markers in dict values and lists.
  167 |
  168 |     When an escaped dict is encountered (`{"__lc_escaped__": ...}`), it's
  169 |     unwrapped and the contents are returned AS-IS (no further processing).
  170 |     The contents represent user data that should not be modified.
  171 |
  172 |     For regular dicts and lists, we recurse to find any nested escape markers.
  173 |
  174 |     Args:
  175 |         obj: The value to unescape.
  176 |
  177 |     Returns:
  178 |         The unescaped value.
  179 |     """
  180 |     if isinstance(obj, dict):
  181 |         if _is_escaped_dict(obj):
  182 |             # Unwrap and return the user data as-is (no further unescaping).
  183 |             # The contents are user data that may contain more escape keys,
  184 |             # but those are part of the user's actual data.
  185 |             return obj[_LC_ESCAPED_KEY]
  186 |
  187 |         # Regular dict - recurse into values to find nested escape markers
  188 |         return {k: _unescape_value(v) for k, v in obj.items()}
  189 |     if isinstance(obj, list):
  190 |         return [_unescape_value(item) for item in obj]
  191 |     return obj
`````

4. [libs/core/langchain_core/load/load.py:819–836](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/load/load.py:819) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/load/load.py#L819-L836)).

   Excerpt SHA-256: `da3799812e45edbddab4dbd8fe2be023078a77110caf1bf76a6c16bcf273e92d`

`````text
  819 |     def _load(obj: Any, depth: int = 0) -> Any:
  820 |         if depth > _MAX_DEPTH:
  821 |             msg = f"Cannot load object nested more than {_MAX_DEPTH} levels deep."
  822 |             raise ValueError(msg)
  823 |         if isinstance(obj, dict):
  824 |             # Check for escaped dict FIRST (before recursing).
  825 |             # Escaped dicts are user data that should NOT be processed as LC objects.
  826 |             if _is_escaped_dict(obj):
  827 |                 return _unescape_value(obj)
  828 |
  829 |             # Not escaped - recurse into children then apply reviver
  830 |             loaded_obj = {k: _load(v, depth + 1) for k, v in obj.items()}
  831 |             return reviver(loaded_obj)
  832 |         if isinstance(obj, list):
  833 |             return [_load(o, depth + 1) for o in obj]
  834 |         return obj
  835 |
  836 |     return _load(obj)
`````

## lc-x-03

**Question:** Consider two ChatGenerationChunk values whose messages are BaseMessageChunk(type='ai'): the left message has content='A', and the right has content=[{'text': 'B'}] (a legacy text block without a type field). With no other metadata, what are the merged message content and the merged generation's text after left + right, and which implementations determine them?

Category: `cross_file` · Difficulty: `hard` · Split: `development`

**Proposed reference answer:** ChatGenerationChunk.__add__ builds a new ChatGenerationChunk from self.message + other.message. BaseMessageChunk.__add__ delegates content combination to merge_content. Its string-then-list branch produces ['A', {'text': 'B'}]. The new generation's set_text validator detects the legacy dictionary containing text without a type, collects the string 'A' and the legacy block's 'B', and joins them without a separator. The merged message therefore has list content ['A', {'text': 'B'}], while the generation's text is 'AB'.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Hard: follows generation addition, message addition, heterogeneous-content merging, and regenerated text; it cannot be answered from the class declaration alone. Verify the BaseMessageChunk (not AIMessageChunk) dispatch path, the string/list branch of merge_content, and ChatGeneration's legacy-block validator. The supplied objects are hypothetical code inputs, not measured experiment outputs.

Annotation SHA-256: `2f92e526569ccaf1bfb3748eae3b5d31eee3e983f34e067f4757f05803ef4568`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:41:33.797320+00:00.

**Review notes:** outputs/chat_generation.py 44-74 and 106-114, messages/base.py 365-408 and 414-451. merge_content gives ['A', {'text': 'B'}] (393); set_text takes the legacy-block branch and joins to 'AB' (57-68).
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/outputs/chat_generation.py:44–74](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/outputs/chat_generation.py:44) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/outputs/chat_generation.py#L44-L74)).

   Excerpt SHA-256: `dbcf583063fd8e956790acf47d11366d9b4007cf0306768a9eea9380c5d69eb3`

`````text
   44 |     @model_validator(mode="after")
   45 |     def set_text(self) -> Self:
   46 |         """Set the text attribute to be the contents of the message."""
   47 |         # Check for legacy blocks with "text" key but no "type" field.
   48 |         # Otherwise, delegate to `message.text`.
   49 |         if isinstance(self.message.content, list):
   50 |             has_legacy_blocks = any(
   51 |                 isinstance(block, dict)
   52 |                 and "text" in block
   53 |                 and block.get("type") is None
   54 |                 for block in self.message.content
   55 |             )
   56 |
   57 |             if has_legacy_blocks:
   58 |                 blocks = []
   59 |                 for block in self.message.content:
   60 |                     if isinstance(block, str):
   61 |                         blocks.append(block)
   62 |                     elif isinstance(block, dict):
   63 |                         block_type = block.get("type")
   64 |                         if block_type == "text" or (
   65 |                             block_type is None and "text" in block
   66 |                         ):
   67 |                             blocks.append(block.get("text", ""))
   68 |                 self.text = "".join(blocks)
   69 |             else:
   70 |                 self.text = self.message.text
   71 |         else:
   72 |             self.text = self.message.text
   73 |
   74 |         return self
`````

2. [libs/core/langchain_core/outputs/chat_generation.py:106–114](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/outputs/chat_generation.py:106) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/outputs/chat_generation.py#L106-L114)).

   Excerpt SHA-256: `e08697d0b9422464253d3e56b730da226c1e9bb83510c47d717ab03b081725b5`

`````text
  106 |         if isinstance(other, ChatGenerationChunk):
  107 |             generation_info = merge_dicts(
  108 |                 self.generation_info or {},
  109 |                 other.generation_info or {},
  110 |             )
  111 |             return ChatGenerationChunk(
  112 |                 message=self.message + other.message,
  113 |                 generation_info=generation_info or None,
  114 |             )
`````

3. [libs/core/langchain_core/messages/base.py:365–408](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/messages/base.py:365) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/messages/base.py#L365-L408)).

   Excerpt SHA-256: `b43ed72ea09fa11e2d48925391c4923c0da9f568c9ec3b629ef2f1c6b981dccf`

`````text
  365 | def merge_content(
  366 |     first_content: str | list[str | dict[Any, Any]],
  367 |     *contents: str | list[str | dict[Any, Any]],
  368 | ) -> str | list[str | dict[Any, Any]]:
  369 |     """Merge multiple message contents.
  370 |
  371 |     Args:
  372 |         first_content: The first `content`. Can be a string or a list.
  373 |         contents: The other `content`s. Can be a string or a list.
  374 |
  375 |     Returns:
  376 |         The merged content.
  377 |
  378 |     """
  379 |     merged: str | list[str | dict[Any, Any]]
  380 |     merged = "" if first_content is None else first_content
  381 |     if isinstance(merged, list):
  382 |         # The branches below append to it, which would change the first message.
  383 |         merged = merged.copy()
  384 |
  385 |     for content in contents:
  386 |         # If current is a string
  387 |         if isinstance(merged, str):
  388 |             # If the next chunk is also a string, then merge them naively
  389 |             if isinstance(content, str):
  390 |                 merged += content
  391 |             # If the next chunk is a list, add the current to the start of the list
  392 |             else:
  393 |                 merged = [merged, *content]
  394 |         elif isinstance(content, list):
  395 |             # If both are lists
  396 |             merged = merge_lists(merged, content)  # type: ignore[assignment]
  397 |         # If the first content is a list, and the second content is a string
  398 |         # If the last element of the first content is a string
  399 |         # Add the second content to the last element
  400 |         elif merged and isinstance(merged[-1], str):
  401 |             merged[-1] += content
  402 |         # If second content is an empty string, treat as a no-op
  403 |         elif content == "":
  404 |             pass
  405 |         # Otherwise, add the second content as a new element of the list
  406 |         elif merged:
  407 |             merged.append(content)
  408 |     return merged
`````

4. [libs/core/langchain_core/messages/base.py:414–451](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/messages/base.py:414) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/messages/base.py#L414-L451)).

   Excerpt SHA-256: `8b9720a4583b09947d73eb7e2a1485d9732884623c6dd2707cae1bfc768a7da2`

`````text
  414 |     def __add__(self, other: Any) -> BaseMessageChunk:  # type: ignore[override]
  415 |         """Message chunks support concatenation with other message chunks.
  416 |
  417 |         This functionality is useful to combine message chunks yielded from
  418 |         a streaming model into a complete message.
  419 |
  420 |         Args:
  421 |             other: Another message chunk to concatenate with this one.
  422 |
  423 |         Returns:
  424 |             A new message chunk that is the concatenation of this message chunk
  425 |             and the other message chunk.
  426 |
  427 |         Raises:
  428 |             TypeError: If the other object is not a message chunk.
  429 |
  430 |         Example:
  431 |             ```txt
  432 |               AIMessageChunk(content="Hello", ...)
  433 |             + AIMessageChunk(content=" World", ...)
  434 |             = AIMessageChunk(content="Hello World", ...)
  435 |             ```
  436 |         """
  437 |         if isinstance(other, BaseMessageChunk):
  438 |             # If both are (subclasses of) BaseMessageChunk,
  439 |             # concat into a single BaseMessageChunk
  440 |
  441 |             return self.__class__(
  442 |                 id=self.id,
  443 |                 type=self.type,
  444 |                 content=merge_content(self.content, other.content),
  445 |                 additional_kwargs=merge_dicts(
  446 |                     self.additional_kwargs, other.additional_kwargs
  447 |                 ),
  448 |                 response_metadata=merge_dicts(
  449 |                     self.response_metadata, other.response_metadata
  450 |                 ),
  451 |             )
`````

## lc-x-04

**Question:** A custom Embeddings subclass inherits aembed_documents and its synchronous embed_documents raises StopIteration. What exception should awaiting aembed_documents surface through LangChain's executor helper, and how are executor selection and context propagation determined?

Category: `cross_file` · Difficulty: `medium` · Split: `development`

**Proposed reference answer:** The inherited aembed_documents awaits run_in_executor(None, self.embed_documents, texts). The helper wraps the synchronous call, catches StopIteration, and raises RuntimeError from the original exception because StopIteration cannot be placed on an asyncio.Future safely. Since the executor/config argument is None, it uses the running event loop's default executor and runs the wrapper through copy_context().run. Thus the await surfaces RuntimeError with the StopIteration as its chained cause, rather than intentionally leaving the future pending.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Medium: the interface delegates the work, while exception translation and copied-context behavior live in a separate implementation file. Verify the exact inherited aembed_documents call and the wrapper/default-executor branches of run_in_executor. This is source inspection of an error path, not a provider call or an executable-test attestation.

Annotation SHA-256: `9c0fde84b4135a56e2d8fe02477191215a09b60c81ce53888e1e44707004874f`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:41:33.797320+00:00.

**Review notes:** embeddings/embeddings.py 58-67 and runnables/config.py 678-712. The wrapper raises RuntimeError from the StopIteration (699-703); executor None selects the loop default executor with copy_context().run (705-710).
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/embeddings/embeddings.py:58–67](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/embeddings/embeddings.py:58) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/embeddings/embeddings.py#L58-L67)).

   Excerpt SHA-256: `c7231416edb8b4360d5f97df17f96bd6c8410cdbc962aa3479504dd3c02b2aa1`

`````text
   58 |     async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
   59 |         """Asynchronous Embed search docs.
   60 |
   61 |         Args:
   62 |             texts: List of text to embed.
   63 |
   64 |         Returns:
   65 |             List of embeddings.
   66 |         """
   67 |         return await run_in_executor(None, self.embed_documents, texts)
`````

2. [libs/core/langchain_core/runnables/config.py:678–712](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/runnables/config.py:678) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/runnables/config.py#L678-L712)).

   Excerpt SHA-256: `a08c57af10a6b7c66bb5fed0e040f6f1a5dd7aae96c20ec42557d5152d3ddae7`

`````text
  678 | async def run_in_executor(
  679 |     executor_or_config: Executor | RunnableConfig | None,
  680 |     func: Callable[P, T],
  681 |     *args: P.args,
  682 |     **kwargs: P.kwargs,
  683 | ) -> T:
  684 |     """Run a function in an executor.
  685 |
  686 |     Args:
  687 |         executor_or_config: The executor or config to run in.
  688 |         func: The function.
  689 |         *args: The positional arguments to the function.
  690 |         **kwargs: The keyword arguments to the function.
  691 |
  692 |     Returns:
  693 |         The output of the function.
  694 |     """
  695 |
  696 |     def wrapper() -> T:
  697 |         try:
  698 |             return func(*args, **kwargs)
  699 |         except StopIteration as exc:
  700 |             # StopIteration can't be set on an asyncio.Future
  701 |             # it raises a TypeError and leaves the Future pending forever
  702 |             # so we need to convert it to a RuntimeError
  703 |             raise RuntimeError from exc
  704 |
  705 |     if executor_or_config is None or isinstance(executor_or_config, dict):
  706 |         # Use default executor with context copied from current context
  707 |         return await asyncio.get_running_loop().run_in_executor(
  708 |             None,
  709 |             cast("Callable[..., T]", partial(copy_context().run, wrapper)),
  710 |         )
  711 |
  712 |     return await asyncio.get_running_loop().run_in_executor(executor_or_config, wrapper)
`````

## lc-x-05

**Question:** A BaseLoader subclass yields one Document with page_content='abcdef' and metadata={'source': 'demo', 'start_index': 99}. Its load_and_split receives an explicit TextSplitter configured with add_start_index=True and chunk_overlap=2; assume that splitter's split_text returns ['abcd', 'cdef']. What page contents and metadata are returned, is the original metadata changed, and how does the loader-to-splitter call path determine this?

Category: `cross_file` · Difficulty: `hard` · Split: `development`

**Proposed reference answer:** BaseLoader.load_and_split uses the supplied splitter, calls self.load(), and passes those documents to split_documents; load materializes lazy_load. TextSplitter.split_documents collects each document's text and metadata and calls create_documents. create_documents deep-copies the input metadata for every chunk. For 'abcd' it searches from max(0, 0+0-2)=0 and records start_index=0; for 'cdef' it searches from max(0, 0+4-2)=2 and records start_index=2. The returned documents contain 'abcd' with {'source': 'demo', 'start_index': 0} and 'cdef' with {'source': 'demo', 'start_index': 2}. The original document's start_index remains 99 because the changes apply to deep copies.

**Authoring notes:** AI-assisted draft annotation pending independent human review; this is not an experiment result. Difficulty rationale and verification steps: Hard: traces loader materialization, explicit splitter selection, metadata transfer, deepcopy, and overlap-aware offset updates across two packages. Verify the supplied-splitter branch and self.load()->split_documents->create_documents calls, then calculate both index/previous_chunk_len updates. The split_text outputs are explicit premises, not invented repository behavior. Final source audit: Included the constructor assignment of public chunk_overlap/add_start_index settings to the internal fields used by create_documents.

Annotation SHA-256: `ab765e5e1289f31827b1d30d96274b09d3a977a6447a352cd5bf52d4233113b7`

**Recorded decision:** accepted by Shekhar.

**Recorded review time:** 2026-11-15T19:41:33.797320+00:00.

**Review notes:** document_loaders/base.py 37-43 and 74-87, text-splitters base.py 101-106 and 119-160. Metadata is deep-copied per chunk (137); start indices are 0 and 2 (139-141); the original keeps start_index 99.
Recorded from Shekhar's source-inspection attestation in chat for commit ea17e48f0a4336c920394fd029de99f1568b4c38. The reviewed_at timestamp is the attestation recording time; no separate inspection time was supplied.

### Source evidence

1. [libs/core/langchain_core/document_loaders/base.py:37–43](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/document_loaders/base.py:37) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/document_loaders/base.py#L37-L43)).

   Excerpt SHA-256: `cdc49b3ab8c2ddb275e4abb101a048b65a2fab26f03b32f271312fa1a4709f9c`

`````text
   37 |     def load(self) -> list[Document]:
   38 |         """Load data into `Document` objects.
   39 |
   40 |         Returns:
   41 |             The documents.
   42 |         """
   43 |         return list(self.lazy_load())
`````

2. [libs/core/langchain_core/document_loaders/base.py:74–87](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/core/langchain_core/document_loaders/base.py:74) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/core/langchain_core/document_loaders/base.py#L74-L87)).

   Excerpt SHA-256: `223570af1274e7133a05cbaf2933cf9ded72760b69d35d263d1791dc4b142984`

`````text
   74 |         if text_splitter is None:
   75 |             if not _HAS_TEXT_SPLITTERS:
   76 |                 msg = (
   77 |                     "Unable to import from langchain_text_splitters. Please specify "
   78 |                     "text_splitter or install langchain_text_splitters with "
   79 |                     "`pip install -U langchain-text-splitters`."
   80 |                 )
   81 |                 raise ImportError(msg)
   82 |
   83 |             text_splitter_: TextSplitter = RecursiveCharacterTextSplitter()
   84 |         else:
   85 |             text_splitter_ = text_splitter
   86 |         docs = self.load()
   87 |         return text_splitter_.split_documents(docs)
`````

3. [libs/text-splitters/langchain_text_splitters/base.py:119–160](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/text-splitters/langchain_text_splitters/base.py:119) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/text-splitters/langchain_text_splitters/base.py#L119-L160)).

   Excerpt SHA-256: `ef105079ae820eb2396dfcde133b77f251bcbf48f28d75ebb09a49f7e79a5b9e`

`````text
  119 |     def create_documents(
  120 |         self, texts: list[str], metadatas: list[dict[Any, Any]] | None = None
  121 |     ) -> list[Document]:
  122 |         """Create a list of `Document` objects from a list of texts.
  123 |
  124 |         Args:
  125 |             texts: A list of texts to be split and converted into documents.
  126 |             metadatas: Optional list of metadata to associate with each document.
  127 |
  128 |         Returns:
  129 |             A list of `Document` objects.
  130 |         """
  131 |         metadatas_ = metadatas or [{}] * len(texts)
  132 |         documents = []
  133 |         for i, text in enumerate(texts):
  134 |             index = 0
  135 |             previous_chunk_len = 0
  136 |             for chunk in self.split_text(text):
  137 |                 metadata = copy.deepcopy(metadatas_[i])
  138 |                 if self._add_start_index:
  139 |                     offset = index + previous_chunk_len - self._chunk_overlap
  140 |                     index = text.find(chunk, max(0, offset))
  141 |                     metadata["start_index"] = index
  142 |                     previous_chunk_len = len(chunk)
  143 |                 new_doc = Document(page_content=chunk, metadata=metadata)
  144 |                 documents.append(new_doc)
  145 |         return documents
  146 |
  147 |     def split_documents(self, documents: Iterable[Document]) -> list[Document]:
  148 |         """Split documents.
  149 |
  150 |         Args:
  151 |             documents: The documents to split.
  152 |
  153 |         Returns:
  154 |             A list of split documents.
  155 |         """
  156 |         texts, metadatas = [], []
  157 |         for doc in documents:
  158 |             texts.append(doc.page_content)
  159 |             metadatas.append(doc.metadata)
  160 |         return self.create_documents(texts, metadatas=metadatas)
`````

4. [libs/text-splitters/langchain_text_splitters/base.py:101–106](/Users/shekhar/development/research/adaptive-rag/datasets/repos/langchain/libs/text-splitters/langchain_text_splitters/base.py:101) ([pinned GitHub source](https://github.com/langchain-ai/langchain/blob/ea17e48f0a4336c920394fd029de99f1568b4c38/libs/text-splitters/langchain_text_splitters/base.py#L101-L106)).

   Excerpt SHA-256: `ef7b514fe9713bbc915d61f51793c825d3079ef5bf57beebcb9e85303c143b48`

`````text
  101 |         self._chunk_size = chunk_size
  102 |         self._chunk_overlap = chunk_overlap
  103 |         self._length_function = length_function
  104 |         self._keep_separator = keep_separator
  105 |         self._add_start_index = add_start_index
  106 |         self._strip_whitespace = strip_whitespace
`````

