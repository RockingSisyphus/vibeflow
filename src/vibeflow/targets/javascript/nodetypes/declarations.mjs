/** Node definition defaults; the SDK supplies the common resource declaration. */
export function nodeDefinition(declare, value) {
  const options = {...value};
  options.display_name ??= options.type_key;
  options.description ??= options.type_key;
  options.version ??= "1.0.0";
  options.flow_kind ??= "process";
  return declare("node", options, "run");
}
