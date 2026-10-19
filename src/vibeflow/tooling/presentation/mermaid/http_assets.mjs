/** Short-lived loopback server for explicitly registered browser assets. */
import {createServer} from "node:http";
import {readFile, realpath, stat} from "node:fs/promises";
import {resolve, relative, isAbsolute, extname} from "node:path";
import {randomUUID} from "node:crypto";

const types = new Map([
  [".html", "text/html; charset=utf-8"], [".svg", "image/svg+xml"],
  [".mjs", "text/javascript"], [".js", "text/javascript"],
  [".css", "text/css"], [".woff2", "font/woff2"], [".woff", "font/woff"],
  [".ttf", "font/ttf"],
]);

export async function serveAssets({mounts = {}, files = {}, documents = {}} = {}) {
  const roots = new Map(await Promise.all(Object.entries(mounts).map(async ([name, root]) =>
    [name, await realpath(root)])));
  const exact = new Map(await Promise.all(Object.entries(files).map(async ([name, file]) =>
    [name, await realpath(file)])));
  const prefix = "/" + randomUUID() + "/";
  const server = createServer(async (request, response) => {
    try {
      if (!["GET", "HEAD"].includes(request.method)) {
        response.writeHead(405).end(); return;
      }
      const pathname = new URL(request.url, "http://127.0.0.1").pathname;
      if (!pathname.startsWith(prefix)) { response.writeHead(404).end(); return; }
      const name = decodeURIComponent(pathname.slice(prefix.length));
      let data, type;
      if (Object.hasOwn(documents, name)) {
        data = Buffer.from(documents[name]); type = "text/html; charset=utf-8";
      } else {
        let file = exact.get(name);
        if (!file) {
          const slash = name.indexOf("/");
          const root = roots.get(name.slice(0, slash));
          if (!root || slash < 0) { response.writeHead(404).end(); return; }
          file = await realpath(resolve(root, name.slice(slash + 1)));
          const inside = relative(root, file);
          if (inside === ".." || inside.startsWith("../") || inside.startsWith("..\\") || isAbsolute(inside)) {
            response.writeHead(404).end(); return;
          }
        }
        type = types.get(extname(file));
        if (!type || !(await stat(file)).isFile()) { response.writeHead(404).end(); return; }
        data = await readFile(file);
      }
      response.writeHead(200, {"Content-Type": type, "Content-Length": data.length,
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"});
      response.end(request.method === "HEAD" ? undefined : data);
    } catch {
      response.writeHead(404).end();
    }
  });
  await new Promise((accept, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", accept);
  });
  return {
    url: name => `http://127.0.0.1:${server.address().port}${prefix}${name}`,
    close: () => new Promise((accept, reject) => {
      server.close(error => error ? reject(error) : accept());
      server.closeAllConnections();
    }),
  };
}
