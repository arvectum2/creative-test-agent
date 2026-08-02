"""Metrics collection, scoring and artifact generation for CTA-BENCH-002.

Captures wall time, TTFT, output tokens, resource samples (CPU, RSS, memory
pressure, swap), process cleanup audits, and produces the CSV/XLSX/MD/JSONL
artifacts described in the CTA-BENCH-002 task.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.shared.llm.stage_processor import process_stage_output
from src.shared.xlsx.simple_writer import SheetSpec, write_xlsx

from scripts.cta_bench_002.spec import BENCHMARK_ID, BENCHMARK_VERSION

TOKEN_PATTERN = r"[\w%]+"


def normalize_tokens(text: str) -> list[str]:
    import re

    pattern = re.compile(TOKEN_PATTERN, flags=re.UNICODE)
    return [
        token.strip("_")
        for token in pattern.findall(text.casefold())
        if token.strip("_")
    ]


def char_error_rate(expected: str, detected: str) -> dict[str, Any]:
    exp = expected.casefold().strip()
    det = detected.casefold().strip()
    if not exp and not det:
        return {"cer": 0.0, "exact": True, "expected_len": 0, "detected_len": 0}
    distance = _levenshtein(exp, det)
    return {
        "cer": distance / max(len(exp), 1),
        "exact": exp == det,
        "expected_len": len(exp),
        "detected_len": len(det),
    }


def word_error_rate(expected: str, detected: str) -> dict[str, Any]:
    exp = normalize_tokens(expected)
    det = normalize_tokens(detected)
    if not exp and not det:
        return {"wer": 0.0, "exact": True, "expected_words": 0, "detected_words": 0}
    distance = _levenshtein(" ".join(exp), " ".join(det))
    words = len(exp)
    return {
        "wer": distance / max(words, 1),
        "exact": exp == det,
        "expected_words": words,
        "detected_words": len(det),
    }


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (left_char != right_char)
            current.append(min(insert, delete, substitute))
        previous = current
    return previous[-1]


def score_text(expected_text: str, detected_text: str) -> dict[str, Any]:
    from collections import Counter

    if isinstance(expected_text, list):
        expected_text = " ".join(str(p) for p in expected_text)
    if isinstance(detected_text, list):
        detected_text = " ".join(str(p) for p in detected_text)
    expected = Counter(normalize_tokens(expected_text))
    detected = Counter(normalize_tokens(detected_text))
    overlap = sum((expected & detected).values())
    expected_count = sum(expected.values())
    detected_count = sum(detected.values())
    precision = overlap / detected_count if detected_count else 0.0
    recall = overlap / expected_count if expected_count else 1.0
    return {
        "expected_token_count": expected_count,
        "detected_token_count": detected_count,
        "matched_token_count": overlap,
        "precision": precision,
        "recall": recall,
        "f1": harmonic_mean(precision, recall),
        "abstained": detected_count == 0,
    }


def score_observations(
    expected: dict[str, str], predicted: dict[str, str]
) -> dict[str, Any]:
    total = len(expected)
    answered = 0
    correct = 0
    confusion: dict[str, int] = defaultdict(int)
    for observable, gold in sorted(expected.items()):
        guess = predicted.get(observable, "uncertain")
        abstained = guess == "uncertain"
        if not abstained:
            answered += 1
        if guess == gold:
            correct += 1
        confusion[f"{gold}->{guess}"] += 1
    precision = correct / answered if answered else 0.0
    recall = correct / total if total else 1.0
    return {
        "evaluated_slots": total,
        "answered_slots": answered,
        "correct_slots": correct,
        "precision": precision,
        "recall": recall,
        "f1": harmonic_mean(precision, recall),
        "exact_accuracy": correct / total if total else 1.0,
        "abstention_rate": (total - answered) / total if total else 0.0,
        "confusion": dict(sorted(confusion.items())),
    }


def harmonic_mean(left: float, right: float) -> float:
    return 2 * left * right / (left + right) if left + right else 0.0


def parse_json_object(content: str) -> dict[str, Any]:
    import re

    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def extract_reference_ids(content: str) -> set[str]:
    import re

    return set(re.findall(r"ref_[a-z0-9_]+", content))


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(max(math.ceil(fraction * len(ordered)) - 1, 0), len(ordered) - 1)
    return ordered[index]


class ResourceSampler:
    """Periodic sampling of a target process group + system memory pressure."""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self.samples: list[dict[str, Any]] = []
        self._stop = False

    def start(self, pids: list[int]) -> None:
        self.samples = []
        self._stop = False
        self._sample(pids)

    def tick(self, pids: list[int]) -> None:
        self._sample(pids)

    def _sample(self, pids: list[int]) -> None:
        row: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "wall_elapsed_s": None,
            "rss_kb": None,
            "cpu_percent": None,
            "memory_pressure_free_pct": None,
            "swap_used_mb": None,
        }
        if pids:
            row["rss_kb"], row["cpu_percent"] = self._ps_sample(pids)
        row["memory_pressure_free_pct"] = self._memory_free_pct()
        row["swap_used_mb"] = self._swap_used_mb()
        self.samples.append(row)

    @staticmethod
    def _ps_sample(pids: list[int]) -> tuple[int | None, float | None]:
        if not pids:
            return None, None
        try:
            proc = __import__("subprocess").run(
                ["ps", "-o", "pid=,rss=,%cpu=", "-p", ",".join(str(p) for p in pids)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception:
            return None, None
        total_rss = 0
        cpu = 0.0
        for line in proc.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 3:
                try:
                    total_rss += int(fields[1])
                    cpu += float(fields[2])
                except ValueError:
                    pass
        return (total_rss if total_rss else None, cpu if cpu else None)

    @staticmethod
    def _memory_free_pct() -> float | None:
        try:
            proc = __import__("subprocess").run(
                ["memory_pressure", "-Q"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            for line in proc.stdout.splitlines():
                if "System-wide memory free percentage:" in line:
                    return float(line.rsplit(":", 1)[1].strip().rstrip("%"))
        except Exception:
            pass
        return None

    @staticmethod
    def _swap_used_mb() -> float | None:
        try:
            proc = __import__("subprocess").run(
                ["sysctl", "-n", "vm.swapusage"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            for token in proc.stdout.split(","):
                token = token.strip()
                if token.startswith("used ="):
                    return float(token.split("=")[1].strip().replace("M", ""))
        except Exception:
            pass
        return None

    def stop(self) -> list[dict[str, Any]]:
        self._stop = True
        return self.samples


def sample_once(pids: list[int]) -> dict[str, Any]:
    sampler = ResourceSampler()
    sampler._sample(pids)
    return sampler.samples[0]


def latency_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "p50": None, "p90": None, "p95": None, "max": None, "count": 0}
    return {
        "mean": statistics.fmean(values),
        "p50": _percentile(values, 0.50),
        "p90": _percentile(values, 0.90),
        "p95": _percentile(values, 0.95),
        "max": max(values),
        "count": len(values),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})
    return path


def write_runs_jsonl(path: Path, runs: list[dict[str, Any]]) -> Path:
    with path.open("w", encoding="utf-8") as stream:
        for run in runs:
            stream.write(json.dumps(run, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def write_summary_xlsx(path: Path, candidate_rows: list[dict[str, Any]]) -> Path:
    fields = [
        "candidate_id",
        "candidate_type",
        "engine",
        "model",
        "status",
        "success_rate",
        "latency_mean_ms",
        "latency_p95_ms",
        "ttft_p95_ms",
        "text_f1",
        "observable_f1",
        "abstention_rate",
        "repeatability",
        "eligible_for_selection",
    ]
    sheet = SheetSpec(
        name="CTA-BENCH-002 Summary",
        rows=[fields, *[[row.get(field, "") for field in fields] for row in candidate_rows]],
        header_rows=1,
        column_widths=[26, 14, 14, 40, 12, 12, 14, 14, 14, 12, 14, 16, 14, 20],
    )
    return write_xlsx(path, [sheet], title="CTA-BENCH-002 Candidate Summary")


def _sha_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_integrity_manifest(output_dir: Path, files: list[Path]) -> Path:
    artifacts = []
    for path in files:
        if path.name == "integrity_manifest.json":
            continue
        if path.is_file():
            artifacts.append(
                {
                    "filename": str(path.relative_to(output_dir)),
                    "sha256": _sha_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    manifest = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": sorted(artifacts, key=lambda item: item["filename"]),
    }
    path = output_dir / "integrity_manifest.json"
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
