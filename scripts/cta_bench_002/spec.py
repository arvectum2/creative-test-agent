"""CTA-BENCH-002 shared constants and candidate/topology registry."""

from __future__ import annotations

BENCHMARK_ID = "cta-bench-002-target-hardware-llm-vlm-ocr"
BENCHMARK_VERSION = "1.0.0"

ARTIFACT_ROOT = "artifacts/cta-bench-002"

# Ports are reserved per runtime so that different server families never
# collide during a benchmark run. All endpoints bind to loopback only.
LOOPBACK = "127.0.0.1"
PORT_VLM_BASE_LLAMA = 8083
PORT_VLM_MLX_8B = 8089
PORT_VLM_MLX_4B = 8091
PORT_LLM_MLX_9B = 8092
PORT_LLM_MLX_4B = 8093

# Candidates that are pure in-process analyzers (no external server).
IN_PROCESS_CANDIDATES = {
    "OCR-TESSERACT",
    "OCR-CHALLENGER",
    "LLM-CURRENT",
}

SINGLE_REQUEST_CANDIDATES = [
    "OCR-TESSERACT",
    "OCR-CHALLENGER",
    "VLM-BASE-LLAMA",
    "VLM-MLX-8B",
    "VLM-MLX-4B",
    "LLM-CURRENT",
    "LLM-MLX-9B",
    "LLM-MLX-4B",
]

HYBRID_VLM_CANDIDATES = ["VLM-BASE-LLAMA", "VLM-MLX-8B", "VLM-MLX-4B"]

TOPOLOGIES = ["TOPOLOGY-U", "TOPOLOGY-S", "TOPOLOGY-R"]

# Residency requirements for TOPOLOGY-R. Measured headroom must be >= this
# fraction of total unified memory on a representative run.
TOPOLOGY_R_MIN_HEADROOM_FRACTION = 0.20

DEFAULT_TIMEOUT_SECONDS = 240
DEFAULT_CONCURRENCY = 2
DEFAULT_REPEATS = 3
WARMUP_CASE_COUNT = 1


def candidate_catalog() -> list[dict]:
    return [
        {
            "candidate_id": "OCR-TESSERACT",
            "candidate_type": "ocr",
            "engine": "tesseract",
            "runtime": "in-process",
            "model": "tesseract-5.5.3",
            "requires_server": False,
            "baseline": True,
        },
        {
            "candidate_id": "OCR-CHALLENGER",
            "candidate_type": "ocr",
            "engine": "paddleocr",
            "runtime": "in-process",
            "model": "PP-OCRv5-mobile",
            "requires_server": False,
        },
        {
            "candidate_id": "VLM-BASE-LLAMA",
            "candidate_type": "vlm",
            "engine": "llama.cpp",
            "runtime": "llama-server",
            "model": "Qwen2.5-VL-7B-Instruct-Q4_K_M",
            "requires_server": True,
            "port": PORT_VLM_BASE_LLAMA,
            "api": "openai_compatible",
            "baseline": True,
        },
        {
            "candidate_id": "VLM-MLX-8B",
            "candidate_type": "vlm",
            "engine": "mlx-vlm",
            "runtime": "mlx-vlm.server",
            "model": "mlx-community/Qwen3-VL-8B-Instruct-4bit",
            "requires_server": True,
            "port": PORT_VLM_MLX_8B,
            "api": "openai_compatible",
            "baseline": False,
        },
        {
            "candidate_id": "VLM-MLX-4B",
            "candidate_type": "vlm",
            "engine": "mlx-vlm",
            "runtime": "mlx-vlm.server",
            "model": "mlx-community/Qwen3-VL-4B-Instruct-4bit",
            "requires_server": True,
            "port": PORT_VLM_MLX_4B,
            "api": "openai_compatible",
            "baseline": False,
        },
        {
            "candidate_id": "LLM-CURRENT",
            "candidate_type": "llm",
            "engine": "app-profile",
            "runtime": "application-profile",
            "model": "profile:current",
            "requires_server": False,
            "api": "app-provider",
            "baseline": True,
        },
        {
            "candidate_id": "LLM-MLX-9B",
            "candidate_type": "llm",
            "engine": "mlx",
            "runtime": "mlx-openai-server",
            "model": "mlx-community/Qwen3.5-9B-MLX-4bit",
            "requires_server": True,
            "port": PORT_LLM_MLX_9B,
            "api": "openai_compatible",
            "baseline": False,
        },
        {
            "candidate_id": "LLM-MLX-4B",
            "candidate_type": "llm",
            "engine": "mlx",
            "runtime": "mlx-openai-server",
            "model": "mlx-community/Qwen3.5-4B-MLX-4bit",
            "requires_server": True,
            "port": PORT_LLM_MLX_4B,
            "api": "openai_compatible",
            "baseline": False,
        },
    ]
