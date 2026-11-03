<!-- vibeflow-directory-purpose -->
# Workflow nodes

Copy nodes.py / nodes.mjs into the project nodes directory and protocol.py / protocol.mjs into a Plugin package. The Plugin provides only example business data schemas. Select it in the workflow.

InvokeSync, Call, CallAndWait, Wait, Send, Receive and Kill use the fixed context.workflow API. Python uses methods and await; JS waiting implementations use completion suspend. Waiting workflows use entry_mode async. Explicit start/end terminals surround the ordinary nodes.

Targets remain in config.workflow, process or in_process startup in config.launch, and expected messaging peers in config.expected_workflows. workflow_operations describes the operation for build and preview. Call returns after registration; CallAndWait waits for real completion. The author owns child lifecycle and cleanup.

Application events and queues belong to project code and ordinary runtime inputs. See ../../docs/user/workflow-coordination.md for host integration.
