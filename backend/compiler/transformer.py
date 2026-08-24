"""
WasmBox Compiler Source Transformation.

Transforms the analyzed Python source code before it gets compiled to WASM.
This includes injecting metadata, bridging host functions, and wrapping the
entrypoint for safe execution.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from .config import CompileConfig
from .errors import CompilerStage, Diagnostic, ErrorSeverity, TransformationError
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

    def transform(self, source: str, analysis: AnalysisResult, config: CompileConfig) -> TransformResult:
        """Apply all source transformations in sequence."""
        result = TransformResult(source=source, original_source=source)
        
        try:
            # Apply transformations in order
            source = self._strip_shebang(source, result)
            source = self._strip_encoding_declaration(source, result)
            source = self._inject_plugin_metadata(source, config, result)
            source = self._inject_host_bridge(source, analysis, result)
            source = self._wrap_entrypoint(source, config, result)
            source = self._normalize_newlines(source, result)

            # Verify it's still valid Python
            try:
                ast.parse(source)
            except SyntaxError as e:
                raise TransformationError(
                    message=f"Transformation produced invalid Python: {e}",
                    line=e.lineno,
                    column=e.offset,
                    code="E401"
                )

            result.source = source
        except TransformationError as e:
            result.diagnostics.append(e.to_diagnostic())
        except Exception as e:
            result.diagnostics.append(
                Diagnostic(
                    code="E400",
                    severity=ErrorSeverity.ERROR,
                    stage=CompilerStage.TRANSFORMER,
                    message=f"Unexpected transformation error: {str(e)}",
                )
            )

        return result

    def _strip_shebang(self, source: str, result: TransformResult) -> str:
        """Remove shebang line from the source if present."""
        if source.startswith("#!"):
            lines = source.splitlines(keepends=True)
            if lines:
                lines[0] = "\n"  # Replace with empty line to preserve line numbers
                result.transformations.append("Stripped shebang")
                return "".join(lines)
        return source

    def _strip_encoding_declaration(self, source: str, result: TransformResult) -> str:
        """Remove encoding declaration lines."""
        lines = source.splitlines(keepends=True)
        transformed = False
        for i, line in enumerate(lines[:2]):
            if re.match(r"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)", line):
                lines[i] = "\n"
                transformed = True
        
        if transformed:
            result.transformations.append("Stripped encoding declaration")
            return "".join(lines)
        return source

    def _inject_plugin_metadata(self, source: str, config: CompileConfig, result: TransformResult) -> str:
        """Inject module-level plugin metadata constants."""
        metadata = (
            f"__wasmbox_plugin__ = True\n"
            f"__wasmbox_version__ = {config.compiler_version!r}\n"
        )
        result.transformations.append("Injected plugin metadata")
        return metadata + source

    def _inject_host_bridge(self, source: str, analysis: AnalysisResult, result: TransformResult) -> str:
        """Inject host function bridge if host functions are referenced."""
        if not analysis.host_function_refs:
            return source

        bridge_code = (
            "\n# --- WasmBox Host Bridge ---\n"
            "class _WasmBoxHost:\n"
            "    def __getattr__(self, name):\n"
            "        def placeholder(*args, **kwargs):\n"
            "            raise RuntimeError(f'Host function {name} not linked')\n"
            "        return placeholder\n"
            "host = _WasmBoxHost()\n"
            "# ---------------------------\n\n"
        )
        result.transformations.append("Injected host function bridge")
        return bridge_code + source

    def _wrap_entrypoint(self, source: str, config: CompileConfig, result: TransformResult) -> str:
        """Wrap the entrypoint with error handling."""
        entrypoint = config.entrypoint_function
        
        wrapper_code = f"""
# --- WasmBox Entrypoint Wrapper ---
def __wasmbox_wrapped_{entrypoint}(*args, **kwargs):
    try:
        return {entrypoint}(*args, **kwargs)
    except Exception as e:
        return {{"error": type(e).__name__, "message": str(e)}}
# ----------------------------------
"""
        # Note: In a real implementation we would modify the AST to rename the original 
        # or properly inject this at the bottom if the entrypoint exists. For now, 
        # append to end and it assumes entrypoint exists.
        result.transformations.append("Wrapped entrypoint with error handling")
        return source + "\n" + wrapper_code

    def _normalize_newlines(self, source: str, result: TransformResult) -> str:
        """Ensure consistent Unix-style newlines."""
        normalized = source.replace("\r\n", "\n").replace("\r", "\n")
        if normalized != source:
            result.transformations.append("Normalized newlines")
        return normalized
