"""Bounded arithmetic evidence; no eval, names, calls, powers or arbitrary code."""

import ast
from fractions import Fraction


def value(text):
    if len(text) > 160:
        return None
    try:
        root = ast.parse(text.strip(), mode="eval")
        if len(list(ast.walk(root))) > 40:
            return None

        def visit(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                if abs(node.value) > 10**12:
                    raise ValueError()
                return Fraction(str(node.value))
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                a, b = visit(node.left), visit(node.right)
                if isinstance(node.op, ast.Add):
                    return a + b
                if isinstance(node.op, ast.Sub):
                    return a - b
                if isinstance(node.op, ast.Mult):
                    return a * b
                return a / b
            raise ValueError()

        return visit(root.body)
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return None
