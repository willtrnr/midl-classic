"""Classic MIDL Parser - A complete parser for classic Microsoft Interface Definition Language files.

(Parses classic MIDL, used for COM/RPC/DirectX. MIDL 3.0 / MIDLRT is not supported.)

Usage:
    from midl_classic import parse_file, parse_string

    # Parse from file
    midl = parse_file("path/to/file.idl")

    # Parse from string
    midl = parse_string('''
        typedef struct Point { long x; long y; } POINT;
    ''')

    # Access parsed elements
    for iface in midl.interfaces:
        print(f"Interface: {iface.name} (UUID: {iface.uuid})")
        for method in iface.methods:
            print(f"  {method.name}({len(method.params)} params)")
"""

__version__ = "0.1.0"

from .ast_nodes import (
    # Core types
    MidlFile, TypeSpec, PointerLevel, Attribute, AttributeName,
    # Parsed SAL annotation
    ParsedAnnotation, AnnotationDirection, AnnotationAccess, AnnotationKind,
    parse_sal_annotation,
    # Expressions
    IntegerLiteral, FloatLiteral, StringLiteral, IdentifierRef,
    BinaryOp, UnaryOp, ParenExpr, Expression,
    # Array
    ArrayDimension,
    # Top-level elements
    ImportStatement, CppQuote, PreprocessorDirective, Constant,
    EnumDef, EnumMember,
    StructDef, StructField, AnonymousUnion, AnonymousStruct,
    UnionDef, UnionCase,
    TypeAlias, FuncPointerTypedef, FuncPointerParam,
    InterfaceDef, InterfaceTypedef, Method, MethodParam,
    ForwardDecl,
    LibraryDef, CoclassDef, CoclassInterface, ImportLib,
)
from .errors import MidlError, ParseError, LexError
from .lexer import Lexer
from .parser import Parser


def parse_string(source: str, filename: str = "<string>") -> MidlFile:
    """Parse MIDL source text into a MidlFile AST.

    Args:
        source: The MIDL source code as a string.
        filename: Optional filename for error messages.

    Returns:
        A MidlFile containing all parsed elements.

    Raises:
        ParseError: If the source contains syntax errors.
        LexError: If the source contains invalid tokens.
    """
    lexer = Lexer(source, filename)
    tokens = lexer.tokenize()
    parser = Parser(tokens, filename)
    return parser.parse()


def parse_file(path: str, encoding: str | None = None) -> MidlFile:
    """Parse an IDL file from disk.

    Args:
        path: Path to the .idl file.
        encoding: File encoding to use.

    Returns:
        A MidlFile containing all parsed elements.

    Raises:
        ParseError: If the file contains syntax errors.
        LexError: If the file contains invalid tokens.
        FileNotFoundError: If the file does not exist.
    """
    with open(path, "r", encoding=encoding) as f:
        source = f.read()
    return parse_string(source, filename=path)


__all__ = [
    # Public API
    "__version__",
    "parse_string", "parse_file",
    # Core types
    "MidlFile", "TypeSpec", "PointerLevel", "Attribute", "AttributeName",
    # Parsed SAL annotation
    "ParsedAnnotation", "AnnotationDirection", "AnnotationAccess", "AnnotationKind",
    "parse_sal_annotation",
    # Expressions
    "IntegerLiteral", "FloatLiteral", "StringLiteral", "IdentifierRef",
    "BinaryOp", "UnaryOp", "ParenExpr", "Expression",
    # Array
    "ArrayDimension",
    # Elements
    "ImportStatement", "CppQuote", "PreprocessorDirective", "Constant",
    "EnumDef", "EnumMember",
    "StructDef", "StructField", "AnonymousUnion", "AnonymousStruct",
    "UnionDef", "UnionCase",
    "TypeAlias", "FuncPointerTypedef", "FuncPointerParam",
    "InterfaceDef", "InterfaceTypedef", "Method", "MethodParam",
    "ForwardDecl",
    "LibraryDef", "CoclassDef", "CoclassInterface", "ImportLib",
    # Errors
    "MidlError", "ParseError", "LexError",
]
