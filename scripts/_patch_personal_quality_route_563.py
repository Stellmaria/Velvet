from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"Anchor not found in {relative}: {old[:120]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


def regex_once(relative: str, pattern: str, replacement: str) -> None:
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")
    source, count = re.subn(pattern, replacement, source, count=1, flags=re.DOTALL)
    if count != 1:
        raise SystemExit(f"Pattern not found in {relative}: {pattern[:120]!r}")
    path.write_text(source, encoding="utf-8")


# Generic structured analysis contract.
replace_once(
    "velvet_bot/domains/vision_routing/models.py",
    "from dataclasses import dataclass, field\nfrom decimal import Decimal\nfrom enum import StrEnum\nfrom typing import Mapping\n",
    "from collections.abc import Callable\nfrom dataclasses import dataclass, field\nfrom decimal import Decimal\nfrom enum import StrEnum\nfrom typing import Mapping\n",
)
replace_once(
    "velvet_bot/domains/vision_routing/models.py",
    "class VisionAnalysisMode(StrEnum):\n    STANDARD = \"standard\"\n    SENSITIVE = \"sensitive\"\n\n\n@dataclass(frozen=True, slots=True)\nclass VisionRouteConfig:",
    "class VisionAnalysisMode(StrEnum):\n    STANDARD = \"standard\"\n    SENSITIVE = \"sensitive\"\n\n\n@dataclass(frozen=True, slots=True)\nclass VisionAnalysisContract:\n    name: str\n    prompt: str\n    schema: Mapping[str, object]\n    normalize: Callable[[object], Mapping[str, object]]\n    max_output_tokens: int = 1800\n    schema_version: int = 1\n    ollama_json_fallback: bool = False\n\n    def __post_init__(self) -> None:\n        safe_name = self.name.strip()\n        if not safe_name or any(\n            not (character.isascii() and (character.isalnum() or character in {\"_\", \"-\"}))\n            for character in safe_name\n        ):\n            raise ValueError(\"Vision contract name должен быть безопасным ASCII identifier.\")\n        if not self.prompt.strip():\n            raise ValueError(\"Vision contract prompt не может быть пустым.\")\n        if not self.schema:\n            raise ValueError(\"Vision contract schema не может быть пустой.\")\n        if self.max_output_tokens < 1:\n            raise ValueError(\"Vision contract max_output_tokens должен быть положительным.\")\n        if self.schema_version < 1:\n            raise ValueError(\"Vision contract schema_version должен быть положительным.\")\n\n\n@dataclass(frozen=True, slots=True)\nclass VisionRouteConfig:",
)
replace_once(
    "velvet_bot/domains/vision_routing/models.py",
    "    \"VisionAnalysisMode\",\n    \"VisionCascadeResult\",",
    "    \"VisionAnalysisContract\",\n    \"VisionAnalysisMode\",\n    \"VisionCascadeResult\",",
)

# Metered provider client accepts semantic or quality structured contracts.
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "    VisionAnalysisMode,\n    VisionProviderAnalysis,",
    "    VisionAnalysisContract,\n    VisionAnalysisMode,\n    VisionProviderAnalysis,",
)
regex_once(
    "velvet_bot/domains/vision_routing/client.py",
    r"    def __init__\(\n        self,\n        \*,\n        config: VisionRouteConfig,\n        executor: AIRequestExecutor\[VisionProviderAnalysis\],\n    \) -> None:\n.*?        self\._executor = executor\n",
    '''    def __init__(
        self,
        *,
        config: VisionRouteConfig,
        executor: AIRequestExecutor[VisionProviderAnalysis],
        contract: VisionAnalysisContract | None = None,
    ) -> None:
        super().__init__(
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        self.route = config.route
        self.mode = (
            VisionAnalysisMode.SENSITIVE
            if config.route is VisionRoute.SENSITIVE
            else VisionAnalysisMode.STANDARD
        )
        self.prompt_version = config.prompt_version
        self.schema_version = config.schema_version
        self.max_attempts = max(1, int(config.max_attempts))
        self._pricing = config.pricing
        self._executor = executor
        self._contract = contract or VisionAnalysisContract(
            name=f"semantic_{self.mode.value}",
            prompt=prompt_for_mode(self.mode),
            schema=schema_for_mode(self.mode),
            normalize=lambda payload: normalize_routed_profile(
                payload,
                mode=self.mode,
                prompt_version=self.prompt_version,
            ),
            max_output_tokens=_MAX_OUTPUT_TOKENS,
            schema_version=self.schema_version,
        )
        if self._contract.schema_version != self.schema_version:
            raise ValueError(
                "Vision route schema_version должен совпадать с analysis contract."
            )
''',
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "        prompt = prompt_for_mode(self.mode)\n        schema = schema_for_mode(self.mode)\n",
    "        prompt = self._contract.prompt\n        schema = self._contract.schema\n        max_output_tokens = self._contract.max_output_tokens\n",
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "            \"schema_version\": self.schema_version,\n            \"prompt_version\": self.prompt_version,\n            \"prepared_bytes\": len(prepared),\n            \"max_output_tokens\": _MAX_OUTPUT_TOKENS,",
    "            \"schema_version\": self.schema_version,\n            \"prompt_version\": self.prompt_version,\n            \"analysis_contract\": self._contract.name,\n            \"prepared_bytes\": len(prepared),\n            \"max_output_tokens\": max_output_tokens,",
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "                output_tokens=_MAX_OUTPUT_TOKENS,\n",
    "                output_tokens=max_output_tokens,\n",
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "                    \"schema_version\": self.schema_version,\n                    \"prompt_version\": self.prompt_version,\n                    \"provider_reported_usage\": analysis.usage_reported,",
    "                    \"schema_version\": self.schema_version,\n                    \"prompt_version\": self.prompt_version,\n                    \"analysis_contract\": self._contract.name,\n                    \"provider_reported_usage\": analysis.usage_reported,",
)
regex_once(
    "velvet_bot/domains/vision_routing/client.py",
    r"    def _request_once\(self, prepared: bytes\) -> VisionProviderAnalysis:\n.*?\n    def _endpoint\(self\) -> str:",
    '''    def _request_once(self, prepared: bytes) -> VisionProviderAnalysis:
        image_base64 = base64.b64encode(prepared).decode("ascii")
        schema_modes = (
            (True, False)
            if self.provider == "ollama" and self._contract.ollama_json_fallback
            else (True,)
        )
        errors: list[str] = []
        for use_schema in schema_modes:
            request = urllib.request.Request(
                self._endpoint(),
                data=json.dumps(
                    self._request_body(image_base64, use_schema=use_schema),
                    ensure_ascii=False,
                ).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            payload = self._read_json(request, timeout=self.timeout_seconds)
            provider_error = payload.get("error")
            if provider_error:
                raise VisionAnalysisError(
                    f"{self.provider}:{self.model}: {provider_error}"
                )
            try:
                profile = self._normalize_payload(payload)
            except VisionAnalysisError as error:
                errors.append(str(error))
                if use_schema and len(schema_modes) > 1:
                    continue
                raise
            input_tokens, output_tokens, usage_reported = _extract_usage(
                payload,
                provider=self.provider,
            )
            return VisionProviderAnalysis(
                profile=profile,
                provider=self.provider,
                model=self.model,
                route=self.route,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage_reported=usage_reported,
            )
        raise VisionAnalysisError(
            f"{self.provider}:{self.model} не вернул {self._contract.name}: "
            + " | ".join(errors)
        )

    def _normalize_payload(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        if self.provider == "ollama":
            message = payload.get("message")
            message = message if isinstance(message, dict) else {}
            candidates = (
                message.get("content"),
                message.get("thinking"),
                payload.get("response"),
            )
            errors: list[str] = []
            for value in candidates:
                text = str(value or "").strip()
                if not text:
                    continue
                try:
                    return dict(self._contract.normalize(_extract_json_object(text)))
                except VisionAnalysisError as error:
                    errors.append(str(error))
            raise VisionAnalysisError(
                "Ollama не вернула структурированный ответ"
                + (": " + "; ".join(errors) if errors else ".")
            )
        content = _extract_provider_content(payload, provider=self.provider)
        return dict(self._contract.normalize(_extract_json_object(content)))

    def _endpoint(self) -> str:''',
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "    def _request_body(self, image_base64: str) -> dict[str, object]:\n        prompt = prompt_for_mode(self.mode)\n        schema = schema_for_mode(self.mode)\n",
    "    def _request_body(\n        self,\n        image_base64: str,\n        *,\n        use_schema: bool = True,\n    ) -> dict[str, object]:\n        prompt = self._contract.prompt\n        schema = self._contract.schema\n",
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "                \"format\": schema,",
    "                \"format\": schema if use_schema else \"json\",",
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "                    \"name\": f\"velvet_vision_{self.mode.value}\",",
    "                    \"name\": f\"velvet_{self._contract.name}_{self.route.value}\",",
)
replace_once(
    "velvet_bot/domains/vision_routing/client.py",
    "            \"max_tokens\": _MAX_OUTPUT_TOKENS,",
    "            \"max_tokens\": self._contract.max_output_tokens,",
)

# Router cache metadata uses the active contract schema version.
replace_once(
    "velvet_bot/domains/vision_routing/service.py",
    "        analysis_type: str = \"semantic-profile\",\n    ) -> None:",
    "        analysis_type: str = \"semantic-profile\",\n        schema_version: int = PROFILE_SCHEMA_VERSION,\n    ) -> None:",
)
replace_once(
    "velvet_bot/domains/vision_routing/service.py",
    "        self.analysis_type = analysis_type.strip()\n        if not self.analysis_type:",
    "        self.analysis_type = analysis_type.strip()\n        self.schema_version = max(1, int(schema_version))\n        if not self.analysis_type:",
)
replace_once(
    "velvet_bot/domains/vision_routing/service.py",
    "                prompt_version=self.prompt_version,\n            )",
    "                prompt_version=self.prompt_version,\n                schema_version=self.schema_version,\n            )",
)
source_path = ROOT / "velvet_bot/domains/vision_routing/service.py"
source = source_path.read_text(encoding="utf-8")
source = source.replace('"schema_version": PROFILE_SCHEMA_VERSION,', '"schema_version": self.schema_version,')
source = source.replace(
    'return f"{self.analysis_type}:schema-{PROFILE_SCHEMA_VERSION}:{mode.value}"',
    'return f"{self.analysis_type}:schema-{self.schema_version}:{mode.value}"',
)
source = source.replace(
    "    prompt_version: int,\n) -> VisionCascadeResult:",
    "    prompt_version: int,\n    schema_version: int,\n) -> VisionCascadeResult:",
)
source = source.replace(
    '            "schema_version": PROFILE_SCHEMA_VERSION,\n            "prompt_version": prompt_version,',
    '            "schema_version": schema_version,\n            "prompt_version": prompt_version,',
)
source_path.write_text(source, encoding="utf-8")

# Factory can build multiple structured routes over the same adapters/ledger/cache.
replace_once(
    "velvet_bot/domains/vision_routing/factory.py",
    "from velvet_bot.domains.vision_routing.models import VisionRoute, VisionRouteConfig\n",
    "from velvet_bot.domains.vision_routing.models import (\n    VisionAnalysisContract,\n    VisionRoute,\n    VisionRouteConfig,\n)\n",
)
replace_once(
    "velvet_bot/domains/vision_routing/factory.py",
    "    ai_usage_service: AIUsageService,\n) -> VisionCascadeRouter:\n",
    "    ai_usage_service: AIUsageService,\n    contract: VisionAnalysisContract | None = None,\n    analysis_type: str = \"semantic-profile\",\n    prompt_version: int | None = None,\n    include_sensitive: bool = True,\n) -> VisionCascadeRouter:\n",
)
replace_once(
    "velvet_bot/domains/vision_routing/factory.py",
    "    prompt_version = _bounded_int(\n        os.getenv(\"AI_VISION_PROMPT_VERSION\", \"1\"),\n        default=1,\n        minimum=1,\n        maximum=1_000_000,\n    )\n",
    "    resolved_prompt_version = (\n        max(1, int(prompt_version))\n        if prompt_version is not None\n        else _bounded_int(\n            os.getenv(\"AI_VISION_PROMPT_VERSION\", \"1\"),\n            default=1,\n            minimum=1,\n            maximum=1_000_000,\n        )\n    )\n    schema_version = contract.schema_version if contract is not None else PROFILE_SCHEMA_VERSION\n",
)
source_path = ROOT / "velvet_bot/domains/vision_routing/factory.py"
source = source_path.read_text(encoding="utf-8")
source = source.replace("prompt_version=prompt_version,", "prompt_version=resolved_prompt_version,")
source = source.replace(
    "    flash = MeteredVisionClient(config=flash_config, executor=executor)\n",
    "    flash = MeteredVisionClient(\n        config=flash_config, executor=executor, contract=contract\n    )\n",
)
source = source.replace(
    "            executor=executor,\n        )",
    "            executor=executor,\n            contract=contract,\n        )",
    2,
)
source = source.replace(
    "        if sensitive_model\n        else None\n    )",
    "        if include_sensitive and sensitive_model\n        else None\n    )",
)
source = source.replace(
    "        prompt_version=prompt_version,\n        analysis_type=\"semantic-profile\",\n",
    "        prompt_version=resolved_prompt_version,\n        analysis_type=analysis_type,\n        schema_version=schema_version,\n",
)
source = source.replace(
    "    prompt_version: int = 1,\n) -> VisionRouteConfig:",
    "    prompt_version: int = 1,\n    schema_version: int = PROFILE_SCHEMA_VERSION,\n) -> VisionRouteConfig:",
)
source = source.replace(
    "        schema_version=PROFILE_SCHEMA_VERSION,\n",
    "        schema_version=schema_version,\n",
)
# Every route config receives the selected schema version.
source = source.replace(
    "        prompt_version=resolved_prompt_version,\n    )",
    "        prompt_version=resolved_prompt_version,\n        schema_version=schema_version,\n    )",
)
source_path.write_text(source, encoding="utf-8")

# Quality contract remains the canonical prompt/schema/normalizer for system and personal use.
replace_once(
    "velvet_bot/ai_quality.py",
    "from velvet_bot.database import Database\n",
    "from velvet_bot.database import Database\nfrom velvet_bot.domains.vision_routing.models import VisionAnalysisContract\n",
)
replace_once(
    "velvet_bot/ai_quality.py",
    "\n\n@dataclass(frozen=True, slots=True)\nclass AIQualitySummary:",
    "\n\ndef build_quality_vision_contract() -> VisionAnalysisContract:\n    return VisionAnalysisContract(\n        name=\"personal_quality\",\n        prompt=_QUALITY_PROMPT,\n        schema=_QUALITY_SCHEMA,\n        normalize=normalize_quality_report,\n        max_output_tokens=1700,\n        schema_version=_ANALYSIS_VERSION,\n        ollama_json_fallback=True,\n    )\n\n\n@dataclass(frozen=True, slots=True)\nclass AIQualitySummary:",
)
replace_once(
    "velvet_bot/ai_quality.py",
    "    \"QualityVisionClient\",\n    \"normalize_quality_report\",",
    "    \"QualityVisionClient\",\n    \"build_quality_vision_contract\",\n    \"normalize_quality_report\",",
)

# Personal quality consumes the shared cascade and records the actual selected route.
replace_once(
    "velvet_bot/services/workspace_qwen_quality.py",
    "from velvet_bot.ai_quality import QualityVisionClient\n",
    "",
)
replace_once(
    "velvet_bot/services/workspace_qwen_quality.py",
    "from velvet_bot.domains.workspaces.qwen_repository import (\n",
    "from velvet_bot.domains.vision_routing.service import VisionCascadeRouter\nfrom velvet_bot.domains.workspaces.qwen_repository import (\n",
)
replace_once(
    "velvet_bot/services/workspace_qwen_quality.py",
    "        client: QualityVisionClient,",
    "        client: VisionCascadeRouter,",
)
replace_once(
    "velvet_bot/services/workspace_qwen_quality.py",
    "                \"Workspace Qwen service is unavailable provider=%s base_url=%s model=%s\",\n                self._client.provider,\n                self._client.base_url,\n                self._client.model,",
    "                \"Workspace personal quality route is unavailable provider=%s models=%s\",\n                self._client.provider,\n                self._client.configured_models,",
)
replace_once(
    "velvet_bot/services/workspace_qwen_quality.py",
    "            raw_report = await self._client.analyze(source)\n            profile = await self._repository.calibration_profile(\n                workspace_id=target.workspace_id,\n                provider=self._client.provider,\n                model=self._client.model,\n            )",
    "            routed = await self._client.analyze(\n                source,\n                metadata={\n                    \"surface\": \"personal-quality\",\n                    \"workspace_id\": target.workspace_id,\n                    \"media_id\": target.media_id,\n                },\n            )\n            raw_report = dict(routed.profile)\n            profile = await self._repository.calibration_profile(\n                workspace_id=target.workspace_id,\n                provider=routed.provider,\n                model=routed.model,\n            )",
)
replace_once(
    "velvet_bot/services/workspace_qwen_quality.py",
    "                report=report,\n            )\n            logger.info(\n                \"Workspace Qwen report ready workspace_id=%s media_id=%s verdict=%s score=%s\",\n                target.workspace_id,\n                target.media_id,\n                report.get(\"verdict\"),\n                report.get(\"quality_score\"),\n            )",
    "                provider=routed.provider,\n                model=routed.model,\n                report=report,\n            )\n            logger.info(\n                \"Workspace personal quality report ready workspace_id=%s media_id=%s \"\n                \"provider=%s model=%s route=%s cache_hit=%s verdict=%s score=%s\",\n                target.workspace_id,\n                target.media_id,\n                routed.provider,\n                routed.model,\n                routed.route.value,\n                routed.cache_hit,\n                report.get(\"verdict\"),\n                report.get(\"quality_score\"),\n            )",
)

# Repository refuses substituted workspace/media pairs and persists actual route identity.
replace_once(
    "velvet_bot/domains/workspaces/qwen_repository.py",
    "        media_id: int,\n        report: dict[str, Any],\n    ) -> None:",
    "        media_id: int,\n        provider: str,\n        model: str,\n        report: dict[str, Any],\n    ) -> None:",
)
regex_once(
    "velvet_bot/domains/workspaces/qwen_repository.py",
    r"                await connection\.execute\(\n                    \"\"\"\n                    UPDATE workspace_qwen_checks\n                    SET status = 'ready',.*?                    encoded,\n                \)\n                changed = await connection\.fetchval\(",
    '''                ready_media_id = await connection.fetchval(
                    """
                    UPDATE workspace_qwen_checks
                    SET status = 'ready',
                        provider = $3::VARCHAR,
                        model = $4::VARCHAR,
                        verdict = $5::VARCHAR,
                        quality_score = $6::SMALLINT,
                        confidence = $7::SMALLINT,
                        report = $8::JSONB,
                        error_message = NULL,
                        analyzed_at = NOW(),
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                      AND media_id = $2::BIGINT
                    RETURNING media_id
                    """,
                    int(workspace_id),
                    int(media_id),
                    provider[:64],
                    model[:160],
                    str(report["verdict"]),
                    int(report["quality_score"]),
                    int(report["confidence"]),
                    encoded,
                )
                if ready_media_id is None:
                    raise ValueError(
                        "Проверка качества не найдена в выбранном личном пространстве."
                    )
                changed = await connection.fetchval(''',
)

# Composition builds a second contract-specific router over the same usage service.
replace_once(
    "velvet_bot/app/workers.py",
    "from velvet_bot.ai_quality import QualityVisionClient\n",
    "from velvet_bot.ai_quality import (\n    QualityVisionClient,\n    build_quality_vision_contract,\n)\n",
)
replace_once(
    "velvet_bot/app/workers.py",
    "        workspace_quality_service = WorkspaceQwenQualityService(\n            bot=bot,\n            repository=WorkspaceQwenRepository(database),\n            client=QualityVisionClient(\n                provider=settings.ai_vision_provider,\n                base_url=settings.ai_vision_base_url,\n                model=settings.ai_vision_model,\n                api_key=settings.ai_vision_api_key,\n                timeout_seconds=settings.ai_vision_timeout_seconds,\n            ),\n            max_attempts=settings.ai_vision_max_attempts,\n        )",
    "        workspace_quality_router = build_vision_cascade_router(\n            settings=settings,\n            database=database,\n            ai_usage_service=active_usage_service,\n            contract=build_quality_vision_contract(),\n            analysis_type=\"personal-quality\",\n            prompt_version=1,\n            include_sensitive=False,\n        )\n        workspace_quality_service = WorkspaceQwenQualityService(\n            bot=bot,\n            repository=WorkspaceQwenRepository(database),\n            client=workspace_quality_router,\n            max_attempts=settings.ai_vision_max_attempts,\n        )",
)
replace_once(
    "velvet_bot/app/workers.py",
    "                description=\"Qwen-проверка личных пространств\",",
    "                description=\"Provider-neutral проверка личных пространств\",",
)

print("personal quality route patch applied")
