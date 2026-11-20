"""Explicit fresh-index recovery with verified reuse and conservative request pacing."""
import argparse,json,os,time
from collections import deque
from pathlib import Path
from adaptive_rag.config import load_config
from adaptive_rag.evaluation.pricing import PriceSchedule,estimate_cost
from adaptive_rag.generation.client import ModelCallNotStarted,OpenAIEmbeddingClient
from adaptive_rag.retrieval.corpus import RepositoryCorpus
from adaptive_rag.retrieval.vector import VectorRetriever

parser=argparse.ArgumentParser()
parser.add_argument('--allow-api',action='store_true',required=True)
args=parser.parse_args()
ROOT=Path('/Users/shekhar/development/research/adaptive-rag')
config=load_config(ROOT/'configs/adaptive.openrouter.local.yaml')
source=ROOT/'datasets/indexes/langchain-openrouter-qwen3-phase4-001'
target=ROOT/'datasets/indexes/langchain-openrouter-qwen3-phase4-002'
assert config.experiment.vector_index==target
prices=PriceSchedule.model_validate_json(config.experiment.price_schedule.read_text())
corpus=RepositoryCorpus.from_repository(config.repository.path,config.repository.commit_sha,config.files)
client=OpenAIEmbeddingClient(base_url=config.models.base_url,model=config.models.embedding_model,
    api_key=os.environ.get(config.models.api_key_env),dimensions=config.models.embedding_dimensions)

class PacedClient:
 def __init__(self):
  self.recent=deque()
  self.calls=0
  self.tokens=0
  self.pacing_seconds=0.0
 @property
 def identity(self):return client.identity
 def embed(self,texts,*,timeout):
  began=time.monotonic()
  estimate=sum(len(text.encode('utf-8')) for text in texts)
  # Planning throttle only; provider-reported usage remains authoritative.
  reserve=min(100000,estimate)
  while self.recent:
   now=time.monotonic()
   while self.recent and now-self.recent[0][0]>=61:self.recent.popleft()
   if not self.recent or sum(value for _,value in self.recent)+reserve<=100000:break
   pause=self.recent[0][0]+61-now
   if time.monotonic()-began+pause+1>=timeout:
    raise ModelCallNotStarted('Index pacing cannot admit a request before its deadline')
   print(json.dumps({'pacing_seconds':round(pause,2),'next_input_utf8_bytes':estimate}),flush=True)
   time.sleep(pause)
   self.pacing_seconds+=pause
  response=client.embed(texts,timeout=timeout-(time.monotonic()-began))
  tokens=response.call.usage.input_tokens
  self.recent.append((time.monotonic(),tokens or 0))
  self.calls+=1
  self.tokens+=tokens or 0
  print(json.dumps({'new_embedding_batches_received':self.calls,'new_provider_tokens':self.tokens}),flush=True)
  return response

progress=PacedClient()
retriever=VectorRetriever(corpus,progress,chunking=config.retrieval.chunking,
    batch_size=config.retrieval.embedding_batch_size)
try:
 result=retriever.build_index(target,budget=config.retrieval.indexing_budget,reuse_from=source)
except BaseException:
 print(json.dumps({'status':'failed_or_interrupted','index':str(target),
  'new_successful_batches':progress.calls,'source_retained':str(source)}),flush=True)
 raise
summary={'status':'completed','index':str(target),'chunks':result.chunk_count,
 'dimensions':result.dimensions,'successful_embedding_batches':len(result.model_calls),
 'successful_batch_usage':result.usage.model_dump(),'successful_batch_cost':estimate_cost(result.model_calls,prices).model_dump(mode='json'),
 'new_embedding_batches':progress.calls,'new_provider_input_tokens':progress.tokens,
 'pacing_seconds':progress.pacing_seconds,'elapsed_seconds':result.elapsed_seconds,
 'reuse_provenance':result.reuse_provenance,
 'complete_construction_cost_usd':None,
 'complete_construction_cost_reason':'Original construction includes an HTTP429 attempt with unknown provider usage; it is retained in reuse provenance.'}
with (target/'build-summary.json').open('x') as stream:stream.write(json.dumps(summary,indent=2)+'\n')
print(json.dumps({key:value for key,value in summary.items() if key!='reuse_provenance'},indent=2),flush=True)
