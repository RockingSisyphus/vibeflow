"""Language-neutral resource descriptors and in-memory catalogs."""

from vibeflow.core.descriptors.json_values import freeze_json, freeze_mapping, thaw_json
from vibeflow.core.descriptors.ownership import ResourceOwner
from vibeflow.core.descriptors.node_types import NodeTypeDescriptor

from vibeflow.core.descriptors.catalogs import BaseLibCatalog, CapabilityCatalog, DataSchemaRegistry, DescriptorCatalogError, DescriptorCatalogs, NodeCatalog, PluginCatalog, SchemaRegistry
from vibeflow.core.descriptors.models import IMPLEMENTATION_COMPLETIONS, IMPLEMENTATION_LANGUAGES, IMPLEMENTATION_TARGETS, JSON_SCHEMA_2020_12, SOURCE_LOCATOR_KINDS, BaseLibDescriptor, CapabilityDescriptor, CapabilityOperation, CapabilityOperationDescriptor, CapabilityRequirement, CapabilityRequirementDescriptor, DataSchemaDescriptor, DescriptorModelError, ImplementationDescriptor, RuleImplementationDescriptor, NodeContractDescriptor, NodeDescriptor, PluginDescriptor, SourceLocator
from vibeflow.core.descriptors._resource_models import PLUGIN_TYPES
from vibeflow.core.descriptors.catalogs import RuleCatalog, RulesetCatalog
from vibeflow.core.descriptors.contributions import ContributionBuilder, PluginContributions, ResourceOrigin, compose_contributions
from vibeflow.core.descriptors.plugin_selection import (
    PluginResolution,
    PluginReviewRecord,
    PluginSelection,
    PluginSelectionError,
    ResolvedPluginSelection,
    review_plugin_selections,
    resolve_plugin_selections,
)

__all__ = [
    "freeze_json", "freeze_mapping", "thaw_json",
    "ContributionBuilder", "PluginContributions", "ResourceOrigin", "ResourceOwner", "compose_contributions",
    "RuleCatalog", "RulesetCatalog",
    "IMPLEMENTATION_COMPLETIONS",
    "IMPLEMENTATION_LANGUAGES",
    "IMPLEMENTATION_TARGETS",
    "JSON_SCHEMA_2020_12",
    "SOURCE_LOCATOR_KINDS",
    "BaseLibCatalog",
    "BaseLibDescriptor",
    "CapabilityCatalog",
    "CapabilityDescriptor",
    "CapabilityOperation",
    "CapabilityOperationDescriptor",
    "CapabilityRequirement",
    "CapabilityRequirementDescriptor",
    "DataSchemaDescriptor",
    "DataSchemaRegistry",
    "DescriptorCatalogError",
    "DescriptorCatalogs",
    "DescriptorModelError",


    "ImplementationDescriptor",
    "RuleImplementationDescriptor",
    "NodeCatalog",
    "NodeContractDescriptor",
    "NodeDescriptor", "NodeTypeDescriptor",
    "PLUGIN_TYPES",
    "PluginCatalog",
    "PluginDescriptor",
    "PluginResolution",
    "PluginReviewRecord",
    "PluginSelection",
    "PluginSelectionError",
    "ResolvedPluginSelection",
    "SchemaRegistry",
    "SourceLocator",
    "review_plugin_selections",
    "resolve_plugin_selections",
]
