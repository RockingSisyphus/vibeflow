import {pathToFileURL} from "node:url";

export async function loadTypeScript(require) {
  const version = String(require("typescript").version || "");
  if (!/^v?7\.\d+(?:\.\d+)?/.test(version)) {
    const error = new Error(`TypeScript >=7 <8 is required, found ${version}`);
    error.code = "VF_TOOLCHAIN_VERSION";
    throw error;
  }
  const [ast, api] = await Promise.all(
    ["typescript/unstable/ast", "typescript/unstable/sync"].map(name => import(pathToFileURL(require.resolve(name)).href)),
  );
  return {...ast, ...api, version};
}
