"""Every automation must map to a real tool whose params validate from the mapping alone.

This is the regression test for a bug where the weekly Discover Weekly backup mapped to a tool
requiring `playlist_id`, so every scheduled run failed validation before doing any work.
"""

from app.models.enums import AutomationKind
from app.services.sweeps import AUTOMATION_TOOLS
from app.services.tools import registry


def test_every_mapped_automation_names_a_registered_tool():
    for kind, (tool_key, _params) in AUTOMATION_TOOLS.items():
        assert tool_key in registry, f"{kind} maps to unknown tool {tool_key}"


def test_mapped_params_validate_without_extra_input():
    """A scheduler supplies only what the mapping holds, so that alone must be enough."""
    for kind, (tool_key, params) in AUTOMATION_TOOLS.items():
        tool_cls = registry.get(tool_key)
        # Raises if a required field is missing, which is exactly the bug this guards against.
        assert tool_cls.Params.model_validate(params) is not None, kind


def test_mapping_keys_are_real_automation_kinds():
    valid = {k.value for k in AutomationKind}
    assert set(AUTOMATION_TOOLS) <= valid
