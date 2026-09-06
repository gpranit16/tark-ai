import ast
import math
import operator
import re
from typing import Any

from app.tools.base import BaseTool, ToolExecutionContext, ToolPermission, ToolResult


class SafeMathEvaluator:
    """Evaluates mathematical expressions safely using Python's AST without eval()."""

    _SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    _SAFE_FUNCTIONS = {
        "sqrt": math.sqrt,
        "abs": abs,
        "round": round,
        "ceil": math.ceil,
        "floor": math.floor,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "exp": math.exp,
        "min": min,
        "max": max,
        "pow": pow,
    }

    _SAFE_CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
    }

    def evaluate(self, expression: str) -> float | int:
        if not expression or not expression.strip():
            raise ValueError("Expression is empty")

        clean_expr = self._preprocess_expression(expression.strip())

        try:
            tree = ast.parse(clean_expr, mode="eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid math syntax: {str(e)}")

        return self._eval_node(tree.body)

    def _preprocess_expression(self, expr: str) -> str:
        """Handle percentages and common natural math formats."""
        # Replace 'X% of Y' -> '(X/100)*Y'
        expr = re.sub(
            r"(\d+(?:\.\d+)?)\s*%\s+of\s+(\d+(?:\.\d+)?)",
            r"(\1 / 100) * \2",
            expr,
            flags=re.IGNORECASE,
        )
        # Replace 'X%' -> '(X/100)'
        expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1 / 100)", expr)
        # Replace '^' with '**' for exponentiation
        expr = expr.replace("^", "**")
        return expr

    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"Unsupported constant value: {node.value}")

        if isinstance(node, ast.Num):  # Python < 3.8 compat
            return node.n

        if isinstance(node, ast.Name):
            if node.id in self._SAFE_CONSTANTS:
                return self._SAFE_CONSTANTS[node.id]
            raise ValueError(f"Variable or symbol '{node.id}' is not allowed")

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in self._SAFE_OPERATORS:
                operand = self._eval_node(node.operand)
                return self._SAFE_OPERATORS[op_type](operand)
            raise ValueError(f"Unsupported unary operator: {op_type}")

        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type in self._SAFE_OPERATORS:
                left = self._eval_node(node.left)
                right = self._eval_node(node.right)
                # Check for zero division
                if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
                    raise ZeroDivisionError("Division by zero")
                # Check for reasonable power bounds
                if op_type == ast.Pow and (right > 1000 or left > 1000000):
                    raise OverflowError("Exponentiation exceeds maximum safe limit")
                return self._SAFE_OPERATORS[op_type](left, right)
            raise ValueError(f"Unsupported binary operator: {op_type}")

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Only direct function calls are allowed")
            func_name = node.func.id
            if func_name not in self._SAFE_FUNCTIONS:
                raise ValueError(f"Function '{func_name}' is not allowed")
            args = [self._eval_node(arg) for arg in node.args]
            return self._SAFE_FUNCTIONS[func_name](*args)

        raise ValueError(f"Unsupported AST syntax node: {type(node).__name__}")


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Perform safe, accurate mathematical and arithmetic calculations, percentages, and scientific math functions."
    category = "utility"
    permissions = [ToolPermission.SAFE]

    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to compute (e.g. '12345 * 678', '15% of 850', 'sqrt(144) + 5^3')",
            }
        },
        "required": ["expression"],
    }

    def __init__(self) -> None:
        self.evaluator = SafeMathEvaluator()

    async def execute(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        expression = str(arguments.get("expression", ""))
        try:
            result = self.evaluator.evaluate(expression)
            # Format nicely
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return ToolResult(
                tool_name=self.name,
                success=True,
                data={
                    "expression": expression,
                    "result": result,
                },
                source="calculator_engine",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                error=str(exc),
                source="calculator_engine",
            )
