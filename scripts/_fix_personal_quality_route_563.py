from __future__ import annotations

from pathlib import Path


path = Path("velvet_bot/domains/vision_routing/service.py")
source = path.read_text(encoding="utf-8")
old = '''def _cached_result(
    cached: CachedVisionAnalysis,
    *,
    mode: VisionAnalysisMode,
    prompt_version: int,
    schema_version: int,
) -> VisionCascadeResult:
    return VisionCascadeResult(
        profile=dict(cached.profile),
        content_hash=cached.content_hash,
        route=cached.route,
        provider=cached.provider,
        model=cached.model,
        confidence=cached.confidence,
        cache_hit=True,
        attempts=(),
        input_tokens=cached.input_tokens,
        output_tokens=cached.output_tokens,
        actual_cost_rub=cached.actual_cost_rub,
        metadata={
            "cache_id": cached.cache_id,
            "analysis_mode": mode.value,
            "schema_version": self.schema_version,
            "prompt_version": prompt_version,
        },
    )
'''
new = old.replace('"schema_version": self.schema_version', '"schema_version": schema_version')
if old not in source:
    raise SystemExit("Cached result schema metadata anchor was not found")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
