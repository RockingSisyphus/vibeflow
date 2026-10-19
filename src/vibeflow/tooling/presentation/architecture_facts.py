"""Plain architecture facts shared by documents, snapshots and Target adapters."""
import json
from vibeflow.tooling.project.document_kinds import ARCHITECTURE_DOCUMENT_HEADER

def render_architecture_payload(payload):
    return ARCHITECTURE_DOCUMENT_HEADER + json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
