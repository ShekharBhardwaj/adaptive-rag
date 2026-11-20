"""Bounded compatibility checks; synthetic outputs are never benchmark results."""

import argparse
import hashlib
import json
import math
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from adaptive_rag.config import load_config
from adaptive_rag.evaluation.pricing import PriceSchedule, estimate_cost
from adaptive_rag.generation.answers import GroundedAnswerGenerator
from adaptive_rag.generation.client import OpenAIChatClient, OpenAIEmbeddingClient
from adaptive_rag.generation.models import GenerationSettings
from adaptive_rag.retrieval.agentic import AgenticRetriever
from adaptive_rag.retrieval.chunking import chunk_corpus
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.models import RetrievalBudget, RetrievalRequest
from adaptive_rag.routing import LLMRouter, RepositoryMetadata, RoutingRequest

args = argparse.ArgumentParser()
args.add_argument('--allow-api', action='store_true', required=True)
args.add_argument('--output', type=Path, required=True)
args.add_argument('--validated-embedding-report', type=Path)
args.add_argument('--validated-chat-report', type=Path)
args = args.parse_args()
ROOT = Path('/Users/shekhar/development/research/adaptive-rag')
config = load_config(ROOT / 'configs/adaptive.openrouter.local.yaml')
folder = args.output.resolve()
folder.mkdir(parents=True, exist_ok=False)
prices = PriceSchedule.model_validate_json((ROOT / config.experiment.price_schedule).read_text())
common = {'base_url': config.models.base_url,
          'api_key': os.environ.get(config.models.api_key_env)}
if not common['api_key']:
    raise ValueError('Configured API credential is absent; no requests made')
embedding = OpenAIEmbeddingClient(model=config.models.embedding_model, **common)
chat = OpenAIChatClient(model=config.models.chat_model, **common)
calls = []
results = {}


def save(name, payload):
    with (folder / name).open('x') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')


def record_calls(stage, records):
    calls.extend(records)
    for call in records:
        with (folder / 'model-calls.jsonl').open('a') as stream:
            stream.write(json.dumps({'stage': stage, 'call': call.model_dump(mode='json')}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
    cost = estimate_cost(calls, prices)
    if cost.estimated_usd is None or cost.estimated_usd > 0.05 or len(calls) > 8:
        raise ValueError('Smoke cost/accounting/call gate reached; further requests disabled')


def embed(stage, texts):
    try:
        response = embedding.embed(texts, timeout=60)
    except Exception as exc:
        record = getattr(exc, 'record', None)
        if record is not None:
            record_calls(stage, (record,))
        raise
    record_calls(stage, (response.call,))
    dimensions = {len(vector) for vector in response.vectors}
    assert len(response.vectors) == len(texts) and len(dimensions) == 1
    assert next(iter(dimensions)) > 0 and response.call.usage.total_tokens is not None
    assert all(all(math.isfinite(x) for x in vector) and any(vector) for vector in response.vectors)
    results[stage] = {'inputs': len(texts), 'dimensions': next(iter(dimensions)),
                      'usage': response.call.usage.model_dump(), 'elapsed_seconds': response.call.elapsed_seconds}


try:
    if args.validated_embedding_report:
        previous = json.loads(args.validated_embedding_report.read_text())
        for stage in ('synthetic_embedding', 'largest_corpus_embedding_batch'):
            item = previous['results'][stage]
            assert item['dimensions'] == 4096 and item['usage']['input_tokens'] is not None
            results[stage] = {**item, 'validated_by': str(args.validated_embedding_report),
                             'report_sha256': hashlib.sha256(args.validated_embedding_report.read_bytes()).hexdigest(),
                             'reexecuted': False}
    else:
        embed('synthetic_embedding', ['Synthetic compatibility input one.', 'Synthetic compatibility input two.'])
        corpus = RepositoryCorpus.from_repository(config.repository.path, config.repository.commit_sha, config.files)
        chunks = chunk_corpus(corpus, config.retrieval.chunking)
        batch_size = config.retrieval.embedding_batch_size
        batches = [chunks[i:i+batch_size] for i in range(0, len(chunks), batch_size)]
        largest = max(batches, key=lambda values: sum(len(item.text.encode()) for item in values))
        embed('largest_corpus_embedding_batch', [chunk.text for chunk in largest])
        assert results['synthetic_embedding']['dimensions'] == results['largest_corpus_embedding_batch']['dimensions']
    source = folder / 'synthetic-source'
    source.mkdir()
    (source / 'synthetic.py').write_text('class SyntheticWidget:\n    value = 7\n')
    def git(*values):
        return subprocess.run(['git', '-C', str(source), *values], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '--quiet', '--template=')
    git('remote', 'add', 'origin', 'https://fixture.invalid/provider-compatibility.git')
    git('add', '.')
    git('-c', 'user.name=Synthetic Compatibility Check', '-c', 'user.email=fixture@example.invalid',
        '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Synthetic compatibility source')
    synthetic = RepositoryCorpus.from_repository(source, git('rev-parse', 'HEAD'), config.files)
    if args.validated_chat_report:
        previous = json.loads(args.validated_chat_report.read_text())
        for stage in ('synthetic_router', 'synthetic_answer'):
            item = previous['results'][stage]
            assert item['status'] == 'completed'
            results[stage] = {**item, 'validated_by': str(args.validated_chat_report),
                             'report_sha256': hashlib.sha256(args.validated_chat_report.read_bytes()).hexdigest(),
                             'reexecuted': False}
    else:
        request = RoutingRequest(query='Where is SyntheticWidget defined in synthetic.py?',
                                 repository=RepositoryMetadata.from_corpus(synthetic),
                                 budget=config.routing.budget)
        route = LLMRouter(chat, max_output_tokens=256).route(request)
        record_calls('synthetic_router', route.model_calls)
        save('synthetic-router.json', route.model_dump(mode='json'))
        assert route.status == 'completed', route.errors
        results['synthetic_router'] = {'status': route.status, 'selected_strategy': route.selected_strategy}
    
        answer = GroundedAnswerGenerator(chat, settings=GenerationSettings(
            max_output_tokens=256, max_seconds=30, max_tokens=6000,
        )).generate('What is the value of SyntheticWidget.value?', (synthetic.evidence('synthetic.py', 1, 2),))
        record_calls('synthetic_answer', answer.model_calls)
        save('synthetic-answer.json', answer.model_dump(mode='json'))
        assert answer.status == 'completed' and answer.citations, answer.errors
        results['synthetic_answer'] = {'status': answer.status, 'citations': len(answer.citations)}
    navigation = AgenticRetriever(synthetic, chat, max_output_tokens=256).retrieve(RetrievalRequest(
        query='Use read_file to read synthetic.py lines 1-2, then call select_evidence with the returned evidence ID.',
        budget=RetrievalBudget(max_tool_calls=5, max_model_calls=4, max_tokens=16000, max_seconds=60),
    ))
    record_calls('synthetic_tool_navigation', navigation.model_calls)
    save('synthetic-navigation.json', navigation.model_dump(mode='json'))
    assert navigation.status == 'completed' and navigation.evidence and navigation.tool_call_count > 0, navigation.errors
    results['synthetic_tool_navigation'] = {'status': navigation.status,
        'tool_calls': navigation.tool_call_count, 'model_calls': len(navigation.model_calls)}
    status = 'passed'
except BaseException as exc:
    status = 'failed'
    results['error'] = {'type': type(exc).__name__, 'message': str(exc)}
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        save('summary.json', {'status': status, 'kind': 'compatibility_smoke_not_benchmark_results', 'results': results})
        raise
summary = {'status': status, 'kind': 'compatibility_smoke_not_benchmark_results',
           'recorded_at': datetime.now(UTC).isoformat(), 'results': results,
           'model_calls': len(calls), 'cost': estimate_cost(calls, prices).model_dump(mode='json')}
save('summary.json', summary)
print(json.dumps(summary, indent=2))
raise SystemExit(0 if status == 'passed' else 2)
