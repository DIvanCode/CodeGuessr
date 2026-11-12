"""Extract named functions and syntactic calls from a round's source files."""

from pathlib import PurePosixPath

from tree_sitter import Node
from tree_sitter_language_pack import get_parser

LANGUAGES = {
    ".c": "c", ".h": "cpp", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp",
    ".hh": "cpp", ".hpp": "cpp", ".m": "objc", ".mm": "objc",
    ".cs": "csharp", ".go": "go", ".rs": "rust", ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala", ".swift": "swift",
    ".py": "python", ".rb": "ruby", ".php": "php",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".lua": "lua",
    ".sh": "bash", ".bash": "bash",
}
DEFINITIONS = {
    "function_definition", "function_declaration", "generator_function_declaration",
    "function_item", "method_definition", "method_declaration", "constructor_declaration",
    "local_function_statement", "method", "singleton_method",
}
FUNCTION_VALUES = {"arrow_function", "function_expression", "generator_function"}
CALLS = {
    "call", "call_expression", "function_call", "function_call_expression",
    "invocation_expression", "method_invocation", "member_call_expression",
    "nullsafe_member_call_expression", "scoped_call_expression", "command",
}
CALL_TARGETS = {
    "identifier", "simple_identifier", "name", "qualified_name", "command_name",
    "attribute", "member_expression", "member_access_expression", "field_expression",
    "selector_expression", "qualified_identifier", "scoped_identifier",
    "navigation_expression", "dot_index_expression", "method_index_expression",
    "variable_name",
}


def text_of(node: Node) -> str:
    return node.text.decode("utf-8")


def definition_name(node: Node) -> Node | None:
    if node.type in FUNCTION_VALUES:
        parent = node.parent
        if parent is not None and parent.type in {"variable_declarator", "pair"}:
            return parent.child_by_field_name("name") or parent.child_by_field_name("key")
        return None
    name = node.child_by_field_name("name")
    if name is None and node.type == "function_declaration":
        # Kotlin's function name has no field label.
        name = next((child for child in node.named_children if child.type == "simple_identifier"), None)
    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        name = declarator
        declarator = declarator.child_by_field_name("declarator")
    return name


def call_name(node: Node) -> str | None:
    target = node.child_by_field_name("function") or node.child_by_field_name("name")
    target = target or node.child_by_field_name("method") or node.named_child(0)
    if target is None or target.type not in CALL_TARGETS:
        return None
    receiver = (
        node.child_by_field_name("receiver")
        or node.child_by_field_name("object")
        or node.child_by_field_name("scope")
    )
    if receiver is None:
        return text_of(target)
    separator = {
        "member_call_expression": "->",
        "nullsafe_member_call_expression": "?->",
        "scoped_call_expression": "::",
    }.get(node.type, ".")
    return f"{text_of(receiver)}{separator}{text_of(target)}"


def extract_functions(path: str, source: str) -> list[dict]:
    language = LANGUAGES.get(PurePosixPath(path).suffix.casefold())
    if language is None:
        return []
    # These grammars share syntax and can refer to definitions in each other's files.
    family = {"c": "cpp", "javascript": "typescript", "tsx": "typescript"}.get(language, language)
    source_bytes = source.replace("\r\n", "\n").replace("\r", "\n").encode()
    root = get_parser(language).parse(source_bytes).root_node
    functions = []
    pending = [(root, None)]
    while pending:
        node, caller = pending.pop()
        if node.type in DEFINITIONS or node.type in FUNCTION_VALUES:
            caller = None
            name = definition_name(node)
            if name is not None and not name.is_missing:
                caller = {
                    "name": text_of(name), "language": family,
                    "start": node.start_point.row + 1,
                    "end": max(node.start_point.row + 1, node.end_point.row + bool(node.end_point.column)),
                    "calls": [],
                }
                functions.append(caller)
        elif caller is not None and node.type in CALLS:
            name = call_name(node)
            if name is not None:
                caller["calls"].append(name)
        pending.extend((child, caller) for child in reversed(node.named_children))
    return functions
