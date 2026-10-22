"""Resource relationship policy is independent of directory structure checks."""
import pytest
from tests.fixtures.support.resource_rules import owner, check


def test_implementation_support_is_owned_without_granting_other_nodes_access():
    node = owner('node', 'n', 'entry.py')
    support = owner('node', 'n', 'helper.py', role='support')
    assert not check([node, support])
    other = owner('node', 'other', 'entry.py')
    denied = check([node, support, other])
    assert len(denied) == 1 and "other" in denied[0].message


def test_workflow_scopes_do_not_union_library_permissions():
    library = owner('base_lib', 'lib', 'helper.py')
    allowed = owner('node', 'n', 'entry.py', libraries=('lib',))
    denied = owner('node', 'n', 'entry.py')
    result = check([allowed, library], more_scopes=({'id': 'other', 'owners': [denied, library]},))
    assert len(result) == 1 and result[0].details['workflow'] == 'other'


def test_baselib_dependencies_are_library_permissions():
    library = {**owner('base_lib', 'lib', 'entry.py'), 'dependencies': ('other',)}
    assert not check([library, owner('base_lib', 'other', 'helper.py')])
    assert len(check([library, owner('node', 'other', 'helper.py')])) == 1


def test_unclaimed_source_has_no_declared_resource_restriction():
    assert not check([owner('node', 'n', 'elsewhere.py')])


@pytest.mark.parametrize('directory', ['ordinary', 'nodes', 'task_nodes', 'custom_nodes', 'base_lib', 'plugins'])
def test_directory_names_do_not_assign_resource_identity(directory):
    assert not check([], source=f'{directory}/worker.py', target='utility/math.py')
    declared = owner('node', 'n', f'{directory}/worker.py')
    findings = check([declared], source=declared['path'], target='utility/math.py')
    assert [item.rule_id for item in findings] == ['RESOURCE.REFERENCE.UNDECLARED']


def test_declared_support_is_not_granted_by_parent_directory():
    entry = owner('base_lib', 'library', 'library/entry.py')
    assert check([entry], source=entry['path'], target='library/neighbor.py')
    support = owner('base_lib', 'library', 'library/neighbor.py', role='support')
    assert not check([entry,support], source=entry['path'], target=support['path'])
    assert check([entry,support], source=support['path'], target='utility/math.py')
