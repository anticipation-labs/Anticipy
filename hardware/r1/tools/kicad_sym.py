"""Minimal KiCad symbol-library reader: s-expression parse + derived-symbol
flattening + pin geometry extraction."""
import os

LIB_DIR = "/usr/share/kicad/symbols"


def tokenize(txt):
    out, i, n = [], 0, len(txt)
    while i < n:
        c = txt[i]
        if c in "()":
            out.append(c); i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while txt[j] != '"' or txt[j - 1] == "\\":
                buf.append(txt[j]); j += 1
            out.append(('"', "".join(buf))); i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not txt[j].isspace() and txt[j] not in "()":
                j += 1
            out.append(txt[i:j]); i = j
    return out


def parse(tokens):
    it = iter(tokens)

    def build():
        node = []
        for t in it:
            if t == "(":
                node.append(build())
            elif t == ")":
                return node
            else:
                node.append(t)
        return node
    root = []
    for t in it:
        if t == "(":
            root.append(build())
    return root


def sx(node, indent=0):
    """serialize back to s-expression text"""
    pad = "  " * indent
    parts = []
    simple = all(not isinstance(x, list) for x in node)
    def atom(a):
        if isinstance(a, tuple):
            return '"%s"' % a[1]
        return a
    if simple:
        return pad + "(" + " ".join(atom(a) for a in node) + ")"
    head = [atom(a) for a in node if not isinstance(a, list)]
    parts.append(pad + "(" + " ".join(head))
    for a in node:
        if isinstance(a, list):
            parts.append(sx(a, indent + 1))
    parts.append(pad + ")")
    return "\n".join(parts)


_lib_cache = {}


def load_lib(libname):
    if libname not in _lib_cache:
        txt = open(os.path.join(LIB_DIR, libname + ".kicad_sym")).read()
        tree = parse(tokenize(txt))[0]
        syms = {}
        for node in tree:
            if isinstance(node, list) and node and node[0] == "symbol":
                syms[node[1][1]] = node
        _lib_cache[libname] = syms
    return _lib_cache[libname]


def get(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def getall(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def flatten_symbol(libname, name):
    """Return a fully resolved symbol node named `libname:name`."""
    syms = load_lib(libname)
    node = syms[name]
    ext = get(node, "extends")
    if ext:
        parent = flatten_symbol(libname, ext[1][1])
        import copy
        merged = copy.deepcopy(parent)
        # override properties from child
        child_props = {p[1][1]: p for p in getall(node, "property")}
        keep = []
        for x in merged:
            if isinstance(x, list) and x and x[0] == "property" and x[1][1] in child_props:
                continue
            keep.append(x)
        merged[:] = keep
        for p in getall(node, "property"):
            import copy as _c
            merged.append(_c.deepcopy(p))
        node = merged
    import copy
    node = copy.deepcopy(node)
    # rename symbol to lib:name and subunits to name_<u>_<s>
    full = "%s:%s" % (libname, name)
    old = node[1][1]
    oldbase = old.split(":")[-1]
    node[1] = ('"', full)
    for sub in getall(node, "symbol"):
        subname = sub[1][1]
        if subname.startswith(oldbase):
            sub[1] = ('"', name + subname[len(oldbase):])
    return node


def symbol_pins(node):
    """[(number, name, type, x, y, angle_deg)] in lib coords (y up)."""
    pins = []
    for sub in getall(node, "symbol"):
        for p in getall(sub, "pin"):
            at = get(p, "at")
            name = get(p, "name")[1]
            num = get(p, "number")[1]
            nm = name[1] if isinstance(name, tuple) else name
            nu = num[1] if isinstance(num, tuple) else num
            pins.append((nu, nm, p[1],
                         float(at[1]), float(at[2]), float(at[3])))
    return pins
