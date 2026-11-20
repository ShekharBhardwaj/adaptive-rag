"""Strict, inert YAML configuration with paths relative to the YAML file."""

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import Field, FiniteFloat, ValidationError

from adaptive_rag.evaluation.experiment_models import ExperimentSettings
from adaptive_rag.ingestion import DiscoveryPolicy
from adaptive_rag.models import CommitSHA, NonBlank, ResearchModel
from adaptive_rag.retrieval.chunking import ChunkingConfig
from adaptive_rag.retrieval.models import RetrievalBudget


class ConfigurationError(ValueError):
    pass


class RepositoryConfig(ResearchModel):
    url: NonBlank
    path: Path
    commit_sha: CommitSHA


class RequestPacingSettings(ResearchModel):
    min_interval_seconds: Annotated[FiniteFloat, Field(ge=0)] = 0.0
    max_requests_per_minute: Annotated[int, Field(strict=True, ge=1)] | None = None


class ModelSettings(ResearchModel):
    base_url: NonBlank
    api_key_env: NonBlank = "OPENAI_API_KEY"
    chat_base_url: NonBlank | None = None
    chat_api_key_env: NonBlank | None = None
    request_pacing: RequestPacingSettings = Field(default_factory=RequestPacingSettings)
    chat_request_pacing: RequestPacingSettings | None = None
    embedding_model: NonBlank | None = None
    chat_model: NonBlank | None = None
    embedding_dimensions: Annotated[int, Field(strict=True, ge=1)] | None = None
    temperature: FiniteFloat | None = 0.0
    max_output_tokens: Annotated[int, Field(strict=True, ge=1)] = 512
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class RetrievalSettings(ResearchModel):
    top_k: Annotated[int, Field(strict=True, ge=1, le=100)] = 5
    budget: RetrievalBudget = Field(default_factory=RetrievalBudget)
    indexing_budget: RetrievalBudget = Field(
        default_factory=lambda: RetrievalBudget(
            max_model_calls=1000,
            max_tokens=1_000_000,
            max_seconds=600,
        )
    )
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding_batch_size: Annotated[int, Field(strict=True, ge=1, le=256)] = 32


class RoutingSettings(ResearchModel):
    chat_model: NonBlank | None = None
    temperature: Annotated[FiniteFloat, Field(ge=0, le=2)] | None = 0.0
    max_output_tokens: Annotated[int, Field(strict=True, ge=1)] = 256
    budget: RetrievalBudget = Field(
        default_factory=lambda: RetrievalBudget(
            max_tool_calls=0, max_model_calls=1, max_tokens=4000, max_seconds=10
        )
    )


class FoundationConfig(ResearchModel):
    schema_version: Literal["1"] = "1"
    repository: RepositoryConfig
    files: DiscoveryPolicy = Field(default_factory=DiscoveryPolicy)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    models: ModelSettings | None = None
    experiment: ExperimentSettings | None = None


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently replacing experimental settings."""


def _unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            if key in result:
                raise ConfigurationError(f"duplicate YAML key: {key!r}")
            result[key] = loader.construct_object(value_node, deep=True)
        except TypeError as exc:
            raise ConfigurationError("YAML mapping keys must be scalar values") from exc
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_config(path: Path | str) -> FoundationConfig:
    config_path = Path(path).resolve()
    try:
        data = yaml.load(config_path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
        config = FoundationConfig.model_validate(data)
    except (OSError, UnicodeError, yaml.YAMLError, ValidationError, RecursionError) as exc:
        raise ConfigurationError(f"invalid configuration {config_path}: {exc}") from exc
    repository = config.repository.model_copy(
        update={"path": (config_path.parent / config.repository.path).resolve()}
    )
    updates = {"repository": repository}
    if config.experiment is not None:
        experiment_updates = {}
        for name in ("dataset", "vector_index", "price_schedule"):
            value = getattr(config.experiment, name)
            if value is not None:
                experiment_updates[name] = (config_path.parent / value).resolve()
        updates["experiment"] = config.experiment.model_copy(update=experiment_updates)
    return config.model_copy(update=updates)
