"""Install the standalone browser tool; never write workflow snapshots here."""
from pathlib import Path
from importlib.resources import files
from uuid import uuid4
import os
from .preview.catalog import atomic_write


def install_page(root):
    root=Path(root).resolve()
    source=Path(__file__).resolve().parents[4] / "tools" / "workflow-viewer"
    assets=source if source.is_dir() else files("vibeflow.tooling").joinpath("viewer_assets")
    destination=root / "vibeflow-preview" / "assets"
    destination.mkdir(parents=True,exist_ok=True)
    for item in assets.iterdir():
        if item.name in {"README.md","index.html","preview.config.js"} or item.is_dir():
            continue
        target=destination/item.name
        data=item.read_bytes()
        if target.exists() and target.read_bytes()==data:
            continue
        temporary=target.with_name("."+target.name+"."+uuid4().hex)
        try:
            temporary.write_bytes(data)
            os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
    html=assets.joinpath("index.html").read_text(encoding="utf-8")
    html=html.replace('src="preview.config.js"','src="vibeflow-preview.config.js"')
    for filename in ("viewer.css","fontawesome.css","solid.css","regular.css","brands.css","elk.bundled.js",
                     "model.js","inspector.js","shapes.js","layout.js","views.js","viewer.js"):
        html=html.replace('"'+filename+'"','"vibeflow-preview/assets/'+filename+'"')
    atomic_write(root/"vibeflow-preview.html",html)
    config=root/"vibeflow-preview.config.js"
    if not config.exists():
        # Exclusive creation preserves user changes and concurrent installers.
        try:
            with config.open("x",encoding="utf-8") as stream:
                stream.write('window.VibeFlowViewerConfig={dataRoot:new URL("./vibeflow-preview/",document.currentScript.src).href};\n')
        except FileExistsError:
            pass


def install_for_record(record):
    try:
        install_page(record.root)
    except Exception as exc:
        from .preview.exporter import PreviewExportError
        record.metadata["preview_error"]="Viewer installation failed: "+str(exc)
        record.update(record.metadata["status"])
        raise PreviewExportError(record,exc) from exc
