import {mkdtemp, readFile, rm, writeFile} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

class NativeAnalysis {
  constructor(ts, packageRoot) {
    this.packageRoot = packageRoot;
    this.version = ts.version;
    this.overlays = new Map();
    this.projectIndex = 0;
    this.api = new ts.API({
      cwd: packageRoot,
      fs: {
        readFile: name => this.overlays.get(path.resolve(name)),
        fileExists: name => this.overlays.has(path.resolve(name)) ? true : undefined,
      },
    });
  }

  async open(request, files, compilerOptions, overlays) {
    const directory = request.workflowEntry
      ? path.dirname(request.workflowEntry)
      : (this.configRoot ??= await mkdtemp(path.join(os.tmpdir(), "vibeflow-audit-ts-")));
    const configPath = path.join(directory, `tsconfig.vibeflow-${this.projectIndex++}.json`);
    await writeFile(configPath, JSON.stringify({compilerOptions, files}), "utf8");

    const previous = this.snapshot;
    this.overlays = overlays;
    const update = {openProjects: [configPath]};
    if (this.configPath) update.closeProjects = [this.configPath];
    // Different Rules may supply different source overlays. Refresh the project
    // view on a cache miss, using the same native compiler process.
    if (previous) update.fileChanges = {invalidateAll: true};
    this.snapshot = this.api.updateSnapshot(update);
    this.configPath = configPath;
    previous?.dispose();

    const project = this.snapshot.getProject(configPath);
    if (!project) {
      const error = new Error("TypeScript did not create a project for AOT validation");
      error.code = "VF_TYPESCRIPT";
      throw error;
    }
    const {program, checker} = project;
    const sourceFiles = program.getSourceFileNames().map(file => program.getSourceFile(file)).filter(Boolean);
    return {program, checker, project, sourceFiles};
  }

  async dispose() {
    try {
      this.api.close();
    } finally {
      if (this.configRoot) await rm(this.configRoot, {recursive: true, force: true});
    }
  }
}

export class AnalysisSession {
  constructor() {
    this.current = null;
    this.native = null;
    this.functions = new Map();
    this.callGraphs = new Map();
  }

  metric(store, sourceFile, extra, create) {
    const key = JSON.stringify([path.resolve(sourceFile.fileName), sourceFile.getFullText(), extra]);
    if (!store.has(key)) store.set(key, create());
    return store.get(key);
  }

  async openNative(ts, request, files, compilerOptions, overlays) {
    const packageRoot = path.resolve(request.packageRoot);
    if (this.native?.packageRoot !== packageRoot || this.native?.version !== ts.version) {
      await this.releaseNative();
      this.native = new NativeAnalysis(ts, packageRoot);
    }
    try {
      return await this.native.open(request, files, compilerOptions, overlays);
    } catch (error) {
      await this.releaseNative();
      throw error;
    }
  }

  async releaseNative() {
    const native = this.native;
    this.native = null;
    await native?.dispose();
  }

  async dispose() {
    this.current = null;
    try {
      await this.releaseNative();
    } finally {
      this.functions.clear();
      this.callGraphs.clear();
    }
  }
}

async function textAt(file, overlays) {
  if (overlays.has(file)) return overlays.get(file);
  try {
    return await readFile(file, "utf8");
  } catch {
    return null;
  }
}

async function unchanged(entry, overlays) {
  for (const [file, text] of entry.texts) {
    if (await textAt(file, overlays) !== text) return false;
  }
  return true;
}

export async function analysisProgram(ts, request, files, compilerOptions, session) {
  const overlays = new Map((request.sourceSnapshots || []).map(source => [path.resolve(source.path), source.text]));
  const key = JSON.stringify([
    path.resolve(request.packageRoot), String(ts.version || ""),
    [...files].sort(), compilerOptions, request.workflowEntry ? path.dirname(request.workflowEntry) : "",
  ]);
  const cached = session?.current;
  if (cached?.key === key && await unchanged(cached.entry, overlays)) {
    return {...cached.entry, dispose: async () => {}};
  }

  const owner = session ?? new AnalysisSession();
  owner.current = null;
  try {
    const program = await owner.openNative(ts, request, files, compilerOptions, overlays);
    const texts = new Map();
    for (const file of program.sourceFiles) {
      const absolute = path.resolve(file.fileName);
      if (!absolute.includes(`${path.sep}node_modules${path.sep}`)) texts.set(absolute, file.getFullText());
    }
    for (const file of files) {
      if (!texts.has(file)) texts.set(file, await textAt(file, overlays));
    }
    const entry = {...program, texts};
    if (session) owner.current = {key, entry};
    return {...entry, dispose: session ? async () => {} : () => owner.dispose()};
  } catch (error) {
    if (!session) await owner.dispose();
    throw error;
  }
}
