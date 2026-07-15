# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import importlib
import sys
from typing import Any

import pytest
from google.adk.events.event import Event


@pytest.fixture
def agent_runtime(monkeypatch: pytest.MonkeyPatch) -> Any:
    module_name = "hello_cloud_agent.agent_runtime_app"
    previous_module = sys.modules.pop(module_name, None)
    monkeypatch.setenv("BT_ENABLE_AGENT_RUNTIME", "1")
    try:
        module = importlib.import_module(module_name)
        yield module.agent_runtime
    finally:
        sys.modules.pop(module_name, None)
        if previous_module is not None:
            sys.modules[module_name] = previous_module


@pytest.mark.asyncio
async def test_agent_stream_query(agent_runtime: Any) -> None:
    """
    Integration test for the agent stream query functionality.
    Tests that the agent returns valid streaming responses.
    """
    # Create message and events for the async_stream_query
    message = "Hi!"
    events = []
    async for event in agent_runtime.async_stream_query(message=message, user_id="test"):
        events.append(event)
    assert len(events) > 0, "Expected at least one chunk in response"

    # Check for valid content in the response
    has_text_content = False
    for event in events:
        validated_event = Event.model_validate(event)
        content = validated_event.content
        if (
            content is not None
            and content.parts
            and any(part.text for part in content.parts)
        ):
            has_text_content = True
            break

    assert has_text_content, "Expected at least one event with text content"
