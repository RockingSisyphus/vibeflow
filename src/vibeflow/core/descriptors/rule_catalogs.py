"""Typed rule catalogs with the existing descriptor conflict semantics."""

from vibeflow.core.descriptors.catalogs import _DescriptorCatalog
from vibeflow.core.rules.models import RuleDescriptor, RulesetDescriptor


class RuleCatalog(_DescriptorCatalog):
    descriptor_label = "rule"
    descriptor_type = RuleDescriptor


class RulesetCatalog(_DescriptorCatalog):
    descriptor_label = "ruleset"
    descriptor_type = RulesetDescriptor


__all__ = ["RuleCatalog", "RulesetCatalog"]
