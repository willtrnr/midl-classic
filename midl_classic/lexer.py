"""Tokenizer for MIDL source files."""

from __future__ import annotations

from .tokens import Token, TokenType, KEYWORDS
from .errors import LexError


class Lexer:
    """Single-pass lexer that tokenizes MIDL source text."""

    def __init__(self, source: str, filename: str = "<string>"):
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: list[Token] = []
        self._in_preprocessor = False

    def _error(self, msg: str) -> LexError:
        return LexError(msg, self.filename, self.line, self.column)

    def _peek(self, offset: int = 0) -> str:
        p = self.pos + offset
        if p < len(self.source):
            return self.source[p]
        return "\0"

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _skip_whitespace(self) -> None:
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == "\n":
                if self._in_preprocessor:
                    # Emit newline token to end preprocessor line
                    self.tokens.append(Token(TokenType.NEWLINE, "\n", self.line, self.column))
                    self._in_preprocessor = False
                self._advance()
            elif ch in (" ", "\t", "\r"):
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                self._skip_line_comment()
            elif ch == "/" and self._peek(1) == "*":
                self._skip_block_comment()
            else:
                break

    def _skip_line_comment(self) -> None:
        # Skip //
        self._advance()
        self._advance()
        while self.pos < len(self.source) and self.source[self.pos] != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        # Skip /*
        self._advance()
        self._advance()
        while self.pos < len(self.source):
            if self.source[self.pos] == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return
            self._advance()
        raise self._error("Unterminated block comment")

    def _read_string(self) -> Token:
        start_line = self.line
        start_col = self.column
        self._advance()  # skip opening "
        chars: list[str] = []
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == "\\":
                self._advance()
                if self.pos < len(self.source):
                    esc = self._advance()
                    if esc == "n":
                        chars.append("\n")
                    elif esc == "t":
                        chars.append("\t")
                    elif esc == "\\":
                        chars.append("\\")
                    elif esc == '"':
                        chars.append('"')
                    elif esc == "'":
                        chars.append("'")
                    elif esc == "0":
                        chars.append("\0")
                    else:
                        chars.append("\\")
                        chars.append(esc)
            elif ch == '"':
                self._advance()
                return Token(TokenType.STRING, "".join(chars), start_line, start_col)
            else:
                chars.append(self._advance())
        raise self._error("Unterminated string literal")

    def _read_number(self) -> Token:
        start_line = self.line
        start_col = self.column
        start_pos = self.pos

        if self.source[self.pos] == "0" and self.pos + 1 < len(self.source):
            next_ch = self.source[self.pos + 1].lower()
            if next_ch == "x":
                # Hex literal: 0x[0-9a-f]+ [suffix]
                self._advance()  # 0
                self._advance()  # x
                hex_start = self.pos
                while self.pos < len(self.source) and self.source[self.pos] in "0123456789abcdefABCDEF":
                    self._advance()
                if self.pos == hex_start:
                    raise self._error("Expected hex digits after 0x")
                int_val = int(self.source[hex_start:self.pos], 16)
                suffix = self._read_int_suffix()
                raw = self.source[start_pos:self.pos]
                return Token(TokenType.INTEGER, raw, start_line, start_col,
                             int_value=int_val, suffix=suffix)

        # Decimal or octal or float
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            self._advance()

        # Check for float
        if self.pos < len(self.source) and self.source[self.pos] == ".":
            self._advance()
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                self._advance()
            self._read_float_exponent()
            suffix = ""
            if self.pos < len(self.source) and self.source[self.pos].lower() in "fl":
                suffix = self.source[self.pos]
                self._advance()
            raw = self.source[start_pos:self.pos]
            return Token(TokenType.FLOAT, raw, start_line, start_col,
                         float_value=float(raw.rstrip("fFlL")))
        elif self.pos < len(self.source) and self.source[self.pos].lower() == "e":
            # Could be float exponent - but only if followed by digit, or +/- then digit
            next_after_e = self._peek(1)
            is_exponent = next_after_e in "0123456789"
            if not is_exponent and next_after_e in "+-":
                # Check there's a digit after the sign
                p2 = self.pos + 2
                is_exponent = p2 < len(self.source) and self.source[p2].isdigit()
            if is_exponent:
                self._read_float_exponent()
                suffix = ""
                if self.pos < len(self.source) and self.source[self.pos].lower() in "fl":
                    suffix = self.source[self.pos]
                    self._advance()
                raw = self.source[start_pos:self.pos]
                return Token(TokenType.FLOAT, raw, start_line, start_col,
                             float_value=float(raw.rstrip("fFlL")))

        # Plain integer
        digit_str = self.source[start_pos:self.pos]
        int_val = int(digit_str) if digit_str else 0
        suffix = self._read_int_suffix()
        raw = self.source[start_pos:self.pos]
        return Token(TokenType.INTEGER, raw, start_line, start_col,
                     int_value=int_val, suffix=suffix)

    def _read_int_suffix(self) -> str:
        suffix = ""
        while self.pos < len(self.source) and self.source[self.pos].lower() in "ul":
            suffix += self.source[self.pos]
            self._advance()
        return suffix

    def _read_float_exponent(self) -> None:
        if self.pos < len(self.source) and self.source[self.pos].lower() == "e":
            self._advance()
            if self.pos < len(self.source) and self.source[self.pos] in "+-":
                self._advance()
            while self.pos < len(self.source) and self.source[self.pos].isdigit():
                self._advance()

    def _is_float_ahead(self) -> bool:
        """Check if the current number will be a float (has a dot after digits)."""
        p = self.pos
        while p < len(self.source) and self.source[p].isdigit():
            p += 1
        return p < len(self.source) and self.source[p] == "."

    def _read_identifier(self) -> Token:
        start_line = self.line
        start_col = self.column
        start_pos = self.pos
        while self.pos < len(self.source) and (self.source[self.pos].isalnum() or self.source[self.pos] == "_"):
            self._advance()
        word = self.source[start_pos:self.pos]

        # Check for wide string prefix L"..."
        if word == "L" and self.pos < len(self.source) and self.source[self.pos] == '"':
            # Read the string and prepend L
            str_tok = self._read_string()
            return Token(TokenType.STRING, str_tok.value, start_line, start_col)

        # Check keyword
        tt = KEYWORDS.get(word)
        if tt is not None:
            return Token(tt, word, start_line, start_col)
        return Token(TokenType.IDENT, word, start_line, start_col)

    def _read_preprocessor_rest(self) -> None:
        """After reading # and directive name, read rest of line as STRING token."""
        start_line = self.line
        start_col = self.column
        # Skip whitespace on same line
        while self.pos < len(self.source) and self.source[self.pos] in " \t":
            self._advance()
        start_pos = self.pos
        while self.pos < len(self.source) and self.source[self.pos] != "\n":
            self._advance()
        content = self.source[start_pos:self.pos].rstrip()
        if content:
            self.tokens.append(Token(TokenType.STRING, content, start_line, start_col))

    def tokenize(self) -> list[Token]:
        """Tokenize the entire source and return a list of Tokens."""
        self.tokens = []
        while self.pos < len(self.source):
            self._skip_whitespace()
            if self.pos >= len(self.source):
                break

            ch = self.source[self.pos]
            start_line = self.line
            start_col = self.column

            # Preprocessor directive
            if ch == "#" and not self._in_preprocessor:
                self._advance()
                self.tokens.append(Token(TokenType.HASH, "#", start_line, start_col))
                self._in_preprocessor = True
                # Skip whitespace
                while self.pos < len(self.source) and self.source[self.pos] in " \t":
                    self._advance()
                # Read directive name
                if self.pos < len(self.source) and (self.source[self.pos].isalpha() or self.source[self.pos] == "_"):
                    tok = self._read_identifier()
                    self.tokens.append(tok)
                    # Read rest of line as content
                    self._read_preprocessor_rest()
                continue

            # String literal
            if ch == '"':
                self.tokens.append(self._read_string())
                continue

            # Single-quoted char (rare but possible)
            if ch == "'":
                self._advance()
                chars: list[str] = []
                while self.pos < len(self.source) and self.source[self.pos] != "'":
                    if self.source[self.pos] == "\\":
                        self._advance()
                        if self.pos < len(self.source):
                            chars.append(self._advance())
                    else:
                        chars.append(self._advance())
                if self.pos < len(self.source):
                    self._advance()  # closing '
                self.tokens.append(Token(TokenType.STRING, "".join(chars), start_line, start_col))
                continue

            # Number
            if ch.isdigit():
                self.tokens.append(self._read_number())
                continue

            # Identifier or keyword
            if ch.isalpha() or ch == "_":
                self.tokens.append(self._read_identifier())
                continue

            # Multi-character operators
            if ch == "<" and self._peek(1) == "<":
                self._advance()
                self._advance()
                self.tokens.append(Token(TokenType.LSHIFT, "<<", start_line, start_col))
                continue
            if ch == ">" and self._peek(1) == ">":
                self._advance()
                self._advance()
                self.tokens.append(Token(TokenType.RSHIFT, ">>", start_line, start_col))
                continue
            if ch == "." and self._peek(1) == "." and self._peek(2) == ".":
                self._advance()
                self._advance()
                self._advance()
                self.tokens.append(Token(TokenType.ELLIPSIS, "...", start_line, start_col))
                continue

            # Single-character tokens
            single_map = {
                "{": TokenType.LBRACE,
                "}": TokenType.RBRACE,
                "(": TokenType.LPAREN,
                ")": TokenType.RPAREN,
                "[": TokenType.LBRACKET,
                "]": TokenType.RBRACKET,
                ";": TokenType.SEMICOLON,
                ",": TokenType.COMMA,
                ":": TokenType.COLON,
                "*": TokenType.STAR,
                ".": TokenType.DOT,
                "|": TokenType.PIPE_OP,
                "+": TokenType.PLUS,
                "-": TokenType.MINUS,
                "~": TokenType.TILDE,
                "&": TokenType.AMPERSAND,
                "^": TokenType.CARET,
                "=": TokenType.EQUALS,
                "/": TokenType.SLASH,
                "%": TokenType.PERCENT,
                "!": TokenType.BANG,
                "?": TokenType.QUESTION,
            }
            if ch in single_map:
                self._advance()
                self.tokens.append(Token(single_map[ch], ch, start_line, start_col))
                continue

            # Skip angle brackets (used in some #include <...>)
            if ch in "<>":
                self._advance()
                continue

            # Unknown character - skip
            self._advance()

        # Emit EOF
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return self.tokens
