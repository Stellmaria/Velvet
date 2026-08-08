from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.benchmark_vision_gateway import (
    Sample,
    _benchmark_passed,
    _build_payload,
    _parse_memory_bytes,
    _parse_percent,
    _percentile,
    _request_json_via_container,
    _schema_valid,
    _summary,
)


class VisionGatewayBenchmarkContractTests(unittest.TestCase):
    def test_memory_and_cpu_stats_are_numeric(self) -> None:
        self.assertEqual(10 * 1024**3, _parse_memory_bytes("10GiB / 12GiB"))
        self.assertEqual(604.5, _parse_percent("604.5%"))

    def test_schema_contract_accepts_only_required_json_shape(self) -> None:
        valid = (
            '{"subjects":["person"],"composition":"centered",'
            '"lighting":"soft","palette":["blue"],"confidence":82}'
        )
        self.assertTrue(_schema_valid(valid))
        self.assertTrue(_schema_valid(f"```json\n{valid}\n```"))
        self.assertFalse(_schema_valid('{"subjects":[]}'))
        self.assertFalse(
            _schema_valid(
                '{"subjects":[],"composition":"x","lighting":"y",'
                '"palette":[],"confidence":101}'
            )
        )
        self.assertFalse(
            _schema_valid(
                '{"subjects":[1],"composition":"x","lighting":"y",'
                '"palette":[],"confidence":80}'
            )
        )
        self.assertFalse(
            _schema_valid(
                '{"subjects":[],"composition":"x","lighting":"y",'
                '"palette":[],"confidence":80,"extra":true}'
            )
        )

    def test_payload_applies_output_cap_and_structured_schema(self) -> None:
        payload = _build_payload(
            model="qwen3.5:9b",
            data_uri="data:image/png;base64,AA==",
            max_output_tokens=512,
        )
        self.assertEqual("qwen3.5:9b", payload["model"])
        self.assertEqual(512, payload["max_tokens"])
        self.assertFalse(payload["stream"])
        response_format = payload["response_format"]
        self.assertEqual("json_schema", response_format["type"])
        json_schema = response_format["json_schema"]
        self.assertTrue(json_schema["strict"])
        schema = json_schema["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {"subjects", "composition", "lighting", "palette", "confidence"},
            set(schema["required"]),
        )

    def test_container_http_status_is_preserved(self) -> None:
        completed = SimpleNamespace(
            returncode=3,
            stderr='HTTP 504: {"error":{"message":"Local VL runtime timed out."}}\n',
            stdout="",
        )
        with patch("scripts.benchmark_vision_gateway.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, r"^HTTP 504:"):
                _request_json_via_container(
                    "gateway-container",
                    "http://vision-gateway:8080/v1/chat/completions",
                    {"model": "qwen3.5:9b"},
                    360,
                )

    def test_percentile_interpolates_small_samples(self) -> None:
        self.assertEqual(2.5, _percentile([1.0, 2.0, 3.0, 4.0], 0.50))
        self.assertAlmostEqual(3.85, _percentile([1.0, 2.0, 3.0, 4.0], 0.95))

    def test_summary_reports_warm_percentiles_and_failure_rates(self) -> None:
        samples = [
            Sample(
                index=1,
                latency_seconds=100.0,
                response_chars=100,
                schema_valid=True,
                completion_tokens=100,
                tokens_per_second_estimate=1.0,
                peak_runtime_memory_bytes=10,
                peak_runtime_cpu_percent=500.0,
                peak_host_swap_used_bytes=1000,
            ),
            Sample(
                index=2,
                latency_seconds=50.0,
                response_chars=100,
                schema_valid=True,
                completion_tokens=100,
                tokens_per_second_estimate=2.0,
                peak_runtime_memory_bytes=20,
                peak_runtime_cpu_percent=600.0,
                peak_host_swap_used_bytes=2000,
            ),
            Sample(
                index=3,
                latency_seconds=None,
                response_chars=0,
                schema_valid=False,
                peak_runtime_memory_bytes=15,
                peak_runtime_cpu_percent=550.0,
                peak_host_swap_used_bytes=1500,
                error="timeout",
            ),
        ]
        result = _summary(samples)
        self.assertEqual(100.0, result["cold_latency_seconds"])
        self.assertEqual(50.0, result["warm_p50_seconds"])
        self.assertEqual(50.0, result["warm_p95_seconds"])
        self.assertEqual(0.6667, result["success_rate"])
        self.assertEqual(0.3333, result["failure_rate"])
        self.assertEqual(1.0, result["schema_validity_rate"])
        self.assertEqual(20, result["peak_runtime_memory_bytes"])
        self.assertEqual(600.0, result["peak_runtime_cpu_percent"])
        self.assertEqual(2000, result["peak_host_swap_used_bytes"])

    def test_benchmark_pass_requires_transport_and_schema_success(self) -> None:
        self.assertTrue(
            _benchmark_passed(
                {
                    "success_rate": 1.0,
                    "failure_rate": 0.0,
                    "schema_validity_rate": 1.0,
                }
            )
        )
        self.assertFalse(
            _benchmark_passed(
                {
                    "success_rate": 1.0,
                    "failure_rate": 0.0,
                    "schema_validity_rate": 0.0,
                }
            )
        )
        self.assertFalse(
            _benchmark_passed(
                {
                    "success_rate": 0.0,
                    "failure_rate": 1.0,
                    "schema_validity_rate": 0.0,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
