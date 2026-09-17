"""Minimal, fast S-expression parser for KiCad files."""
import re

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
                node.append(t[1:-1].encode().decode('unicode_escape', 'replace'))
            else:
                try:
                    node.append(float(t) if ('.' in t or 'e' in t or 'E' in t) else int(t))
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
