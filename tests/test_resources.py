from types import SimpleNamespace

from distributed_compute import resources


class FakePsutil:
    @staticmethod
    def cpu_count(logical: bool) -> int:
        assert logical is True
        return 8

    @staticmethod
    def virtual_memory() -> SimpleNamespace:
        return SimpleNamespace(available=123_456)

    @staticmethod
    def cpu_percent(interval: float) -> float:
        assert interval == 0
        return 12.5


def test_desktop_resource_snapshot_prefers_psutil(monkeypatch) -> None:
    monkeypatch.setattr(resources, "_psutil", FakePsutil())
    assert resources.resource_snapshot(sample_interval=0) == {
        "logical_cpu_cores": 8,
        "available_ram_bytes": 123_456,
        "cpu_usage_percent": 12.5,
    }


def test_native_resource_snapshot_without_psutil(monkeypatch) -> None:
    readings = iter(((100, 40), (200, 60)))
    monkeypatch.setattr(resources, "_psutil", None)
    monkeypatch.setattr(resources.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(resources, "_read_proc_cpu_times", lambda: next(readings))
    monkeypatch.setattr(resources, "_available_ram_from_proc", lambda: 654_321)

    assert resources.resource_snapshot(sample_interval=0) == {
        "logical_cpu_cores": 4,
        "available_ram_bytes": 654_321,
        "cpu_usage_percent": 80.0,
    }


def test_broken_psutil_falls_back_to_native(monkeypatch) -> None:
    class BrokenPsutil:
        @staticmethod
        def cpu_count(logical: bool) -> int:
            raise RuntimeError("platform Android is not supported")

    monkeypatch.setattr(resources, "_psutil", BrokenPsutil())
    monkeypatch.setattr(resources.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(resources, "_available_ram_from_proc", lambda: 1000)
    monkeypatch.setattr(resources, "_cpu_percent_without_psutil", lambda interval, cores: 25.0)
    assert resources.resource_snapshot(sample_interval=0)["available_ram_bytes"] == 1000


def test_android_termux_is_reported_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    assert resources.is_android_termux()
    assert resources.os_name() == "Android/Termux"
