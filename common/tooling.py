"""One schema builder for both sides of the benchmark.

Tools are plain Python methods with type hints and a docstring. `build_tools`
turns a list of them into OpenAI-style function schemas. Argument values that
must come from a closed set are declared with `EnumSource`, which is resolved
against the current world state (e.g. the stage) at call time.

Nothing in the codebase parses markers or regexes: if a model wants to do
something, it calls a tool and the tool validates its own arguments.
"""

from __future__ import annotations

import inspect
import re
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence


@dataclass
class ToolResult:
    """What every tool returns. Errors are data, never exceptions."""

    ok: bool
    content: Any = None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            out["content"] = self.content
        else:
            out["error"] = self.error
        return out

    @classmethod
    def success(cls, content: Any = None) -> "ToolResult":
        return cls(True, content=content)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(False, error=error)


@dataclass(frozen=True)
class EnumSource:
    """Declares that an argument's allowed values are computed at call time.

    The resolver receives the context object the tool set was built for, so a
    policy can offer a different enum per stage without the schema builder
    knowing anything about stages.
    """

    resolve: Callable[[Any], Sequence[str]]
    description: str = ""


@dataclass
class ToolSpec:
    name: str
    description: str
    method: Callable[..., Any]
    enums: Mapping[str, EnumSource] = field(default_factory=dict)


def tool(
    description: str,
    *,
    enums: Mapping[str, EnumSource] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a method as a callable tool.

    The first paragraph of the docstring is the tool description; an `Args:`
    section supplies per-argument descriptions; a `Returns:` section is ignored
    for schema purposes but kept for readers.
    """

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__tool__ = ToolSpec(  # type: ignore[attr-defined]
            name=fn.__name__,
            description=description or _first_paragraph(fn.__doc__ or ""),
            method=fn,
            enums=dict(enums or {}),
        )
        return fn

    return decorate


def _first_paragraph(doc: str) -> str:
    text = inspect.cleandoc(doc)
    if not text:
        return ""
    head = re.split(r"\n\s*\n", text, maxsplit=1)[0]
    return " ".join(line.strip() for line in head.splitlines())


def _doc_sections(doc: str) -> dict[str, str]:
    """Parse numpydoc-ish `Args:` / `Returns:` blocks into {arg: text}."""
    text = inspect.cleandoc(doc or "")
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower() in {"args:", "arguments:", "parameters:", "returns:", "raises:"}:
            if current is not None:
                sections[current] = " ".join(buffer).strip()
            current = stripped.lower().rstrip(":")
            buffer = []
            continue
        if current is None:
            continue
        if not stripped:
            continue
        buffer.append(stripped)
    if current is not None:
        sections[current] = " ".join(buffer).strip()
    return sections


_ARG_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*[:—-]\s*(?P<text>.+)$")


def _arg_descriptions(doc: str) -> dict[str, str]:
    raw = _doc_sections(doc).get("args", "")
    if not raw:
        return {}
    # Split on "name: text" boundaries that follow a period or at the start.
    out: dict[str, str] = {}
    chunks = re.split(r"(?<=[.;])\s+(?=[A-Za-z_][A-Za-z0-9_]*\s*(?:\([^)]*\))?\s*[:—-])", raw)
    for chunk in chunks:
        m = _ARG_RE.match(chunk.strip())
        if m:
            out[m.group("name")] = m.group("text").strip()
    return out


class SchemaError(ValueError):
    """Raised when a tool signature cannot be represented as a JSON schema."""


def _json_type(annotation: Any) -> dict[str, Any]:
    """Map a Python annotation to a JSON-schema fragment."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            inner = _json_type(non_none[0])
            inner["nullable"] = True
            return inner
        return {"anyOf": [_json_type(a) for a in non_none]}

    if origin is typing.Literal:
        values = list(args)
        return {"type": _literal_type(values), "enum": values}

    if origin in (list, typing.List, Sequence, typing.Sequence, Iterable):
        item = _json_type(args[0]) if args else {"type": "string"}
        return {"type": "array", "items": item}

    if origin in (dict, typing.Dict, Mapping, typing.Mapping):
        return {"type": "object"}

    if annotation is str:
        return {"type": "string"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is dict or annotation is Mapping:
        return {"type": "object"}
    if annotation is list:
        return {"type": "array", "items": {"type": "string"}}

    # Dataclasses / pydantic models used as an argument get an object schema
    # with no properties: the tool validates the body itself.
    if hasattr(annotation, "model_json_schema"):
        return annotation.model_json_schema()  # type: ignore[no-any-return]
    if hasattr(annotation, "__dataclass_fields__"):
        return {"type": "object"}

    return {"type": "string"}


def _literal_type(values: list[Any]) -> str:
    kinds = {type(v) for v in values}
    if kinds == {bool}:
        return "boolean"
    if kinds <= {int}:
        return "integer"
    if kinds <= {int, float}:
        return "number"
    return "string"


def build_tools(
    methods: Iterable[Callable[..., Any]],
    context: Any = None,
    *,
    strict: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Callable[..., Any]]]:
    """Build OpenAI tool schemas from decorated methods.

    Args:
        methods: decorated functions or bound methods.
        context: object passed to every `EnumSource` resolver (usually the actor
            or the harness, so enums can depend on stage or case).
        strict: when true, an argument annotated with a plain type but marked
            with an `EnumSource` must resolve to a non-empty list.

    Returns:
        `(schemas, name -> callable)` where each callable is bound to `context`
        if the original was an unbound method.
    """
    schemas: list[dict[str, Any]] = []
    registry: dict[str, Callable[..., Any]] = {}

    for fn in methods:
        spec = getattr(fn, "__tool__", None) or getattr(getattr(fn, "__func__", None), "__tool__", None)
        if spec is None:
            raise SchemaError(f"{fn!r} is not decorated with @tool")

        bound = _bind(fn, context)
        signature = inspect.signature(bound)
        hints = typing.get_type_hints(getattr(fn, "__func__", fn))
        descriptions = _arg_descriptions(inspect.getdoc(getattr(fn, "__func__", fn)) or "")

        properties: dict[str, Any] = {}
        required: list[str] = []

        for name, param in signature.parameters.items():
            if name in {"self", "context"}:
                continue
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                raise SchemaError(f"{spec.name}: *args/**kwargs are not allowed")

            schema = _json_type(hints.get(name, param.annotation))
            if name in descriptions:
                schema["description"] = descriptions[name]

            enum_source = spec.enums.get(name)
            if enum_source is not None:
                values = list(enum_source.resolve(context))
                if strict and not values:
                    raise SchemaError(
                        f"{spec.name}.{name}: enum resolved to no values for {context!r}"
                    )
                if values:
                    schema["enum"] = values
                if enum_source.description:
                    schema["description"] = enum_source.description

            properties[name] = schema
            if param.default is inspect.Parameter.empty:
                required.append(name)

        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                },
            }
        )
        registry[spec.name] = bound

    return schemas, registry


def _bind(fn: Callable[..., Any], context: Any) -> Callable[..., Any]:
    """If `fn` is an unbound method and we have a context, bind it."""
    if context is not None and inspect.isfunction(fn):
        params = list(inspect.signature(fn).parameters)
        if params and params[0] in {"self", "context"}:
            return types.MethodType(fn, context)  # type: ignore[return-value]
    return fn


def validate_arguments(
    registry: Mapping[str, Callable[..., Any]],
    name: str,
    arguments: Mapping[str, Any],
) -> ToolResult:
    """Check that a call names a real tool and every enum value is allowed.

    Providers are not obliged to honour JSON-schema `enum`, so this is the
    enforcement point that matters. It is deliberately separate from the tool
    body: the body can assume its arguments already passed this gate.
    """
    fn = registry.get(name)
    if fn is None:
        return ToolResult.failure(f"unknown tool: {name}")

    spec = getattr(fn, "__tool__", None) or getattr(getattr(fn, "__func__", None), "__tool__", None)
    if spec is None:
        return ToolResult.failure(f"{name} is not a tool")

    signature = inspect.signature(fn)
    allowed = {p for p in signature.parameters if p not in {"self", "context"}}
    for key in arguments:
        if key not in allowed:
            return ToolResult.failure(f"{name}: unexpected argument {key!r}")
    for pname, param in signature.parameters.items():
        if pname in {"self", "context"}:
            continue
        if param.default is inspect.Parameter.empty and pname not in arguments:
            return ToolResult.failure(f"{name}: missing argument {pname!r}")

    source = spec.enums
    for arg, enum_source in source.items():
        if arg not in arguments:
            continue
        values = set(enum_source.resolve(getattr(fn, "__self__", None)))
        if values and arguments[arg] not in values:
            return ToolResult.failure(
                f"{name}.{arg}: {arguments[arg]!r} is not allowed here "
                f"(expected one of {sorted(values)})"
            )

    return ToolResult.success()


def call_tool(
    registry: Mapping[str, Callable[..., Any]],
    name: str,
    arguments: Mapping[str, Any],
) -> ToolResult:
    """Validate then execute, converting exceptions into a ToolResult."""
    verdict = validate_arguments(registry, name, arguments)
    if not verdict.ok:
        return verdict

    fn = registry[name]
    try:
        result = fn(**dict(arguments))
    except TypeError as exc:
        return ToolResult.failure(f"{name}: {exc}")
    except Exception as exc:  # noqa: BLE001 - tool boundary must not raise
        return ToolResult.failure(f"{name} failed: {type(exc).__name__}: {exc}")

    if isinstance(result, ToolResult):
        return result
    return ToolResult.success(result)
