"""MIDL file dump tool - prints all parsed elements with rich annotations.

Installed as the ``midl-dump`` console script.

Usage:
    midl-dump <file.idl> [--filter TYPE] [--verbose]

Examples:
    midl-dump dxgi.idl
    midl-dump d3d11.idl --filter interfaces
    midl-dump d3d12.idl --filter structs --verbose
"""

from __future__ import annotations

import argparse
import sys

from . import (
    parse_file, MidlFile,
    ImportStatement, CppQuote, PreprocessorDirective, Constant,
    EnumDef, EnumMember,
    StructDef, StructField, AnonymousUnion, AnonymousStruct,
    UnionDef, UnionCase,
    TypeAlias, FuncPointerTypedef,
    InterfaceDef, Method, MethodParam,
    ForwardDecl, LibraryDef, CoclassDef, ImportLib,
    TypeSpec, Attribute, AttributeName,
    IntegerLiteral, FloatLiteral, StringLiteral, IdentifierRef,
    BinaryOp, UnaryOp, ParenExpr, Expression, ArrayDimension,
    ParsedAnnotation, AnnotationDirection, AnnotationAccess, AnnotationKind,
)


def format_type(ts: TypeSpec) -> str:
    """Format a TypeSpec into a readable string."""
    return ts.format()


def format_expression(expr: Expression) -> str:
    """Format an expression into a readable string."""
    if isinstance(expr, IntegerLiteral):
        if expr.base == 16:
            return f"0x{expr.value:x}"
        return str(expr.value)
    elif isinstance(expr, FloatLiteral):
        return str(expr.value)
    elif isinstance(expr, StringLiteral):
        return f'"{expr.value}"'
    elif isinstance(expr, IdentifierRef):
        return expr.name
    elif isinstance(expr, BinaryOp):
        left = format_expression(expr.left)
        right = format_expression(expr.right)
        return f"{left} {expr.op} {right}"
    elif isinstance(expr, UnaryOp):
        return f"{expr.op}{format_expression(expr.operand)}"
    elif isinstance(expr, ParenExpr):
        return f"({format_expression(expr.inner)})"
    return str(expr)


def format_array_dims(dims: list[ArrayDimension]) -> str:
    """Format array dimensions."""
    parts = []
    for d in dims:
        if d.size is None:
            parts.append("[]")
        else:
            parts.append(f"[{format_expression(d.size)}]")
    return "".join(parts)


def indent(text: str, level: int = 1) -> str:
    """Indent text by level * 4 spaces."""
    prefix = "    " * level
    return "\n".join(prefix + line for line in text.split("\n"))


def format_parsed_annotation(ann: ParsedAnnotation) -> str:
    """Format a ParsedAnnotation into a compact readable string."""
    parts = []

    # Kind + direction
    if ann.kind == AnnotationKind.COM_OUTPTR:
        parts.append("COM outptr")
    elif ann.kind == AnnotationKind.OUTPTR:
        parts.append("outptr")
    elif ann.kind == AnnotationKind.RANGE:
        parts.append("range")
    elif ann.kind == AnnotationKind.NUL_TERMINATED:
        parts.append("nul-terminated")
    elif ann.kind == AnnotationKind.FIELD_SIZE:
        parts.append("field_size")

    if ann.optional:
        parts.append("optional")
    if ann.may_be_null:
        parts.append("may_be_null")

    # Buffer access
    if ann.access == AnnotationAccess.READS:
        parts.append(f"reads({ann.size_expr})")
    elif ann.access == AnnotationAccess.READS_BYTES:
        parts.append(f"reads_bytes({ann.size_expr})")
    elif ann.access == AnnotationAccess.WRITES:
        parts.append(f"writes({ann.size_expr})")
    elif ann.access == AnnotationAccess.WRITES_BYTES:
        parts.append(f"writes_bytes({ann.size_expr})")
    elif ann.access == AnnotationAccess.WRITES_TO:
        parts.append(f"writes_to(capacity={ann.capacity_expr}, count={ann.size_expr})")
    elif ann.access == AnnotationAccess.WRITES_BYTES_TO:
        parts.append(f"writes_bytes_to(capacity={ann.capacity_expr}, count={ann.size_expr})")
    elif ann.access == AnnotationAccess.UPDATES_BYTES:
        parts.append(f"updates_bytes({ann.size_expr})")
    elif ann.access == AnnotationAccess.FIELD_SIZE:
        qual = "full " if ann.full else ""
        parts.append(f"elements({qual}{ann.size_expr})")
    elif ann.access == AnnotationAccess.FIELD_SIZE_BYTES:
        qual = "full " if ann.full else ""
        parts.append(f"bytes({qual}{ann.size_expr})")

    # Range
    if ann.range_min is not None:
        parts.append(f"[{ann.range_min} .. {ann.range_max}]")

    return ", ".join(parts) if parts else ""


def format_param_info(p: MethodParam) -> str:
    """Format a parameter with all its annotation details."""
    parts = []

    # Direction
    direction = p.direction_str()
    if direction:
        parts.append(f"[{direction}]")

    # Type
    parts.append(format_type(p.type_spec))

    # Name
    if p.name:
        parts.append(p.name)

    # Array dimensions
    if p.array_dimensions:
        parts[-1] += format_array_dims(p.array_dimensions)

    result = " ".join(parts)

    # Collect structured details
    details = []

    # IDL attributes first (these are from the [attr] blocks, not SAL)
    if p.is_string:
        details.append("string")
    if p.size_is:
        details.append(f"size_is({p.size_is})")
    if p.max_is:
        details.append(f"max_is({p.max_is})")
    if p.length_is:
        details.append(f"length_is({p.length_is})")
    if p.iid_is:
        details.append(f"iid_is({p.iid_is})")

    # Parsed SAL annotation
    ann = p.parsed_annotation
    if ann:
        ann_str = format_parsed_annotation(ann)
        if ann_str:
            details.append(ann_str)

    if details:
        result += "  {" + ", ".join(details) + "}"

    return result


# ---------------------------------------------------------------------------
# Dump functions
# ---------------------------------------------------------------------------

def dump_imports(midl: MidlFile) -> None:
    imports = midl.imports
    if not imports:
        return
    print(f"\n--- Imports ({len(imports)}) ---")
    for imp in imports:
        print(f"  import \"{imp.path}\"")


def dump_constants(midl: MidlFile, verbose: bool = False) -> None:
    constants = midl.constants
    if not constants:
        return
    print(f"\n--- Constants ({len(constants)}) ---")
    for c in constants:
        val = format_expression(c.value)
        extra = ""
        if isinstance(c.value, IntegerLiteral) and c.value.base == 16:
            extra = f"  ({c.value.value})"
        print(f"  const {format_type(c.type_spec)} {c.name} = {val}{extra}")


def dump_enums(midl: MidlFile, verbose: bool = False) -> None:
    enums = midl.enums
    if not enums:
        return
    print(f"\n--- Enums ({len(enums)}) ---")
    for e in enums:
        tag = f" (tag: {e.tag})" if e.tag and e.tag != e.name else ""
        print(f"  enum {e.name}{tag}: {len(e.members)} members")
        for mem in e.members:
            val = ""
            if mem.value is not None:
                val = f" = {format_expression(mem.value)}"
                if isinstance(mem.value, IntegerLiteral) and mem.value.base == 16:
                    val += f"  ({mem.value.value})"
            print(f"    {mem.name}{val}")


def format_struct_field(m: StructField) -> str:
    """Format a struct field with type, name, array dims, bitfield, and annotation."""
    type_str = format_type(m.type_spec)
    dims = format_array_dims(m.array_dimensions) if m.array_dimensions else ""
    bitfield = f" : {m.bitfield_width}" if m.bitfield_width is not None else ""
    ann_str = ""
    ann = m.parsed_annotation
    if ann:
        formatted = format_parsed_annotation(ann)
        if formatted:
            ann_str = f"  {{{formatted}}}"
    return f"{type_str} {m.name}{dims}{bitfield}{ann_str}"


def dump_struct_members(members: list, level: int = 2) -> None:
    """Recursively dump struct/union members."""
    prefix = "    " * level
    for m in members:
        if isinstance(m, StructField):
            print(f"{prefix}{format_struct_field(m)}")
        elif isinstance(m, AnonymousUnion):
            name_str = f" {m.name}" if m.name else ""
            print(f"{prefix}union{name_str} {{")
            dump_struct_members(m.members, level + 1)
            print(f"{prefix}}}")
        elif isinstance(m, AnonymousStruct):
            name_str = f" {m.name}" if m.name else ""
            print(f"{prefix}struct{name_str} {{")
            dump_struct_members(m.members, level + 1)
            print(f"{prefix}}}")


def dump_structs(midl: MidlFile, verbose: bool = False) -> None:
    structs = midl.structs
    if not structs:
        return
    print(f"\n--- Structs ({len(structs)}) ---")
    for s in structs:
        tag = f" (tag: {s.tag})" if s.tag and s.tag != s.name else ""
        aliases = f" aliases: {', '.join(s.aliases)}" if s.aliases else ""
        print(f"  struct {s.name}{tag}{aliases}")
        dump_struct_members(s.members, 2)


def dump_unions(midl: MidlFile, verbose: bool = False) -> None:
    unions = midl.unions
    if not unions:
        return
    print(f"\n--- Unions ({len(unions)}) ---")
    for u in unions:
        tag = f" (tag: {u.tag})" if u.tag and u.tag != u.name else ""
        print(f"  union {u.name}{tag}:")
        if u.switch_type:
            print(f"    switch({format_type(u.switch_type)} {u.switch_name or ''})")
        for c in u.cases:
            vals = ", ".join(format_expression(v) for v in c.case_values)
            if c.is_default:
                label = "default"
            else:
                label = f"case({vals})"
            if c.member:
                if isinstance(c.member, StructField):
                    print(f"    [{label}] {format_struct_field(c.member)}")
                else:
                    name_str = f" {c.member.name}" if c.member.name else ""
                    print(f"    [{label}] struct{name_str} {{")
                    dump_struct_members(c.member.members, 3)
                    print(f"    }}")
            else:
                print(f"    [{label}] (empty)")
        for m in u.members:
            if isinstance(m, StructField):
                print(f"    {format_struct_field(m)}")


def dump_typedefs(midl: MidlFile, verbose: bool = False) -> None:
    typedefs = midl.typedefs
    func_ptrs = [e for e in midl.elements if isinstance(e, FuncPointerTypedef)]
    if not typedefs and not func_ptrs:
        return
    total = len(typedefs) + len(func_ptrs)
    print(f"\n--- Typedefs ({total}) ---")
    for t in typedefs:
        attrs_str = ""
        if t.attributes:
            attrs_str = f" [{', '.join(a.raw_name for a in t.attributes)}]"
        aliases = f", aliases: {', '.join(t.aliases)}" if t.aliases else ""
        print(f"  typedef{attrs_str} {format_type(t.type_spec)} {t.name}{aliases}")
    for fp in func_ptrs:
        params = ", ".join(
            f"{format_type(p.type_spec)} {p.name or ''}" for p in fp.params
        )
        cc = f" {fp.calling_convention}" if fp.calling_convention else ""
        print(f"  typedef {format_type(fp.return_type)} ({cc}*{fp.name})({params})")


def dump_interfaces(midl: MidlFile, verbose: bool = False) -> None:
    interfaces = midl.interfaces
    if not interfaces:
        return
    print(f"\n--- Interfaces ({len(interfaces)}) ---")
    for iface in interfaces:
        parent = f" : {iface.parent}" if iface.parent else ""
        uuid = iface.uuid or "none"
        attrs = []
        if iface.is_object:
            attrs.append("object")
        if iface.is_local:
            attrs.append("local")
        pd = iface.pointer_default
        if pd:
            attrs.append(f"pointer_default({pd})")
        attrs_str = f"  [{', '.join(attrs)}]" if attrs else ""
        print(f"  interface {iface.name}{parent}")
        print(f"    uuid: {uuid}{attrs_str}")

        # Inline typedefs
        if iface.typedefs:
            print(f"    typedefs: {len(iface.typedefs)}")
            if verbose:
                for td in iface.typedefs:
                    inner = td.typedef
                    print(f"      {type(inner).__name__}: {inner.name}")

        # Methods
        print(f"    methods: {len(iface.methods)}")
        for method in iface.methods:
            method_attrs = ""
            if method.attributes:
                ma = ", ".join(
                    f"{a.raw_name}({a.value})" if a.value else a.raw_name
                    for a in method.attributes
                )
                method_attrs = f" [{ma}]"

            ret = format_type(method.return_type)
            print(f"      {ret} {method.name}({len(method.params)} params){method_attrs}")

            if True:  # Always show parameter details
                for p in method.params:
                    info = format_param_info(p)
                    print(f"        {info}")


def dump_forward_decls(midl: MidlFile) -> None:
    fds = midl.forward_decls
    if not fds:
        return
    print(f"\n--- Forward Declarations ({len(fds)}) ---")
    for fd in fds:
        print(f"  {fd.kind} {fd.name}")


def dump_libraries(midl: MidlFile, verbose: bool = False) -> None:
    libs = midl.libraries
    if not libs:
        return
    print(f"\n--- Libraries ({len(libs)}) ---")
    for lib in libs:
        uuid = ""
        for a in lib.attributes:
            if a.name == AttributeName.UUID:
                uuid = f" uuid={a.value}"
        print(f"  library {lib.name}{uuid}")
        for elem in lib.elements:
            if isinstance(elem, ImportLib):
                print(f"    importlib(\"{elem.path}\")")
            elif isinstance(elem, ForwardDecl):
                print(f"    {elem.kind} {elem.name} (forward)")
            elif isinstance(elem, CoclassDef):
                dump_coclass(elem, level=2)


def dump_coclass(cc: CoclassDef, level: int = 1) -> None:
    prefix = "    " * level
    uuid = ""
    for a in cc.attributes:
        if a.name == AttributeName.UUID:
            uuid = f" uuid={a.value}"
    other_attrs = [a.raw_name for a in cc.attributes
                   if a.name not in (AttributeName.UUID,)]
    attrs_str = f" [{', '.join(other_attrs)}]" if other_attrs else ""
    print(f"{prefix}coclass {cc.name}{uuid}{attrs_str}")
    for ci in cc.interfaces:
        ci_attrs = ", ".join(a.raw_name for a in ci.attributes)
        if ci_attrs:
            ci_attrs = f"[{ci_attrs}] "
        print(f"{prefix}  {ci_attrs}{ci.name}")


def dump_coclasses(midl: MidlFile, verbose: bool = False) -> None:
    ccs = midl.coclasses
    if not ccs:
        return
    print(f"\n--- Coclasses ({len(ccs)}) ---")
    for cc in ccs:
        dump_coclass(cc)


def dump_cpp_quotes(midl: MidlFile) -> None:
    cqs = midl.cpp_quotes
    if not cqs:
        return
    print(f"\n--- cpp_quote directives ({len(cqs)}) ---")
    for cq in cqs:
        text = cq.text
        if len(text) > 100:
            text = text[:97] + "..."
        print(f"  cpp_quote(\"{text}\")")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def dump_file(midl: MidlFile, filter_type: str = "all", verbose: bool = False) -> None:
    """Dump all parsed elements from a MIDL file."""
    print(f"=== {midl.filename} ===")
    print(f"Total elements: {len(midl.elements)}")

    if filter_type in ("all", "imports"):
        dump_imports(midl)
    if filter_type in ("all", "constants"):
        dump_constants(midl, verbose)
    if filter_type in ("all", "enums"):
        dump_enums(midl, verbose)
    if filter_type in ("all", "structs"):
        dump_structs(midl, verbose)
    if filter_type in ("all", "unions"):
        dump_unions(midl, verbose)
    if filter_type in ("all", "typedefs"):
        dump_typedefs(midl, verbose)
    if filter_type in ("all", "interfaces"):
        dump_interfaces(midl, verbose)
    if filter_type in ("all", "forward_decls"):
        dump_forward_decls(midl)
    if filter_type in ("all", "libraries"):
        dump_libraries(midl, verbose)
    if filter_type in ("all", "coclasses"):
        dump_coclasses(midl, verbose)
    if filter_type in ("all", "cpp_quotes") and verbose:
        dump_cpp_quotes(midl)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump MIDL file contents with rich annotations.",
        epilog="Example: python midl_dump.py examples/dxgi.idl --filter interfaces -v",
    )
    parser.add_argument("file", help="Path to .idl file")
    parser.add_argument(
        "--filter", "-f",
        choices=["all", "imports", "constants", "enums", "structs", "unions",
                 "typedefs", "interfaces", "forward_decls", "libraries",
                 "coclasses", "cpp_quotes"],
        default="all",
        help="Filter to show only specific element types (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed information (enum values, struct fields, etc.)",
    )
    parser.add_argument(
        "--encoding", "-e",
        default="utf-8-sig",
        help="Encoding to use when reading the file (default: utf-8-sig)"
    )
    args = parser.parse_args()

    try:
        midl = parse_file(args.file, args.encoding)
    except FileNotFoundError:
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    dump_file(midl, args.filter, args.verbose)


if __name__ == "__main__":
    main()
