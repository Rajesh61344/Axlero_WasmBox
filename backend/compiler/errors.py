"""
WasmBox Compiler Error Hierarchy.

Provides structured, serializable error types for every stage of the
compilation pipeline. Each error carries a machine-readable code, the
pipeline stage that produced it, a human-readable message, and optional
source location information.

Error Code Prefixes:
    E001–E099  Parse errors
    E100–E199  Validation errors
    E200–E299  Security violations
    E300–E399  Dependency errors
    E400–E499  Transformation errors
    E500–E599  Backend compilation errors
    E600–E699  WASM validation errors
    E700–E799  Artifact errors
    E800–E899  Runtime contract errors
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorSeverity(str, Enum):
    """Severity levels for compiler diagnostics."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class CompilerStage(str, Enum):
    """Pipeline stages that can produce errors."""

    PARSER = "parser"
    VALIDATOR = "validator"
    ANALYZER = "analyzer"
    TRANSFORMER = "transformer"
    DEPENDENCIES = "dependencies"
    BACKEND = "backend"
    WASM_VALIDATION = "wasm_validation"
    ARTIFACT = "artifact"
    RUNTIME = "runtime"
    PIPELINE = "pipeline"
    CACHE = "cache"


@dataclass(frozen=True)
class SourceLocation:
    """Source code location for error reporting."""

    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary, omitting None values."""
        return {k: v for k, v in {
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "filename": self.filename,
        }.items() if v is not None}


@dataclass
class Diagnostic:
    """A single compiler diagnostic message.

    Diagnostics can represent errors, warnings, or informational messages
    from any stage of the pipeline.
    """

    code: str
    severity: ErrorSeverity
    stage: CompilerStage
    message: str
    location: SourceLocation | None = None
    suggestion: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        result: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value,
            "stage": self.stage.value,
            "message": self.message,
        }
        if self.location:
            result["location"] = self.location.to_dict()
        if self.suggestion:
            result["suggestion"] = self.suggestion
        if self.context:
            result["context"] = self.context
        return result

    def __str__(self) -> str:
        parts = [f"{self.severity.value.upper()} {self.code}: {self.message}"]
        if self.location and self.location.line is not None:
            loc = f"  at line {self.location.line}"
            if self.location.column is not None:
                loc += f", column {self.location.column}"
            if self.location.filename:
                loc += f" in {self.location.filename}"
            parts.append(loc)
        if self.suggestion:
            parts.append(f"  Suggestion: {self.suggestion}")
        return "\n".join(parts)


class CompilerError(Exception):
    """Base exception for all compiler errors.

    Every compiler error carries a machine-readable code, the pipeline
    stage that produced it, a human-readable message, and optional
    source location information.
    """

    def __init__(
        self,
        code: str,
        stage: CompilerStage,
        message: str,
        line: int | None = None,
        column: int | None = None,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.stage = stage
        self.message = message
        self.line = line
        self.column = column
        self.suggestion = suggestion
        self.details = details or {}
        super().__init__(self.format_message())

    def format_message(self) -> str:
        """Format the error as a human-readable string."""
        parts = [f"[{self.code}] {self.stage.value}: {self.message}"]
        if self.line is not None:
            loc = f"  Line {self.line}"
            if self.column is not None:
                loc += f", Column {self.column}"
            parts.append(loc)
        if self.suggestion:
            parts.append(f"  Suggestion: {self.suggestion}")
        return "\n".join(parts)

    def to_diagnostic(self) -> Diagnostic:
        """Convert to a Diagnostic object."""
        return Diagnostic(
            code=self.code,
            severity=ErrorSeverity.ERROR,
            stage=self.stage,
            message=self.message,
            location=SourceLocation(
                line=self.line,
                column=self.column,
            ) if self.line is not None or self.column is not None else None,
            suggestion=self.suggestion,
            context=self.details,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary for API responses."""
        return self.to_diagnostic().to_dict()


class ParseError(CompilerError):
    """Error during Python source parsing."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        suggestion: str | None = None,
        code: str = "E001",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.PARSER,
            message=message,
            line=line,
            column=column,
            suggestion=suggestion,
            details=details,
        )


class ValidationError(CompilerError):
    """Error during AST validation."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        suggestion: str | None = None,
        code: str = "E100",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.VALIDATOR,
            message=message,
            line=line,
            column=column,
            suggestion=suggestion,
            details=details,
        )


class SecurityViolation(CompilerError):
    """Security policy violation detected in source code."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        suggestion: str | None = None,
        code: str = "E200",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.VALIDATOR,
            message=message,
            line=line,
            column=column,
            suggestion=suggestion,
            details=details,
        )


class DependencyError(CompilerError):
    """Error during dependency resolution."""

    def __init__(
        self,
        message: str,
        code: str = "E300",
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.DEPENDENCIES,
            message=message,
            suggestion=suggestion,
            details=details,
        )


class TransformationError(CompilerError):
    """Error during source transformation."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        code: str = "E400",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.TRANSFORMER,
            message=message,
            line=line,
            column=column,
            details=details,
        )


class BackendCompilationError(CompilerError):
    """Error during WASM backend compilation."""

    def __init__(
        self,
        message: str,
        code: str = "E500",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.BACKEND,
            message=message,
            details=details,
        )


class WasmValidationError(CompilerError):
    """Error during WASM artifact validation."""

    def __init__(
        self,
        message: str,
        code: str = "E600",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.WASM_VALIDATION,
            message=message,
            details=details,
        )


class ArtifactError(CompilerError):
    """Error during artifact storage or retrieval."""

    def __init__(
        self,
        message: str,
        code: str = "E700",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.ARTIFACT,
            message=message,
            details=details,
        )


class RuntimeContractError(CompilerError):
    """Error in runtime contract validation."""

    def __init__(
        self,
        message: str,
        code: str = "E800",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            stage=CompilerStage.RUNTIME,
            message=message,
            details=details,
        )
