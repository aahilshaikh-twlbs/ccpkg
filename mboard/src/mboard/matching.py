import re


def _has_wildcard(glob):
    # type: (str) -> bool
    return ("*" in glob) or ("?" in glob)


def _translate(glob):
    # type: (str) -> str
    # Translate a glob into an anchored regex pattern string.
    #   **  -> .*        (any chars including "/")
    #   *   -> [^/]*     (any chars except "/")
    #   ?   -> [^/]      (single char except "/")
    # every other character is matched literally (re.escape).
    out = []
    i = 0
    n = len(glob)
    while i < n:
        ch = glob[i]
        if ch == "*":
            if i + 1 < n and glob[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if ch == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(ch))
        i += 1
    return "^" + "".join(out) + "$"


def path_matches(glob, abs_path):
    # type: (str, str) -> bool
    # Match an absolute glob against an absolute path. See contract §6.
    if _has_wildcard(glob):
        return re.match(_translate(glob), abs_path) is not None
    # No wildcards: exact match, or glob is a prefix directory of abs_path.
    if glob == abs_path:
        return True
    prefix = glob if glob.endswith("/") else glob + "/"
    return abs_path.startswith(prefix)
