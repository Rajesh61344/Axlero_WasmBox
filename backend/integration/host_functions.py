"""
WasmBox Host Function Declaration System.

Provides the infrastructure for declaring, registering, and validating
host functions that plugins can call through the host bridge.

Host functions are the only way for sandboxed plugins to interact
with external services. Each host function requires explicit permissions,
and the tenant's policy determines which functions are available.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.compiler.errors import (
    CompilerStage,
    Diagnostic,
    ErrorSeverity,
    SourceLocation,
)
from backend.integration.runtime_contract import HostFunctionSpec, TenantPolicy

logger = logging.getLogger("wasmbox.host_functions")


@dataclass
class RegisteredHostFunction:
    """A host function that has been registered with the system.

    Contains the specification, implementation callback, and metadata.
    """

    spec: HostFunctionSpec
    callback: Callable[..., Any] | None = None
    enabled: bool = True


class HostFunctionRegistry:
    """Registry for host functions available to plugins.

    Manages the declaration, registration, and validation of host functions.
    Provides the `@host_function` decorator for easy registration.
    """

    def __init__(self) -> None:
        self._functions: dict[str, RegisteredHostFunction] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the default set of host functions."""
        # Logging
        self.register(
            HostFunctionSpec(
                name="log",
                permissions=["logging"],
                description="Write a log message from the plugin.",
                param_types=["string"],
                return_type="none",
            )
        )

        # Input/output
        self.register(
            HostFunctionSpec(
                name="get_input",
                permissions=["io:read"],
                description="Get the input data passed to the plugin.",
                param_types=[],
                return_type="any",
            )
        )
        self.register(
            HostFunctionSpec(
                name="set_output",
                permissions=["io:write"],
                description="Set the output data from the plugin.",
                param_types=["any"],
                return_type="none",
            )
        )

        # Key-value store
        self.register(
            HostFunctionSpec(
                name="kv_get",
                permissions=["kv:read"],
                description="Read a value from the tenant's key-value store.",
                param_types=["string"],
                return_type="any",
            )
        )
        self.register(
            HostFunctionSpec(
                name="kv_set",
                permissions=["kv:write"],
                description="Write a value to the tenant's key-value store.",
                param_types=["string", "any"],
                return_type="none",
            )
        )

        # HTTP (explicitly gated)
        self.register(
            HostFunctionSpec(
                name="http_get",
                permissions=["http:read"],
                description="Make an HTTP GET request through the host proxy.",
                param_types=["string"],
                return_type="dict",
            )
        )

    def register(
        self,
        spec: HostFunctionSpec,
        callback: Callable[..., Any] | None = None,
    ) -> None:
        """Register a host function specification.

        Args:
            spec: The host function specification.
            callback: Optional implementation callback.
        """
        self._functions[spec.name] = RegisteredHostFunction(
            spec=spec,
            callback=callback,
            enabled=True,
        )
        logger.debug("Registered host function: %s", spec.name)

    def get(self, name: str) -> RegisteredHostFunction | None:
        """Get a registered host function by name.

        Args:
            name: The function name.

        Returns:
            The registered function, or None if not found.
        """
        return self._functions.get(name)

    def list_functions(self) -> list[HostFunctionSpec]:
        """List all registered host function specs.

        Returns:
            List of all registered host function specifications.
        """
        return [f.spec for f in self._functions.values() if f.enabled]

    def list_names(self) -> list[str]:
        """List all registered host function names.

        Returns:
            List of function names.
        """
        return [name for name, f in self._functions.items() if f.enabled]

    def validate_requested(
        self,
        requested: list[str],
        tenant_policy: TenantPolicy,
    ) -> tuple[list[str], list[Diagnostic]]:
        """Validate requested host functions against tenant policy.

        Checks that:
        1. Each requested function is registered
        2. Each requested function is allowed by tenant policy

        Args:
            requested: List of host function names requested by the plugin.
            tenant_policy: The tenant's security policy.

        Returns:
            Tuple of (approved_functions, diagnostics).
        """
        approved: list[str] = []
        diagnostics: list[Diagnostic] = []

        for func_name in requested:
            # Check if function exists in registry
            registered = self.get(func_name)
            if registered is None:
                diagnostics.append(Diagnostic(
                    code="E800",
                    severity=ErrorSeverity.ERROR,
                    stage=CompilerStage.RUNTIME,
                    message=f"Unknown host function: '{func_name}'",
                    suggestion=(
                        f"Available host functions: {', '.join(self.list_names())}. "
                        "Plugins cannot dynamically discover host functions."
                    ),
                ))
                continue

            if not registered.enabled:
                diagnostics.append(Diagnostic(
                    code="E801",
                    severity=ErrorSeverity.ERROR,
                    stage=CompilerStage.RUNTIME,
                    message=f"Host function '{func_name}' is currently disabled.",
                ))
                continue

            # Check tenant policy
            if not tenant_policy.is_host_function_allowed(func_name):
                diagnostics.append(Diagnostic(
                    code="E802",
                    severity=ErrorSeverity.ERROR,
                    stage=CompilerStage.RUNTIME,
                    message=f"Host function '{func_name}' is not allowed for tenant '{tenant_policy.tenant_id}'",
                    suggestion=(
                        "Contact your administrator to request access to this host function."
                    ),
                    context={
                        "function": func_name,
                        "tenant_id": tenant_policy.tenant_id,
                        "required_permissions": registered.spec.permissions,
                    },
                ))
                continue

            # Function is approved
            approved.append(func_name)
            logger.debug(
                "Host function '%s' approved for tenant '%s'",
                func_name,
                tenant_policy.tenant_id,
            )

        # Add info diagnostic for approved functions
        if approved:
            diagnostics.append(Diagnostic(
                code="I800",
                severity=ErrorSeverity.INFO,
                stage=CompilerStage.RUNTIME,
                message=f"Approved host functions: {', '.join(approved)}",
            ))

        return approved, diagnostics

    def get_specs_for_manifest(self, function_names: list[str]) -> list[dict[str, Any]]:
        """Get serializable specs for the given function names.

        Args:
            function_names: List of function names.

        Returns:
            List of spec dictionaries for the manifest.
        """
        specs = []
        for name in function_names:
            registered = self.get(name)
            if registered:
                specs.append(registered.spec.to_dict())
        return specs


def host_function(
    name: str,
    permissions: list[str] | None = None,
    description: str = "",
) -> Callable:
    """Decorator to register a function as a host function.

    Usage:
        @host_function(name="log", permissions=["logging"])
        def host_log(message: str) -> None:
            print(f"[Plugin Log] {message}")

    Args:
        name: The name the plugin uses to call this function.
        permissions: Required permissions.
        description: Human-readable description.

    Returns:
        Decorator function.
    """
    def decorator(func: Callable) -> Callable:
        spec = HostFunctionSpec(
            name=name,
            permissions=permissions or [],
            description=description or func.__doc__ or "",
        )

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.debug("Host function '%s' called", name)
            return func(*args, **kwargs)

        wrapper._wasmbox_host_spec = spec  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Default host function implementations (for testing/demo)
# ---------------------------------------------------------------------------


@host_function(name="log", permissions=["logging"], description="Log a message")
def default_host_log(message: str) -> None:
    """Default log host function implementation."""
    logger.info("[Plugin] %s", message)


@host_function(
    name="get_customer_data",
    permissions=["customer:read"],
    description="Read customer data by ID",
)
def default_get_customer_data(customer_id: str) -> dict[str, Any]:
    """Default customer data host function (returns mock data)."""
    return {"customer_id": customer_id, "name": "Example Customer"}


# Global default registry instance
_default_registry: HostFunctionRegistry | None = None


def get_default_registry() -> HostFunctionRegistry:
    """Get or create the default host function registry.

    Returns:
        The default HostFunctionRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = HostFunctionRegistry()
    return _default_registry
