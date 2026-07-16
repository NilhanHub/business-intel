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
import hashlib
import logging
import os
from typing import Any

if os.environ.get("BT_ENABLE_AGENT_RUNTIME") != "1":
    raise RuntimeError(
        "Agent Runtime is disabled for this local-only build. "
        "Set BT_ENABLE_AGENT_RUNTIME=1 and install the agent-runtime extra only for an explicitly approved cloud workflow."
    )

try:
    import vertexai
    from google.cloud import logging as google_cloud_logging
    from vertexai.agent_engines.templates.adk import AdkApp
except ImportError as exc:
    raise RuntimeError(
        "Agent Runtime dependencies are not installed. Run `uv sync --extra agent-runtime` only for an explicitly approved cloud workflow."
    ) from exc

from dotenv import load_dotenv
from google.adk.artifacts import (
    GcsArtifactService,
    InMemoryArtifactService,
)

from sl_trigger_leads.agent import app as adk_app
from sl_trigger_leads.app_utils.telemetry import setup_telemetry
from sl_trigger_leads.app_utils.typing import Feedback

# Load environment variables from .env file at runtime
load_dotenv()


def _load_hunter_key_from_secret_manager_if_needed() -> None:
    """Populate HUNTER_API_KEY from Secret Manager when env injection is absent."""
    if os.environ.get("HUNTER_API_KEY"):
        return
    project_id = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
        or os.environ.get("GCLOUD_PROJECT")
        or "business-intel-123"
    )
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/HUNTER_API_KEY/versions/latest"
        response = client.access_secret_version(request={"name": name})
        value = response.payload.data.decode("utf-8").strip()
        if value:
            os.environ["HUNTER_API_KEY"] = value
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
            logging.getLogger(__name__).info(
                "Loaded HUNTER_API_KEY from Secret Manager: present=True hash=%s",
                digest,
            )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "HUNTER_API_KEY Secret Manager fallback unavailable: %s",
            exc.__class__.__name__,
        )


class AgentEngineApp(AdkApp):
    def set_up(self) -> None:
        """Initialize the agent engine app with logging and telemetry."""
        vertexai.init()
        _load_hunter_key_from_secret_manager_if_needed()
        setup_telemetry()
        super().set_up()
        logging.basicConfig(level=logging.INFO)
        logging_client = google_cloud_logging.Client()
        self.logger = logging_client.logger(__name__)
        if gemini_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = gemini_location

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Collect and log feedback."""
        feedback_obj = Feedback.model_validate(feedback)
        self.logger.log_struct(feedback_obj.model_dump(), severity="INFO")

    def register_operations(self) -> dict[str, list[str]]:
        """Registers the operations of the Agent."""
        operations = super().register_operations()
        operations[""] = [*operations.get("", []), "register_feedback"]
        return operations


gemini_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")
agent_runtime = AgentEngineApp(
    app=adk_app,
    artifact_service_builder=lambda: (
        GcsArtifactService(bucket_name=logs_bucket_name)
        if logs_bucket_name
        else InMemoryArtifactService()
    ),
)
