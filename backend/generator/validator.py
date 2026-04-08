"""Validates generated connector code for correctness."""

import ast
import logging
from typing import List

logger = logging.getLogger(__name__)

REQUIRED_FUNCTIONS = ["authenticate", "track_shipment", "parse_tracking_response"]


class CodeValidator:
    """Validates generated Python connector code."""

    def validate(self, code: str) -> List[str]:
        """Validate code and return list of errors. Empty list = valid."""
        errors = []

        # 1. Syntax check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            return errors  # Can't do further checks

        # 2. Check required functions exist
        func_names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_names.add(node.name)

        for fn in REQUIRED_FUNCTIONS:
            if fn not in func_names:
                errors.append(f"Missing required function: {fn}")

        # 3. Check STATUS_MAP exists and is a dict assignment
        has_status_map = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "STATUS_MAP":
                        has_status_map = True
                        if isinstance(node.value, ast.Dict) and len(node.value.keys) == 0:
                            errors.append("STATUS_MAP is empty")

        if not has_status_map:
            errors.append("Missing STATUS_MAP assignment")

        # 4. Check map_status helper exists
        if "map_status" not in func_names:
            errors.append("Missing map_status helper function")

        if errors:
            logger.warning(f"Validation found {len(errors)} errors: {errors}")
        else:
            logger.info("Code validation passed")

        return errors
