--------------------------------
Implementation 1
---

---

In miner_deepagent.py the definition of logger middle requires slight change.
The part
def \_build_logging_middleware() -> Callable:
"""
Build a wrap_tool_call middleware that logs: - Which tool was called (yellow) - The tool's input arguments (truncated) - Completion of the tool call (green) - Any errors (red)
"""

    @wrap_tool_call
    def _log_tool_calls(request: Any, handler: Callable) -> Any:
        """Intercept every tool call and log it via loguru."""
        tool_name = getattr(request, "name", str(request))
        raw_args = getattr(request, "args", {})

extract tool_name and raw_args but the problem is request is a ToolMessage class instance and it doesn't have name and args attributes. It has tool_meesage(confirm it) so extract tool_meeage first and from it extract tool_name and args as a dictionary in case those are not present return 'Common Tool' as name and {} as args.

---

## Implementation 2

current router only has json and pydantic class but I want the deep agent miner to also have pydantic class option.
It would change in prompt, code and other place I guess the initial option to keep output model in SQL miner would work for both. so make this change in deep agent miner as well. It required make changes in the model class to add another method to create entities,relations and flows from strucutred output model to write in deep agent flow.
Next create a dummy example and test it.
