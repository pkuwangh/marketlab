"""Replay pre-B3 rules with only break retries removed; no canonical writes."""

import ast
import runpy
import subprocess
import sys
from types import ModuleType


class RemoveBreakRetry(ast.NodeTransformer):
    def visit_Expr(self, node):
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_reopen_after_new_low"
            and call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "br"
        ):
            return None
        return self.generic_visit(node)


def main():
    source = subprocess.check_output(
        ["git", "show", "a1efbf3:src/marketlab/regime_lifecycle.py"], text=True
    )
    tree = RemoveBreakRetry().visit(ast.parse(source))
    module = ModuleType("break_retry_ablation")
    sys.modules[module.__name__] = module
    exec(compile(tree, "break_retry_ablation", "exec"), module.__dict__)
    research = runpy.run_path("plans/v1.2/entry_research.py")
    runner = research["main"]
    runner.__globals__.update(transition=module.transition, DEFAULT_CONFIG=module.DEFAULT_CONFIG)
    runner("B3-retry-ablation")


if __name__ == "__main__":
    main()
