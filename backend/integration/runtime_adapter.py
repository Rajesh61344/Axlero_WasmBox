"""
WasmBox Runtime Adapter.

Adapter for Wasmtime runtime to interact with compiled WASM artifacts.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from typing import Any

from backend.compiler.config import ExecutionLimits
from backend.compiler.models import PluginManifest, WasmArtifact
from backend.integration.host_functions import get_default_registry
from backend.integration.runtime_contract import (
    ExecutionResponse,
    RuntimeArtifact,
    TenantPolicy,
)

try:
    import wasmtime
except ImportError:
    wasmtime = None


class WasmtimeAdapter:
    """Adapter for executing WASM artifacts using Wasmtime."""

    def __init__(
        self,
        host_registry: Any = None,
        policy_provider: Callable[[str], TenantPolicy] | None = None,
    ) -> None:
        self.host_registry = host_registry
        self.policy_provider = policy_provider
        self._wasmtime_available = wasmtime is not None

    def resolve_tenant_policy(self, tenant_id: str) -> TenantPolicy:
        """Resolve the security policy for a tenant.

        A custom policy provider may supply tenant-specific permissions.

        When no provider is configured, the runtime uses a restrictive
        default policy that only permits the safe ``log`` host function.
        """

        if self.policy_provider is not None:
            policy = self.policy_provider(tenant_id)

            if not isinstance(policy, TenantPolicy):
                raise TypeError(
                    "policy_provider must return a TenantPolicy instance."
                )

            if policy.tenant_id != tenant_id:
                raise ValueError(
                    "policy_provider returned a policy for a different tenant."
                )

            return policy

        return TenantPolicy(
            tenant_id=tenant_id,
            allowed_host_functions={"log"},
        )

    def execute(
        self,
        artifact: WasmArtifact | RuntimeArtifact,
        input_data: dict[str, Any],
        limits: ExecutionLimits | None = None,
    ) -> ExecutionResponse:
        """Execute the WASM artifact."""

        if not self._wasmtime_available:
            return ExecutionResponse(
                success=False,
                error="Wasmtime is not installed. Full execution is not possible.",
                error_code="WASMTIME_MISSING",
            )

        wasm_bytes = getattr(artifact, "wasm_bytes", None)

        if wasm_bytes is None:
            wasm_bytes = getattr(
                artifact,
                "artifact_bytes",
                b"",
            )

        if not wasm_bytes:
            return ExecutionResponse(
                success=False,
                error="No WASM artifact bytes found.",
                error_code="NO_WASM_ARTIFACT",
            )

        # ---------------------------------------------------------
        # Manifest
        # ---------------------------------------------------------

        manifest = getattr(
            artifact,
            "manifest",
            None,
        )

        if not manifest:
            manifest = self.extract_manifest(wasm_bytes)

        # ---------------------------------------------------------
        # Source
        # ---------------------------------------------------------

        extracted_source = self.extract_source(wasm_bytes)

        if not extracted_source:
            return ExecutionResponse(
                success=False,
                error="No source found in artifact",
                error_code="NO_SOURCE",
            )

        # ---------------------------------------------------------
        # Host Function Security Validation
        # ---------------------------------------------------------

        requested = (
            manifest.requested_host_functions
            if manifest
            else []
        )

        registry = (
            self.host_registry
            if self.host_registry is not None
            else get_default_registry()
        )

        tenant_id = (
            getattr(manifest, "tenant_id", None)
            or getattr(artifact, "tenant_id", None)
            or "default"
        )

        # Resolve the tenant-specific security policy.
        #
        # requested_host_functions only describes what the plugin
        # wants to use. It does NOT grant permission.
        #
        # If no external policy provider is configured, the runtime
        # falls back to a restrictive default policy.
        policy = self.resolve_tenant_policy(tenant_id)

        if requested:
            approved, diagnostics = registry.validate_requested(
                requested,
                policy,
            )

            # Reject if the registry produced any security errors.
            for diagnostic in diagnostics:
                if diagnostic.code.startswith("E"):
                    return ExecutionResponse(
                        success=False,
                        error=diagnostic.message,
                        error_code="HOST_FUNCTION_NOT_ALLOWED",
                    )

            # Defensive check:
            # every requested function must be explicitly approved.
            if set(approved) != set(requested):
                return ExecutionResponse(
                    success=False,
                    error=(
                        "One or more requested host functions "
                        "were not authorized."
                    ),
                    error_code="HOST_FUNCTION_NOT_ALLOWED",
                )

        # ---------------------------------------------------------
        # Temporary stdin/stdout files
        # ---------------------------------------------------------

        temp_stdin: str | None = None
        temp_stdout: str | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                delete=False,
            ) as stdin_file:
                stdin_file.write(
                    json.dumps(input_data)
                )
                temp_stdin = stdin_file.name

            with tempfile.NamedTemporaryFile(
                mode="r",
                delete=False,
            ) as stdout_file:
                temp_stdout = stdout_file.name

            # -----------------------------------------------------
            # Configure Wasmtime
            # -----------------------------------------------------

            config = wasmtime.Config()

            config.consume_fuel = True

            engine = wasmtime.Engine(config)

            store = wasmtime.Store(engine)

            # -----------------------------------------------------
            # Execution fuel
            # -----------------------------------------------------

            fuel_limit = (
                limits.max_fuel
                if limits
                else (
                    manifest.max_fuel
                    if manifest
                    else 5_000_000
                )
            )

            store.set_fuel(fuel_limit)

            # -----------------------------------------------------
            # WASI / Linker
            # -----------------------------------------------------

            linker = wasmtime.Linker(engine)

            linker.define_wasi()

            wasi = wasmtime.WasiConfig()

            wasi.stdin_file = temp_stdin
            wasi.stdout_file = temp_stdout
            wasi.inherit_stderr()

            wasi.argv = [
                "python",
                "-c",
                extracted_source,
            ]

            store.set_wasi(wasi)

            # -----------------------------------------------------
            # Load WASM module
            # -----------------------------------------------------

            module = wasmtime.Module(
                engine,
                wasm_bytes,
            )

            # -----------------------------------------------------
            # Instantiate module
            # -----------------------------------------------------

            instance = linker.instantiate(
                store,
                module,
            )

            # -----------------------------------------------------
            # Execute _start
            # -----------------------------------------------------

            start_func = instance.exports(
                store
            ).get("_start")

            if start_func:
                start_func(store)

            # -----------------------------------------------------
            # Read stdout
            # -----------------------------------------------------

            output_str = ""

            if temp_stdout:
                with open(
                    temp_stdout,
                    "r",
                ) as stdout_file:
                    output_str = stdout_file.read()

            # -----------------------------------------------------
            # Parse output
            # -----------------------------------------------------

            try:
                output = (
                    json.loads(output_str)
                    if output_str
                    else {}
                )

            except json.JSONDecodeError:
                output = {
                    "raw_output": output_str
                }

            # -----------------------------------------------------
            # Successful execution
            # -----------------------------------------------------

            fuel_remaining = store.get_fuel()

            fuel_consumed = (
                fuel_limit - fuel_remaining
            )

            return ExecutionResponse(
                success=True,
                output=output,
                fuel_consumed=fuel_consumed,
                stdout=output_str,
            )

        # ---------------------------------------------------------
        # WASM Trap
        # ---------------------------------------------------------

        except wasmtime.Trap as exc:
            message = str(exc)

            if "all fuel consumed" in message.lower():
                return ExecutionResponse(
                    success=False,
                    error=(
                        "Execution timeout or infinite "
                        "loop detected."
                    ),
                    error_code="TIMEOUT",
                )

            return ExecutionResponse(
                success=False,
                error=f"WASM Trap: {message}",
                error_code="WASM_TRAP",
            )

        # ---------------------------------------------------------
        # General execution error
        # ---------------------------------------------------------

        except Exception as exc:
            return ExecutionResponse(
                success=False,
                error=str(exc),
                error_code="EXECUTION_ERROR",
            )

        # ---------------------------------------------------------
        # Cleanup
        # ---------------------------------------------------------

        finally:
            if temp_stdin:
                try:
                    os.unlink(temp_stdin)
                except OSError:
                    pass

            if temp_stdout:
                try:
                    os.unlink(temp_stdout)
                except OSError:
                    pass

    def validate_artifact(
        self,
        artifact: WasmArtifact | RuntimeArtifact,
    ) -> bool:
        """Validate that an artifact can be loaded by Wasmtime."""

        if not self._wasmtime_available:
            return False

        wasm_bytes = getattr(
            artifact,
            "wasm_bytes",
            None,
        )

        if wasm_bytes is None:
            wasm_bytes = getattr(
                artifact,
                "artifact_bytes",
                b"",
            )

        if not wasm_bytes:
            return False

        try:
            engine = wasmtime.Engine()

            wasmtime.Module.validate(
                engine,
                wasm_bytes,
            )

            return True

        except Exception:
            return False

    def extract_manifest(
        self,
        wasm_bytes: bytes,
    ) -> PluginManifest | None:
        """Extract the manifest from a WASM custom section."""

        from backend.compiler.wasm_builder import (
            extract_custom_section,
        )

        manifest_bytes = extract_custom_section(
            wasm_bytes,
            ".wasmbox.manifest",
        )

        if not manifest_bytes:
            manifest_bytes = extract_custom_section(
                wasm_bytes,
                "wasmbox_manifest",
            )

        if not manifest_bytes:
            return None

        try:
            data = json.loads(
                manifest_bytes.decode("utf-8")
            )

            return PluginManifest(**data)

        except Exception:
            return None

    def extract_source(
        self,
        wasm_bytes: bytes,
    ) -> str | None:
        """Extract source code from a WASM custom section."""

        from backend.compiler.wasm_builder import (
            extract_custom_section,
        )

        source_bytes = extract_custom_section(
            wasm_bytes,
            ".wasmbox.source",
        )

        if not source_bytes:
            source_bytes = extract_custom_section(
                wasm_bytes,
                "wasmbox_source",
            )

        if not source_bytes:
            return None

        try:
            return source_bytes.decode("utf-8")

        except Exception:
            return None