"""Identity adapters and worker encoding are independent of analysis effects."""
from types import SimpleNamespace
from vibeflow.targets.javascript.build.fact_views import JavascriptFacts
from vibeflow.targets.javascript.build.rule_wire import rule_wire_facts


def test_worker_encoding_does_not_trigger_project_analysis():
    class Analysis:
        def project_facts(self,*_):
            raise AssertionError('encoding performed analysis')
    assert rule_wire_facts({'sources':[],'analysis_cache':Analysis()}) == {'sources':[]}


def test_javascript_views_track_source_ownership_configuration_and_extras():
    adapter = JavascriptFacts('node')
    facts = {'sources':[{'path':'same.ts','text':'export const x=1;'}],
        'source_owners':[{'node_type': 'vibeflow.node', 'path':'same.ts','kind':'node','id':'left'}],
        'import_policy':{'allow':['left']},'plugins':{'limit':1}}
    first = adapter.capture(facts)
    assert adapter.capture(facts) is first
    for changed in ({'sources':[{'path':'same.ts','text':'export const x=2;'}]},
        {'source_owners':[{'node_type': 'vibeflow.node', 'path':'same.ts','kind':'node','id':'right'}]},
        {'import_policy':{'allow':['right']}},{'plugins':{'limit':2}}):
        assert adapter.capture({**facts,**changed}).identity != first.identity
    extra = SimpleNamespace(value=1)
    assert adapter.capture({**facts,'extra':extra}).identity != adapter.capture({**facts,'extra':extra}).identity


def test_catalog_changes_remain_part_of_identity_without_duplicate_declarations(monkeypatch):
    from vibeflow.targets.javascript.build import fact_views
    settings={'limit':1}
    monkeypatch.setattr(fact_views,'contribution_facts',lambda _: {'plugins':dict(settings)})
    adapter=JavascriptFacts('node')
    facts={'catalogs':object(),'plugins':{'limit':1},'sources':[]}
    assert fact_views.identity_facts(facts)['catalog_changes']=={}
    first=adapter.capture(facts)
    settings['limit']=2
    changed=adapter.capture(facts)
    assert changed.identity!=first.identity
    assert fact_views.identity_facts(facts)['catalog_changes']=={'plugins':{'limit':2}}
