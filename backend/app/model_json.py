"""Conservative JSON transport repairs; schema validation remains mandatory."""
import json
import re


class OutputError(ValueError):
    def __init__(self, reason, raw=""):
        super().__init__(reason)
        self.raw = raw


# These TeX commands start with otherwise valid JSON escapes (\t, \f, ...).
LATEX = re.compile(r"\\(?:frac|forall|begin|beta|bar|boxed|big|bigr|bigl|right|rho|rangle|rvert|theta|text|textbf|textrm|times|tan|tau|tilde|to|top|neq|nu|nabla|not|vec|varepsilon|varphi)\b")


def parse_output(raw):
    text = raw.strip().lstrip("\ufeff")
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)[:-3].strip()
    if not text:
        raise OutputError("empty JSON output", raw)
    fixed, quoted, i = [], False, 0
    while i < len(text):
        char = text[i]
        if char == '"':
            quoted = not quoted
        elif quoted and char == "\\":
            if i + 1 >= len(text):
                break  # Never manufacture the missing end of a truncated response.
            following = text[i + 1]
            if LATEX.match(text, i) or following not in '"\\/bfnrtu':
                fixed.append("\\\\")
                i += 1
                continue
            fixed.append(text[i:i + 2])
            i += 2
            continue
        elif quoted and ord(char) < 32:
            fixed.append(json.dumps(char)[1:-1])
            i += 1
            continue
        elif not quoted and char == "," and text[i + 1:].lstrip().startswith(("}", "]")):
            i += 1
            continue
        fixed.append(char)
        i += 1
    try:
        value = json.loads("".join(fixed))
    except ValueError as exc:
        raise OutputError("invalid or incomplete JSON", raw) from exc
    if not isinstance(value, dict):
        raise OutputError("expected a JSON object", raw)
    return value
