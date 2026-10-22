"""Install the standalone browser tool; never write workflow snapshots here."""
from pathlib import Path
from importlib.resources import files
import re
from urllib.parse import urlsplit
from vibeflow.tooling.file_io import atomic_write


def viewer_assets():
    source=Path(__file__).resolve().parents[4] / "tools" / "workflow-viewer"
    return source if source.is_dir() else files("vibeflow.tooling").joinpath("viewer_assets")


def install_page(root):
    root=Path(root).resolve()
    assets=viewer_assets()
    destination=root / "vibeflow-preview" / "assets"
    destination.mkdir(parents=True,exist_ok=True)
    for item in assets.iterdir():
        if item.name in {"README.md","index.html","preview.config.js"} or item.is_dir():
            continue
        target=destination/item.name
        data=item.read_bytes()
        if target.exists() and target.read_bytes()==data:
            continue
        atomic_write(target, data)
    html=assets.joinpath("index.html").read_text(encoding="utf-8")
    def reference(match):
        attribute,quote,url=match.groups()
        if url=="preview.config.js":url="vibeflow-preview.config.js"
        elif url and not urlsplit(url).scheme and not url.startswith(("/","#")):url="vibeflow-preview/assets/"+url
        return attribute+"="+quote+url+quote
    html=re.sub(r'\b(src|href)=([\"\'])(.*?)\2',reference,html)
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
