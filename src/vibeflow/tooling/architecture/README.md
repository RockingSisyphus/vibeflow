<!-- vibeflow-directory-purpose -->
# Architecture facts and documents

This package owns the common workflow projection, project index, resource implementation relationships, document serialization/checking and workflow relation projection. It consumes operation-local inventory and prepared Target facts; it does not discover or execute business implementations, evaluate Rules, compile graphs or launch workflows.

Target presentation adapters provide declarations, source locations, prepared graph access and resource facts. `workflow.py` assembles their common graph and Nodeset records. `project.py` joins inventory with registered architecture documents and effective node references. `documents.py` owns JSONC and explicit freshness checks. The preview exporter projects saved project documents and publishes snapshots; browser rendering stays in `tools/workflow-viewer`.

Known planned coordination calls retain declaration/configuration intent as `planned` operation facts, without evaluating Rules or granting runtime permissions. Core supplies their call identities and inherited configuration scopes.
