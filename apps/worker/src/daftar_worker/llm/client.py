"""An OpenAI-compatible client: flat JSON schemas, answers re-validated in code, and a cache."""

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from jsonschema import Draft202012Validator


TIMEOUT_SECONDS = 180
# The first call also loads the model, which took over 3 minutes from a cold disk on the RTX 4070.
FIRST_CALL_TIMEOUT_SECONDS = 600
VOTE_TEMPERATURE = 0.7
# Fixed, so the same input with the same model gives the same analysis (R-11).
VOTE_SEEDS = (11, 23, 37, 41, 53)
FIRST_VOTES = 3
REFUSED = {"__refused__": True}
Check = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    model: str
    quant: str | None = None
    cache_dir: Path | None = None
    # Off by default: in a real run the model turned "revient dans" into "redevient", which keeps
    # every fact and still says the wrong thing. The templates are already clear.
    reword: bool = False


def settings_from_env(env: Mapping[str, str] | None = None) -> LlmSettings | None:
    """None means rules only (R-11): C-10 says an empty base URL turns the model off."""
    source = os.environ if env is None else env
    base_url = (source.get("DAFTAR_LLM_BASE_URL") or "").rstrip("/")
    model = source.get("DAFTAR_LLM_MODEL") or ""
    if not base_url or not model:
        return None
    reword = source.get("DAFTAR_LLM_REWORD") == "1"
    return LlmSettings(base_url, model, cache_dir=Path.home() / ".cache" / "daftar" / "llm", reword=reword)


class ModelUnavailable(Exception):
    """The endpoint can't be reached, so the analysis stays rules-only."""


@dataclass
class Vote:
    answer: str
    agreement: float  # The share of votes for the winner.
    votes: int


@dataclass
class LlmStats:
    calls: int = 0
    cached: int = 0
    invalid: int = 0
    tasks: Counter[str] = field(default_factory=Counter)


class LlmClient:
    def __init__(self, settings: LlmSettings, prompt_version: str) -> None:
        self.settings = settings
        self.prompt_version = prompt_version
        self.stats = LlmStats()
        self._answered = False
        self.quant = settings.quant or self._read_quant()

    def _read_quant(self) -> str | None:
        """Ollama can say how a model is quantised. Other servers may not, and that's fine."""
        root = self.settings.base_url.removesuffix("/v1")
        request = urllib.request.Request(
            f"{root}/api/show",
            data=json.dumps({"model": self.settings.model}).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                details = json.load(response).get("details", {})
        except (OSError, ValueError):
            return None
        level = details.get("quantization_level")
        return str(level) if level else None

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.settings.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.stats.calls += 1
        try:
            timeout = TIMEOUT_SECONDS if self._answered else FIRST_CALL_TIMEOUT_SECONDS
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data: dict[str, Any] = json.load(response)
                self._answered = True
                return data
        except urllib.error.HTTPError as error:
            return {"error": error.code}
        except (OSError, ValueError) as error:
            raise ModelUnavailable(type(error).__name__) from error

    def _cache_path(self, key: str) -> Path | None:
        return self.settings.cache_dir / f"{key}.json" if self.settings.cache_dir else None

    def _key(self, parts: list[Any]) -> str:
        identity = [self.prompt_version, self.settings.model, self.quant, *parts]
        return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def ask(
        self,
        task: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        check: Check | None = None,
        temperature: float = 0.0,
        seed: int = 0,
    ) -> dict[str, Any] | None:
        """One answer, valid by schema and `check`. None after one retry: the rules' answer stands."""
        self.stats.tasks[task] += 1
        key = self._key([task, system, prompt, schema, temperature, seed])
        path = self._cache_path(key)
        if path is not None and path.exists():
            self.stats.cached += 1
            cached: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            return None if cached == REFUSED else cached
        body = {
            "model": self.settings.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": temperature,
            "seed": seed,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": task, "strict": True, "schema": schema},
            },
            # Qwen3.5 thinks by default. Each server has its own way to say no.
            "think": False,
            "reasoning_effort": "none",
            "chat_template_kwargs": {"enable_thinking": False},
        }
        validator = Draft202012Validator(schema)
        result: dict[str, Any] | None = None
        for _ in range(2):
            answer = _parse(self._post(body))
            if answer is not None and not list(validator.iter_errors(answer)) and (check is None or check(answer)):
                result = answer
                break
            self.stats.invalid += 1
        # A refused answer is cached too: the same input must give the same analysis (R-11), and a
        # rerun shouldn't ask again. An unreachable server raises before this, so it isn't cached.
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            stored = result if result is not None else REFUSED
            path.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        return result

    def vote(self, task: str, system: str, prompt: str, options: list[str]) -> Vote | None:
        """Self-consistency: ask several times, and let the agreement be the confidence.

        Starts with 3 votes, and goes to 5 only if they split. None if no option gets a majority of
        the valid answers, or if too few answers were valid.
        """
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["answer"],
            "properties": {"answer": {"type": "string", "enum": options}},
        }
        tally: Counter[str] = Counter()
        asked = 0
        for seed in VOTE_SEEDS:
            if asked >= FIRST_VOTES and tally and tally.most_common(1)[0][1] == asked:
                break
            answer = self.ask(task, system, prompt, schema, temperature=VOTE_TEMPERATURE, seed=seed)
            asked += 1
            if answer is not None:
                tally[answer["answer"]] += 1
        total = sum(tally.values())
        if total < FIRST_VOTES:
            return None
        ordered = sorted(tally.items(), key=lambda item: (-item[1], item[0]))
        winner, count = ordered[0]
        if count * 2 <= total:
            return None
        return Vote(winner, count / total, total)


def _parse(response: dict[str, Any]) -> dict[str, Any] | None:
    try:
        content = response["choices"][0]["message"]["content"]
        data = json.loads(content)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None
