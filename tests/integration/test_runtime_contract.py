"""Regression tests for the Role 3 -> Role 2 runtime contract."""

from backend.compiler.models import PluginManifest
from backend.compiler.config import ExecutionLimits
from backend.integration.runtime_contract import (
    ExecutionResponse,
    HostFunctionSpec,
    TenantPolicy,
    RuntimeArtifact,
    RuntimeExecutor,
    RuntimeCapabilities,
)


def test_execution_response_to_dict():
    response = ExecutionResponse(
        success=True,
        output={"result": 42},
        execution_time_ms=12.5,
        fuel_consumed=1000,
        memory_used_bytes=4096,
        stdout="hello",
    )

    data = response.to_dict()

    assert data["success"] is True
    assert data["output"] == {"result": 42}
    assert data["execution_time_ms"] == 12.5
    assert data["fuel_consumed"] == 1000
    assert data["memory_used_bytes"] == 4096
    assert data["stdout"] == "hello"
    assert "stderr" not in data


def test_execution_response_error():
    response = ExecutionResponse(
        success=False,
        error="Execution failed",
        error_code="RUNTIME_ERROR",
    )

    data = response.to_dict()

    assert data["success"] is False
    assert data["error"] == "Execution failed"
    assert data["error_code"] == "RUNTIME_ERROR"


def test_host_function_spec_to_dict():
    spec = HostFunctionSpec(
        name="log",
        permissions=["logging"],
        description="Write a log message",
        param_types=["str"],
        return_type="any",
    )

    data = spec.to_dict()

    assert data["name"] == "log"
    assert data["permissions"] == ["logging"]
    assert data["description"] == "Write a log message"
    assert data["param_types"] == ["str"]
    assert data["return_type"] == "any"


def test_tenant_policy_allows_requested_host_functions():
    policy = TenantPolicy(
        tenant_id="tenant-1",
        allowed_host_functions={"log", "metrics"},
    )

    allowed, rejected = policy.validate_host_functions(
        ["log", "metrics"]
    )

    assert allowed == ["log", "metrics"]
    assert rejected == []


def test_tenant_policy_rejects_unauthorized_host_functions():
    policy = TenantPolicy(
        tenant_id="tenant-1",
        allowed_host_functions={"log"},
    )

    allowed, rejected = policy.validate_host_functions(
        ["log", "filesystem.read", "network.request"]
    )

    assert allowed == ["log"]
    assert rejected == ["filesystem.read", "network.request"]


def test_tenant_policy_single_host_function_check():
    policy = TenantPolicy(
        tenant_id="tenant-1",
        allowed_host_functions={"log"},
    )

    assert policy.is_host_function_allowed("log") is True
    assert policy.is_host_function_allowed("network.request") is False


def test_runtime_capabilities_defaults():
    capabilities = RuntimeCapabilities()

    assert capabilities.supports_fuel is True
    assert capabilities.supports_epochs is True
    assert capabilities.supports_memory_limits is True
    assert capabilities.supports_wasi is True
    assert capabilities.supports_component_model is False
    assert capabilities.wasm_version == 1


def test_runtime_artifact_protocol_is_runtime_checkable():
    manifest = PluginManifest(plugin_name="test-plugin")

    class Artifact:
        artifact_bytes = b"wasm"
        artifact_hash = "abc123"

        @property
        def manifest(self):
            return manifest

    artifact = Artifact()

    assert isinstance(artifact, RuntimeArtifact)


def test_runtime_executor_protocol_is_runtime_checkable():
    class Executor:
        def execute(
            self,
            artifact,
            input_data,
            limits: ExecutionLimits | None = None,
        ):
            return ExecutionResponse(success=True, output=input_data)

        def validate_artifact(self, artifact):
            return True

    executor = Executor()

    assert isinstance(executor, RuntimeExecutor)
