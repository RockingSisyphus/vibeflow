"""Owned source imports retain Python package-resource behavior."""
import pytest

from vibeflow.targets.python.sdk.source_namespace import source_namespace


@pytest.mark.parametrize("kind", ("owner", "package", "namespace"))
def test_owned_package_resources_are_readable_without_global_aliases(tmp_path, kind):
    owner = tmp_path / "source"
    package = owner if kind == "owner" else owner / "assets"
    package.mkdir(parents=True)
    if kind == "package":
        (package / "__init__.py").write_text("")
    (package / "value.txt").write_text("owned data")
    source = package / "reader.py"
    source.write_text('from importlib.resources import files\n'
                      'def read(): return files(__package__).joinpath("value.txt").read_text()\n')
    module = source_namespace(owner).load(source)
    assert module.read() == "owned data"
