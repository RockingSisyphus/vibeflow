"""One source run publishes one record, even when checked entry points delegate."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from vibeflow.tooling.presentation.preview.diagnostics import incidental_preview
from vibeflow.tooling.application.python.presentation.preview import python_preview
from vibeflow.tooling.presentation.preview.catalog import new_record, utc_now
from vibeflow.tooling.presentation.viewer import install_page
from vibeflow.tooling.presentation.preview.exporter import workflow_identity, preview_workspace

_session = ContextVar("vibeflow_source_run_preview", default=None)


@contextmanager
def source_run_preview(config, *, workspace=None, preview_root=None):
    if _session.get() is not None:
        if workspace is not None:
            _session.get()["workspace"] = workspace
        yield
        return
    session = dict(config=Path(config).resolve(), workspace=workspace, preview_root=preview_root, record=None, started=utc_now())
    token = _session.set(session)
    try:
        yield
    except BaseException as exc:
        session["error"] = str(exc) or type(exc).__name__
        raise
    finally:
        try:
            _finish(session)
        finally:
            _session.reset(token)


def bind_run_observer(observer):
    session = _session.get()
    if session is not None:
        session["observer"] = observer


def _finish(session):
    observer = session.get("observer")
    outcome = observer.result if observer is not None else {"status":"failed","error":session.get("error","Run observation did not start")}
    status, error = outcome["status"], outcome["error"]
    record = session["record"]
    if record is None:
        record = incidental_preview(_missing_preview, session=session, status=status, error=error)
    if record is not None:
        incidental_preview(record.update, status=status, error=error,
                           error_path=session.get("error_path"))


def _missing_preview(session, status, error):
    workspace = preview_workspace(session["config"], session["workspace"])
    root = Path(session["preview_root"] or (workspace.root if workspace else session["config"].parent)).resolve()
    install_page(root)
    record = new_record(root, workflow_identity(session["config"], workspace), "run", status)
    record.metadata.update(created_at=session["started"], preview_error=error or "本次操作未生成可用展示数据。")
    return record


def start_run_preview(prepared, run_dir, health=None):
    session = _session.get()
    if session is None or session["record"] is not None:
        return
    workspace = session["workspace"]
    if workspace is None:
        from vibeflow.tooling.project.workspace_loader import load_workspace_config, find_project_config, load_project_workspace
        for directory in session["config"].parents:
            candidate = directory / "vibeflow_config.jsonc"
            if candidate.is_file():
                workspace = load_workspace_config(candidate)
                break
        if workspace is None and find_project_config(session["config"]):
            workspace = load_project_workspace(session["config"])
    session["error_path"] = Path(run_dir) / "preview.error.txt"
    session["record"] = incidental_preview(python_preview, prepared=prepared, config=session["config"],
        workspace=workspace, preview_root=session["preview_root"], category="run", status="running",
        error_path=session["error_path"])
    if session["record"] is not None:
        incidental_preview(_attach_run_preview, record=session["record"], run_dir=run_dir,
            health=health, error_path=session["error_path"])


def _attach_run_preview(record, run_dir, health):
    import json
    import os
    record.metadata["run_id"] = Path(run_dir).name
    if health is not None:
        record.metadata["check_status"] = health.status
    record.update("running")
    (Path(run_dir) / "preview.json").write_text(json.dumps({"id": record.metadata["id"],
        "directory": os.path.relpath(record.directory, run_dir)}, ensure_ascii=False), encoding="utf-8")

