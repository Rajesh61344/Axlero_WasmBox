"""
WasmBox Compiler Source Transformation.

Transforms analyzed Python source code before compilation.
This includes metadata injection, host-function bridge generation,
entrypoint wrapping, and source normalization.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from .config import CompileConfig
from .errors import (
    CompilerStage,
    Diagnostic,
    ErrorSeverity,
    TransformationError,
)
from .models import AnalysisResult


@dataclass
class TransformResult:
    """Result of source transformation stage."""

    source: str
    original_source: str
    transformations: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


class SourceTransformer:
    """Transforms plugin source code for WASM execution."""

    def transform(
        self,
        source: str,
        analysis: AnalysisResult,
        config: CompileConfig,
    ) -> TransformResult:
        """Apply all source transformations in a controlled sequence."""

        result = TransformResult(
            source=source,
            original_source=source,
        )

        try:
            source = self._strip_shebang(
                source,
                result,
            )

            source = self._strip_encoding_declaration(
                source,
                result,
            )

            source = self._inject_plugin_metadata(
                source,
                config,
                result,
            )

            source = self._inject_host_bridge(
                source,
                analysis,
                result,
            )

            source = self._wrap_entrypoint(
                source,
                config,
                result,
            )

            source = self._normalize_newlines(
                source,
                result,
            )

            # Final syntax verification.
            try:
                ast.parse(source)
            except SyntaxError as exc:
                raise TransformationError(
                    message=(
                        "Transformation produced invalid Python: "
                        f"{exc}"
                    ),
                    line=exc.lineno,
                    column=exc.offset,
                    code="E401",
                ) from exc

            result.source = source

        except TransformationError as exc:
            result.diagnostics.append(
                exc.to_diagnostic()
            )

        except Exception as exc:
            result.diagnostics.append(
                Diagnostic(
                    code="E400",
                    severity=ErrorSeverity.ERROR,
                    stage=CompilerStage.TRANSFORMER,
                    message=(
                        "Unexpected transformation error: "
                        f"{exc}"
                    ),
                )
            )

        return result

    # ------------------------------------------------------------------
    # Source cleanup
    # ------------------------------------------------------------------

    def _strip_shebang(
        self,
        source: str,
        result: TransformResult,
    ) -> str:
        """Remove a shebang while preserving the original line count."""

        if not source.startswith("#!"):
            return source

        lines = source.splitlines(
            keepends=True,
        )

        if not lines:
            return source

        lines[0] = "\n"

        result.transformations.append(
            "Stripped shebang"
        )

        return "".join(lines)

    def _strip_encoding_declaration(
        self,
        source: str,
        result: TransformResult,
    ) -> str:
        """Remove Python encoding declarations from the first two lines."""

        lines = source.splitlines(
            keepends=True,
        )

        transformed = False

        encoding_pattern = re.compile(
            r"^[ \t\f]*#.*?coding[:=][ \t]*"
            r"([-_.a-zA-Z0-9]+)"
        )

        for index, line in enumerate(lines[:2]):
            if encoding_pattern.match(line):
                lines[index] = "\n"
                transformed = True

        if transformed:
            result.transformations.append(
                "Stripped encoding declaration"
            )

            return "".join(lines)

        return source

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _inject_plugin_metadata(
        self,
        source: str,
        config: CompileConfig,
        result: TransformResult,
    ) -> str:
        """Inject immutable WasmBox metadata constants."""

        metadata = (
            "__wasmbox_plugin__ = True\n"
            f"__wasmbox_version__ = "
            f"{config.compiler_version!r}\n"
        )

        result.transformations.append(
            "Injected plugin metadata"
        )

        return metadata + source

    # ------------------------------------------------------------------
    # Host bridge
    # ------------------------------------------------------------------

    def _inject_host_bridge(
        self,
        source: str,
        analysis: AnalysisResult,
        result: TransformResult,
    ) -> str:
        """
        Inject a controlled host bridge when host functions are referenced.

        The bridge deliberately does not expose arbitrary Python objects,
        imports, modules, or runtime internals to plugin code.

        Actual host-function authorization and execution remains the
        responsibility of the trusted runtime layer.
        """

        if not analysis.host_function_refs:
            return source

        bridge_code = """
# --- WasmBox Host Bridge ---
class _WasmBoxHost:
    \"\"\"Restricted host-function bridge.

    Host calls are resolved by the trusted runtime integration layer.
    Unknown functions fail closed.
    \"\"\"

    def __init__(self):
        self._allowed = frozenset()

    def configure(self, allowed_functions):
        \"\"\"Configure the names made available to the bridge.\"\"\"
        self._allowed = frozenset(
            str(name)
            for name in allowed_functions
        )

    def call(self, name, *args, **kwargs):
        \"\"\"Request a host function call.

        The transformed plugin cannot directly access host callbacks.
        A runtime integration layer must provide the actual dispatcher.
        \"\"\"
        if name not in self._allowed:
            raise PermissionError(
                f"Host function '{name}' is not authorized"
            )

        raise RuntimeError(
            f"Host function '{name}' is not linked by the runtime"
        )

    def __getattr__(self, name):
        \"\"\"Expose only an explicit host-function call wrapper.\"\"\"

        if name.startswith("_"):
            raise AttributeError(name)

        def host_call(*args, **kwargs):
            return self.call(
                name,
                *args,
                **kwargs,
            )

        return host_call


host = _WasmBoxHost()
# ---------------------------
"""

        result.transformations.append(
            "Injected restricted host function bridge"
        )

        return bridge_code + "\n" + source

    # ------------------------------------------------------------------
    # Entrypoint
    # ------------------------------------------------------------------

    def _wrap_entrypoint(
        self,
        source: str,
        config: CompileConfig,
        result: TransformResult,
    ) -> str:
        """Wrap the configured plugin entrypoint with error handling."""

        entrypoint = config.entrypoint_function

        wrapper_code = f"""
# --- WasmBox Entrypoint Wrapper ---
def __wasmbox_wrapped_{entrypoint}(*args, **kwargs):
    \"\"\"Execute the plugin entrypoint with controlled error reporting.\"\"\"
    try:
        return {entrypoint}(*args, **kwargs)
    except Exception as exc:
        return {{
            "error": type(exc).__name__,
            "message": str(exc),
        }}
# ----------------------------------
"""

        if config.backend == "wasi_python":
            wrapper_code += f"""
if __name__ == "__main__":
    import json
    import sys

    try:
        input_data = json.load(sys.stdin)
    except Exception:
        input_data = {{}}

    result = __wasmbox_wrapped_{entrypoint}(
        input_data
    )

    print(
        json.dumps(
            result,
            default=str,
        )
    )
"""

        result.transformations.append(
            "Wrapped entrypoint with error handling"
        )

        return source + "\n" + wrapper_code

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_newlines(
        self,
        source: str,
        result: TransformResult,
    ) -> str:
        """Normalize CRLF/CR line endings to LF."""

        normalized = (
            source
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        if normalized != source:
            result.transformations.append(
                "Normalized newlines"
            )

        return normalized