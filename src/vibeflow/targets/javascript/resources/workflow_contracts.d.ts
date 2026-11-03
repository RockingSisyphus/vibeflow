export interface WorkflowReference { readonly root?: string; readonly path: string; readonly entry?: string }
export interface WorkflowStatus { readonly id?: string; readonly state: "starting" | "running" | "stopping" | "succeeded" | "failed" | "cancelled"; readonly outputs?: any; readonly error?: any }
export interface WorkflowSession {
  invoke_sync?(request: {workflow: WorkflowReference; inputs?: Record<string, unknown>}, context?: {signal?: any}): Record<string, unknown>;
  call(request: {workflow: WorkflowReference; launch: Record<string, unknown>; inputs?: Record<string, unknown>; timeout?: number}, context?: {signal?: any}): Promise<{id: string}>;
  wait(request: {id: string; timeout?: number}, context?: {signal?: any}): Promise<WorkflowStatus>;
  send(request: {id: string; port?: string; payload: unknown}, context?: {signal?: any}): void;
  receive(request?: {port?: string; timeout?: number}, context?: {signal?: any}): Promise<{sender: string; port: string; payload: any}>;
  kill(request: {id: string; workflow: WorkflowReference; timeout?: number}, context?: {signal?: any}): Promise<WorkflowStatus>;
}
export interface WorkflowNodeContext {
  readonly signal?: {readonly aborted: boolean; readonly reason: unknown; readonly onabort: ((event: any) => unknown) | null; throwIfAborted(): void; addEventListener(type: string, listener: any, options?: any): void; removeEventListener(type: string, listener: any, options?: any): void; dispatchEvent(event: any): boolean};
  readonly workflow: Readonly<Omit<WorkflowSession, "invoke_sync"> & {self(): {id: string}; invoke_sync(request: {workflow: WorkflowReference; inputs?: Record<string, unknown>}): Record<string, unknown>}>;
  trace(kind: string, details?: Readonly<Record<string, unknown>>): void;
  updateInfo(info: readonly Readonly<Record<string, unknown>>[]): void;
}
