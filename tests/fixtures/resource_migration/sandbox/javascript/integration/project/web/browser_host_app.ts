import { createWorkflowHost } from "@vibeflow/workflow";

interface BrowserWorkflowExports {
  readonly createWorkflowHost: typeof createWorkflowHost;
}

interface WorkflowRequest {
  readonly resolve: (workflow: BrowserWorkflowExports) => void;
}

document.addEventListener("vibeflow-sandbox-request-workflow", event => {
  const request = event as CustomEvent<WorkflowRequest>;
  request.detail.resolve(Object.freeze({ createWorkflowHost }));
});
