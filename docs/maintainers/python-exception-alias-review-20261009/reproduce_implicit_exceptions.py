"""New cases reuse the previous independent static/CLI engine unchanged."""
import importlib.util
from pathlib import Path
import sys

CASES = (
    ('set_single_unhashable', '{(alias := inputs)}', True),
    ('set_comp_unhashable', '{(alias := inputs) for item in (0,)}', True),
    ('set_all_elements_evaluated_before_hash_control', '{(alias := inputs), (alias := {})}', False),
    ('dict_comp_unhashable', '{(alias := inputs): 1 for item in (0,)}', True),
    ('unpack_failure', 'alias = inputs\na, b = (1,)\nalias = {}', True),
    ('assertion_failure', 'alias = inputs\nassert False\nalias = {}', True),
    ('delete_unbound', 'alias = inputs\ndel missing\nalias = {}', True),
    ('dict_unhashable_control', '{(alias := inputs): 1}', True),
    ('straight_clear_safe_set', 'alias = inputs\nalias = {}\n{1, 2}', False),
    ('safe_set_no_input', '{1, 2}', False),
)


def main():
    # --cli chooses the existing formal SDK project builder; other arguments
    # retain its --product, --work, --report interface.
    cli = '--cli' in sys.argv
    if cli:
        sys.argv.remove('--cli')
    directory = Path(__file__).resolve().parents[1] / 'python-alias-facts-review-20261008'
    sys.path.insert(0, str(directory))
    name = 'reproduce_exception_cli.py' if cli else 'reproduce_exception_alias.py'
    spec = importlib.util.spec_from_file_location('original_exception_probe', directory / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CASES = CASES
    module.main()


if __name__ == '__main__':
    main()
