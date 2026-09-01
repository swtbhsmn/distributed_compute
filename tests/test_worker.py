import json
from pathlib import Path

from distributed_compute.worker import BenchmarkResult, load_or_create_state


def test_worker_identity_and_benchmark_are_persistent(tmp_path: Path, monkeypatch) -> None:
    state_path = tmp_path / "worker.json"
    benchmark = BenchmarkResult(elapsed_seconds=0.5, operations=100, operations_per_second=200)
    monkeypatch.setattr("distributed_compute.worker.run_benchmark", lambda: benchmark)

    first_id, first_benchmark = load_or_create_state(state_path)
    second_id, second_benchmark = load_or_create_state(state_path)

    assert first_id == second_id
    assert first_benchmark == second_benchmark == benchmark
    assert json.loads(state_path.read_text())["worker_id"] == first_id

