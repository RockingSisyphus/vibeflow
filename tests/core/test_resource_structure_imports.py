import pytest
from vibeflow.targets.shared.quality_support import FileQuality, QualityStructureLimits, QualityStructureRoles
from vibeflow.targets.shared.quality_support.root_structure import analyze_root_structure
from vibeflow.targets.shared.quality_support.resource_imports import resource_import_violations

def owner(kind, identifier, path, *, role='entry', libraries=(), plugin='', lines=None):
    return {'kind': kind, 'id': identifier, 'path': path, 'role': role, 'base_libs': libraries, 'plugin_id': plugin, 'import_lines': lines, 'symbol': ''}

def check(owners, *, source='entry.py', target='helper.py', more_scopes=()):
    return resource_import_violations(source, target, ({'line': 1},), ({'id': 'selected', 'owners': owners}, *more_scopes))

def test_implementation_support_is_owned_without_granting_other_nodes_access():
    node = owner('node', 'n', 'entry.py')
    support = owner('node', 'n', 'helper.py', role='support')
    assert check([node, support]) == []
    other = owner('node', 'other', 'entry.py')
    denied = check([node, support, other])
    assert len(denied) == 1 and denied[0][1]['id'] == 'other'

def test_workflow_scopes_do_not_union_library_permissions():
    library = owner('base_lib', 'lib', 'helper.py')
    allowed = owner('node', 'n', 'entry.py', libraries=('lib',))
    denied = owner('node', 'n', 'entry.py')
    result = check([allowed, library], more_scopes=({'id': 'other', 'owners': [denied, library]},))
    assert len(result) == 1 and result[0][3] == 'other'

def test_baselib_dependencies_are_library_permissions():
    library = {**owner('base_lib', 'lib', 'entry.py'), 'dependencies': ('other',)}
    assert check([library, owner('base_lib', 'other', 'helper.py')]) == []
    assert len(check([library, owner('node', 'other', 'helper.py')])) == 1

def test_unclaimed_source_has_no_declared_resource_restriction():
    assert check([owner('node', 'n', 'elsewhere.py')]) == []

def source_file(path):
    return FileQuality(path, path.removesuffix('.py').replace('/', '.'), 1, 1, 0, 0, 0, 0, 0, (), ())

@pytest.mark.parametrize('directory', ['ordinary', 'nodes', 'task_nodes', 'custom_nodes', 'base_lib', 'plugins'])
def test_unclaimed_directory_names_do_not_assign_resource_identity(directory):
    source = source_file(f'{directory}/worker.py')
    target = source_file('utility/math.py')
    edge = (source.module, target.module)
    summary, findings = analyze_root_structure((source, target), {source.module: (target.module,)}, {edge: ({'path': source.path, 'line': 1, 'column': 1},)}, QualityStructureLimits())
    assert findings == ()
    assert summary['root_layout']['code_files'] == 2
    assert summary['root_layout']['code_dirs'] == 2
    assert summary['root_layout']['max_code_dir_depth'] == 1

@pytest.mark.parametrize(('kind', 'code'), [('node', 'NODE_UNDECLARED_PROJECT_IMPORT'), ('base_lib', 'BASE_LIB_UPWARD_IMPORT'), ('plugin', 'PLUGIN_NODE_IMPORT')])
def test_declared_import_restrictions_use_ownership_in_any_directory(kind, code):
    source, target = (source_file('ordinary/entry.py'), source_file('ordinary/neighbor.py'))
    edge = (source.module, target.module)
    scopes = ({'id': 'chosen', 'owners': [owner(kind, 'declared', source.path)]},)
    summary, findings = analyze_root_structure((source, target), {source.module: (target.module,)}, {edge: ({'path': source.path, 'line': 7, 'column': 2},)}, QualityStructureLimits(), roles=QualityStructureRoles(_resource_scopes=scopes))
    assert len(findings) == 1
    assert findings[0].rule_id == 'QUALITY.STRUCTURE.' + code
    assert findings[0].details['resource_id'] == 'declared'
    assert findings[0].details['workflow_scope'] == 'chosen'
    assert findings[0].source_location == {'path': source.path, 'line': 7, 'column': 2}
    assert summary['root_layout']['code_files'] == 2

def test_declared_support_is_not_granted_by_parent_directory():
    entry, neighbor = (source_file('library/entry.py'), source_file('library/neighbor.py'))
    outside = source_file('utility/math.py')
    edges = {entry.module: (neighbor.module,), neighbor.module: (outside.module,)}
    sites = {(source, targets[0]): ({'line': 1},) for source, targets in edges.items()}
    declared = owner('base_lib', 'library', entry.path)
    _, findings = analyze_root_structure((entry, neighbor, outside), edges, sites, QualityStructureLimits(), roles=QualityStructureRoles(_resource_scopes=({'id': 'chosen', 'owners': [declared]},)))
    assert [finding.object_id for finding in findings] == [f'{entry.module} -> {neighbor.module}']
    support = owner('base_lib', 'library', neighbor.path, role='support')
    _, findings = analyze_root_structure((entry, neighbor, outside), edges, sites, QualityStructureLimits(), roles=QualityStructureRoles(_resource_scopes=({'id': 'chosen', 'owners': [declared, support]},)))
    assert [finding.object_id for finding in findings] == [f'{neighbor.module} -> {outside.module}']
