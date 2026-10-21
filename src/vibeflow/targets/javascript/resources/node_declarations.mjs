/** Node definition defaults; the SDK supplies the common resource declaration. */
export function nodeDefinition(declare, value) {
  const options = {...value};
  if (typeof options.node_type !== "string" || !options.node_type.trim()) throw new TypeError("node.node_type must reference a NodeType");
  options.display_name ??= options.id;
  options.description ??= options.id;
  options.version ??= "1.0.0";
  options.flow_kind ??= "process";
  return declare("node", options, "run");
}
