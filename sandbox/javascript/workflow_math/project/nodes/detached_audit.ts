interface AuditParams {
  readonly label: string;
}



export async function run(
  inputs: Readonly<Record<never, never>>,
  params: AuditParams,
  context: any,
): Promise<Readonly<Record<never, never>>> {
  await (inputs as any)["app.session"].value.audit.record({
    label: params.label,
  }, {signal: context.signal});
  return {};
}
