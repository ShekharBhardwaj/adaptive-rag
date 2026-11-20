"""Build the shared real index once; provider calls are journaled by the framework."""

import argparse
import json
import os
from pathlib import Path

from adaptive_rag.config import load_config
from adaptive_rag.evaluation.pricing import PriceSchedule, estimate_cost
from adaptive_rag.generation.client import OpenAIEmbeddingClient
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.vector import VectorRetriever

parser = argparse.ArgumentParser()
parser.add_argument('--allow-api', action='store_true', required=True)
args = parser.parse_args()
ROOT = Path('/Users/shekhar/development/research/adaptive-rag')
config = load_config(ROOT / 'configs/adaptive.openrouter.local.yaml')
compatibility = json.loads((ROOT / 'experiments/preflight/phase4-2026-11-16/live-compatibility-008/summary.json').read_text())
assert compatibility['status'] == 'passed', 'Full index requires successful compatibility gate'
prices = PriceSchedule.model_validate_json(config.experiment.price_schedule.read_text())
corpus = RepositoryCorpus.from_repository(config.repository.path, config.repository.commit_sha, config.files)
client = OpenAIEmbeddingClient(base_url=config.models.base_url, model=config.models.embedding_model,
    api_key=os.environ.get(config.models.api_key_env), dimensions=config.models.embedding_dimensions)


class ProgressClient:
    def __init__(self):
        self.calls = 0
        self.tokens = 0

    @property
    def identity(self):
        return client.identity

    def embed(self, texts, *, timeout):
        response = client.embed(texts, timeout=timeout)
        self.calls += 1
        self.tokens += response.call.usage.total_tokens or 0
        if self.calls == 1 or self.calls % 10 == 0:
            print(json.dumps({'embedding_batches_received': self.calls,
                              'provider_tokens_so_far': self.tokens}), flush=True)
        return response


progress = ProgressClient()
retriever = VectorRetriever(corpus, progress, chunking=config.retrieval.chunking,
                           batch_size=config.retrieval.embedding_batch_size)
try:
    result = retriever.build_index(config.experiment.vector_index, budget=config.retrieval.indexing_budget)
except BaseException:
    print(json.dumps({'status': 'failed_or_interrupted', 'index': str(config.experiment.vector_index),
                      'successful_embedding_batches': progress.calls,
                      'failure_and_events_retained': True}), flush=True)
    raise
summary = {'status': 'completed', 'index': str(config.experiment.vector_index),
           'chunks': result.chunk_count, 'embedding_batches': len(result.model_calls),
           'dimensions': result.dimensions, 'usage': result.usage.model_dump(),
           'elapsed_seconds': result.elapsed_seconds,
           'cost': estimate_cost(result.model_calls, prices).model_dump(mode='json')}
with (config.experiment.vector_index / 'build-summary.json').open('x') as stream:
    stream.write(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2), flush=True)
