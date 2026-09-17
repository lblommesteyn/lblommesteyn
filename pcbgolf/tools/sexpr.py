"""Minimal, fast S-expression parser for KiCad files."""
import re
import math as _math

class Q(str):
    """A string that was quoted in the source, so it must be re-quoted."""
    __slots__ = ()


class Node(list):
    """An s-expr node: Node[0] is the tag (str), rest are atoms/Nodes."""
    @property
    def tag(self):
        return self[0] if self and isinstance(self[0], str) else None

    def find_all(self, tag):
        return [c for c in self[1:] if isinstance(c, Node) and c.tag == tag]

    def find(self, tag):
        for c in self[1:]:
            if isinstance(c, Node) and c.tag == tag:
                return c
        return None

    def val(self, tag, idx=1, default=None):
        n = self.find(tag)
        if n is None or len(n) <= idx:
            return default
        return n[idx]

    def descend(self, tag):
        """Recursively yield every node with the given tag."""
        stack = [self]
        while stack:
            n = stack.pop()
            for c in n[1:]:
                if isinstance(c, Node):
                    if c.tag == tag:
                        yield c
                    stack.append(c)

_TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+')

_ESC = {'\\n': '\n', '\\t': '\t', '\\r': '\r', '\\"': '"', '\\\\': '\\'}

def _unescape(s):
    out = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            pair = s[i:i+2]
            if pair in _ESC:
                out.append(_ESC[pair]); i += 2; continue
        out.append(s[i]); i += 1
    return ''.join(out)

def _escape(s):
    return (s.replace('\\', '\\\\').replace('"', '\\"')
             .replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r'))

def fmt_num(v):
    """KiCad writes the shortest round-tripping decimal, no trailing zeros,
    and preserves negative zero."""
    if isinstance(v, int):
        return str(v)
    f = float(v)
    s = repr(f)
    if s.endswith('.0'):
        s = s[:-2]
    if f == 0.0 and _math.copysign(1.0, f) < 0 and not s.startswith('-'):
        s = '-' + s
    return s

def dumps(node, indent=0, _buf=None):
    """Serialise a Node tree back to KiCad s-expression text."""
    top = _buf is None
    if top: _buf = []
    pad = '\t' * indent
    _buf.append(pad + '(')
    first = True
    inline_children = []
    for i, c in enumerate(node):
        if isinstance(c, Node):
            inline_children.append(i)
    for i, c in enumerate(node):
        if isinstance(c, Node):
            _buf.append('\n')
            dumps(c, indent + 1, _buf)
        else:
            if not first:
                _buf.append(' ')
            if isinstance(c, Q):
                _buf.append('"' + _escape(c) + '"')
            elif isinstance(c, str):
                _buf.append(c)
            else:
                _buf.append(fmt_num(c))
        first = False
    if inline_children:
        _buf.append('\n' + pad)
    _buf.append(')')
    if top:
        return ''.join(_buf)


def parse(text):
    toks = _TOKEN.findall(text)
    pos = 0
    n = len(toks)

    def rd():
        nonlocal pos
        node = Node()
        while pos < n:
            t = toks[pos]
            pos += 1
            if t == '(':
                node.append(rd())
            elif t == ')':
                return node
            elif t[0] == '"':
                node.append(Q(_unescape(t[1:-1])))
            else:
                try:
                    if t == '-0':
                        node.append(-0.0)          # int() would lose the sign
                    elif '.' in t or 'e' in t or 'E' in t:
                        node.append(float(t))
                    else:
                        node.append(int(t))
                except ValueError:
                    node.append(t)
        return node

    root = Node()
    while pos < n:
        if toks[pos] == '(':
            pos += 1
            root.append(rd())
        else:
            pos += 1
    return root[0] if len(root) == 1 else root

def load(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return parse(f.read())
