interface AuditParams {
  readonly label: string;
}

interface AuditContext {
  readonly capabilities: {
    readonly "sandbox.audit": {
      readonly record: (
        input: { readonly label: string },
      ) =>
        | { readonly accepted: boolean }
        | Promise<{ readonly accepted: boolean }>;
    };
  };
}

export async function run(
  _inputs: Readonly<Record<never, never>>,
  params: AuditParams,
  context: AuditContext,
): Promise<Readonly<Record<never, never>>> {
  await context.capabilities["sandbox.audit"].record({
    label: params.label,
  });
  return {};
}
