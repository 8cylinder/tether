from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import Self

import pytest

from tether import local


class Recorder:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **kwargs: object) -> SimpleNamespace:
        self.commands.append(command)
        return SimpleNamespace(
            returncode=self.returncode, stdout=self.stdout, stderr=""
        )


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_get_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        local.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(b'{"ok": true}'),
    )

    assert local._get_json("http://example") == {"ok": True}


@pytest.mark.parametrize("body", [b"not json"])
def test_get_json_invalid_payload(
    body: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        local.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(body),
    )

    assert local._get_json("http://example") is None


def test_get_json_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(request: object, timeout: float) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(local.urllib.request, "urlopen", fail)

    assert local._get_json("http://example") is None


def test_url_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local, "_get_json", lambda url, **kwargs: {})
    assert local.url_reachable("http://example") is True


def test_ollama_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        local, "_get_json", lambda url, **kwargs: {"version": "0.40.18"}
    )
    assert local.ollama_version() == "0.40.18"


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"version": 3}],
)
def test_ollama_version_unavailable(
    payload: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "_get_json", lambda url, **kwargs: payload)
    assert local.ollama_version() is None


def test_ollama_models(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "models": [
            {
                "name": "mimo-v2.6:9b",
                "details": {"context_length": 262144},
                "capabilities": ["completion", "tools"],
            },
            {
                "name": "embed",
                "details": {"context_length": 2048},
                "capabilities": ["embedding"],
            },
        ]
    }
    monkeypatch.setattr(local, "_get_json", lambda url, **kwargs: payload)

    models = local.ollama_models()

    assert [model.name for model in models] == ["mimo-v2.6:9b", "embed"]
    assert models[0].context_length == 262144
    assert models[0].supports_tools is True
    assert models[1].supports_tools is False


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"models": "nope"},
        {
            "models": [
                "nope",
                {"name": 3},
                {"name": "ok", "details": "nope", "capabilities": "nope"},
                {"name": "ok", "details": {"context_length": True}},
            ]
        },
    ],
)
def test_ollama_models_tolerates_bad_payloads(
    payload: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "_get_json", lambda url, **kwargs: payload)
    models = local.ollama_models()

    for model in models:
        assert model.name == "ok"
        assert model.context_length is None
        assert model.capabilities == ()


def test_ollama_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "models": [
            {"name": "mimo-v2.6:9b", "context_length": 32768},
            {"name": "other"},
        ]
    }
    monkeypatch.setattr(local, "_get_json", lambda url, **kwargs: payload)

    loaded = local.ollama_loaded()

    assert loaded == [
        local.LoadedOllamaModel("mimo-v2.6:9b", 32768),
        local.LoadedOllamaModel("other", None),
    ]


@pytest.mark.parametrize(
    "payload",
    [None, [], {"models": "nope"}, {"models": ["nope", {"name": 3}]}],
)
def test_ollama_loaded_tolerates_bad_payloads(
    payload: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "_get_json", lambda url, **kwargs: payload)
    assert local.ollama_loaded() == []


def test_context_length_prefers_loaded_model() -> None:
    loaded = [local.LoadedOllamaModel("m", 32768)]
    env = {"OLLAMA_CONTEXT_LENGTH": "4096"}
    assert local.context_length(loaded, env) == 32768


def test_context_length_uses_environment() -> None:
    env = {"OLLAMA_CONTEXT_LENGTH": "16384"}
    assert local.context_length([], env) == 16384


def test_context_length_invalid_environment() -> None:
    assert local.context_length([], {"OLLAMA_CONTEXT_LENGTH": "nope"}) is None


def test_context_length_unknown() -> None:
    assert local.context_length([], {}) is None


def test_container_reachable_via_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local, "url_reachable", lambda url: True)
    assert local.container_reachable({}, "172.17.0.1") is True


@pytest.mark.parametrize(
    "bind",
    ["0.0.0.0:11434", "[::]:11434", ":11434"],
)
def test_container_reachable_via_bind(
    bind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local, "url_reachable", lambda url: False)
    assert local.container_reachable({"OLLAMA_HOST": bind}, "172.17.0.1")


def test_container_not_reachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local, "url_reachable", lambda url: False)
    assert not local.container_reachable(
        {"OLLAMA_HOST": "127.0.0.1:11434"}, "172.17.0.1"
    )


def test_bridge_gateway_uses_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder(stdout="172.18.0.1\n")
    monkeypatch.setattr(local.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(local.subprocess, "run", recorder)

    assert local.bridge_gateway() == "172.18.0.1"
    assert recorder.commands[0][:4] == [
        "docker",
        "network",
        "inspect",
        "bridge",
    ]


@pytest.mark.parametrize(
    "stdout,returncode",
    [("", 0), ("172.17.0.1", 1)],
)
def test_bridge_gateway_falls_back(
    stdout: str,
    returncode: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local.shutil, "which", lambda name: "/bin/docker")
    monkeypatch.setattr(
        local.subprocess, "run", Recorder(stdout=stdout, returncode=returncode)
    )

    assert local.bridge_gateway() == local.DEFAULT_BRIDGE_GATEWAY


def test_bridge_gateway_without_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local.shutil, "which", lambda name: None)
    assert local.bridge_gateway() == local.DEFAULT_BRIDGE_GATEWAY


def test_bridge_gateway_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("docker", 10)

    monkeypatch.setattr(local.shutil, "which", lambda name: "/bin/docker")
    monkeypatch.setattr(local.subprocess, "run", fail)

    assert local.bridge_gateway() == local.DEFAULT_BRIDGE_GATEWAY


def test_systemd_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder(
        stdout=("OLLAMA_HOST=0.0.0.0:11434 OLLAMA_CONTEXT_LENGTH=32768")
    )
    monkeypatch.setattr(local.shutil, "which", lambda name: "/bin/systemctl")
    monkeypatch.setattr(local.subprocess, "run", recorder)

    env = local.systemd_environment()

    assert env == {
        "OLLAMA_HOST": "0.0.0.0:11434",
        "OLLAMA_CONTEXT_LENGTH": "32768",
    }
    assert recorder.commands[0][:3] == ["systemctl", "show", "ollama"]


def test_systemd_environment_without_systemctl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local.shutil, "which", lambda name: None)
    assert local.systemd_environment() == {}


def test_systemd_environment_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local.shutil, "which", lambda name: "/bin/systemctl")
    monkeypatch.setattr(local.subprocess, "run", Recorder(returncode=1))

    assert local.systemd_environment() == {}


def test_systemd_environment_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("systemctl", 10)

    monkeypatch.setattr(local.shutil, "which", lambda name: "/bin/systemctl")
    monkeypatch.setattr(local.subprocess, "run", fail)

    assert local.systemd_environment() == {}


@pytest.mark.parametrize(
    "args,expected",
    [
        (["--network=host"], True),
        (["--network", "host"], True),
        (["--add-host=host.docker.internal:host-gateway"], True),
        (["--add-host", "host.docker.internal:host-gateway"], True),
        ([], False),
        (["--network", "bridge"], False),
        (["--add-host", "other:1.2.3.4"], False),
    ],
)
def test_docker_host_access(args: list[str], expected: bool) -> None:
    assert local.docker_host_access(args) is expected
