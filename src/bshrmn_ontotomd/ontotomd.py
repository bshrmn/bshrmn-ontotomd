import logging
from dataclasses import asdict, dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import SimpleQueue
from typing import Optional, TypeVar
from urllib.parse import urlparse

from pydantic import AnyUrl
from rdflib import BNode, Literal, URIRef
from rdflib import Graph as RdfGraph
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS, split_uri
from rich import print
from rich.progress import Progress, SpinnerColumn, TextColumn, track
from yaml import SafeDumper, dump

from bshrmn_ontotomd import (
    GlobalParamsConfig,
    LoggingParamsConfig,
    PreloadConfig,
    ProcessConfig,
)

logger = logging.getLogger(__name__)

# Default namespaces to preload locally
PRELOAD_NAMESPACES = [
    "http://www.w3.org/2002/07/owl#",
    "http://www.w3.org/2004/02/skos/core#",
    "http://xmlns.com/foaf/0.1/",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://purl.org/dc/elements/1.1/",
    "http://purl.org/dc/dcam/",
    "http://purl.org/dc/dcmitype/",
    "http://purl.org/dc/terms/",
]

# Supported extensions for local ontos
ONTO_FILE_EXTENSIONS = {
    ".owl",
    ".rdf",
    ".ttl",
    ".n3",
}

# Categories to be made into pages
CLASS_TYPES = {
    RDFS.Class,
    OWL.Class,
}

INDIVIDUAL_TYPES = {
    OWL.NamedIndividual,
}

PROPERTY_TYPES = {
    RDF.Property,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
}

ALIAS_PROPERTIES = {
    SKOS.prefLabel,
    RDFS.label,
    SKOS.altLabel,
}

DESCRIPTION_PROPERTIES = {
    DCTERMS.abstract,
    RDFS.comment,
    SKOS.note,
    SKOS.definition,
    DC.description,
    DCTERMS.description,
    SKOS.historyNote,
    SKOS.scopeNote,
    SKOS.example,
}

# Some URIRef values should be left as raw links instead of aliased to another value
# Examples: ontologies, documentation, web pages, etc.
# Attempting to fetch them could result in long load times before falling back to the raw value
# NOTE: This is a rough list and should be expanded based on the use case
EXTERNAL_LINK_PROPERTIES = {
    RDFS.isDefinedBy,
    RDFS.seeAlso,
    OWL.versionIRI,
    DCTERMS.contributor,
    DCTERMS.creator,
}

T = TypeVar("T")


@dataclass
class CommandResult[T]:
    result: Optional[T] = None
    error_message: str = ""


@dataclass
class OntoResource:
    type: str = ""
    resource: URIRef = None
    name_properties: dict[URIRef, list[str]] = field(default_factory=dict)
    description_properties: dict[URIRef, list[str]] = field(default_factory=dict)
    other_properties: dict[URIRef, list[str]] = field(default_factory=dict)

    def update_names(self, key, value):
        if key in self.name_properties:
            self.name_properties[key].append(value)
        else:
            self.name_properties[key] = [value]

    def update_descriptions(self, key, value):
        if key in self.description_properties:
            self.description_properties[key].append(value)
        else:
            self.description_properties[key] = [value]

    def update_others(self, key, value):
        if key in self.other_properties:
            self.other_properties[key].append(value)
        else:
            self.other_properties[key] = [value]

    def title(self, title_priority_list: list[str]):
        for property in title_priority_list:
            if property in self.name_properties:
                return self.name_properties[property][0]

        _, local_name = split_uri(self.resource)
        return local_name


@dataclass
class OTMProcessSummary:
    # Number of classes found in primary ontology file
    primary_class_count: int = 0
    # Number of individuals found in primary ontology file
    primary_individual_count: int = 0
    # Number of properties found in primary ontology file
    primary_property_count: int = 0
    # Number of skippable or unavailable resources found in primary ontology file
    primary_skipped_count: int = 0
    # Number of stubbed resources found in primary ontology file
    stubbed_count: int = 0
    # Number of resources processed using external ontologies
    external_processed_count: int = 0
    # Number of skippable or unavailable resources found in external ontologies
    external_skipped_count: int = 0


@dataclass
class OTMSProcessDetails():
    namespaces_used : list[str] = field(default_factory=list)
    bad_namespaces : list[str] = field(default_factory=list)
    bad_resources : list[str] = field(default_factory=list)
    stubbed_resources : list[str] = field(default_factory=list)
    processed_resources : list[str] = field(default_factory=list)
    primary_unprocessed_resources : list[str] = field(default_factory=list)
    external_unprocessed_resources : list[str] = field(default_factory=list)


class OTMGlobalConfig:
    # Path to directory containing local ontologies
    ontologies_directory: Path = None
    # Path to directory for script outputs
    output_directory: Path = None
    # Ontologies stored locally
    local_ontos: dict[str, str] = {}
    # Namespaces and their associated graphs
    parsed_graphs: dict[str, RdfGraph] = {}
    # Resources that should be skipped instead of resolved
    skippable_resources: set[URIRef] = set()
    # Queue to hold resources that need to be processed
    resource_queue: SimpleQueue[URIRef] = SimpleQueue()
    # Resources that have been added to the queue
    queued_resources: set[URIRef] = set()
    # Resources that should not have pages made for them
    do_not_create_resources: set[URIRef] = set()
    # Copy of CLASS_TYPES mergeable with additional config values
    class_types_set: set[URIRef] = CLASS_TYPES.copy()
    # Copy of INDIVIDUAL_TYPES mergeable with additional config values
    individual_types_set: set[URIRef] = INDIVIDUAL_TYPES.copy()
    # Copy of PROPERTY_TYPES mergeable with additional config values
    property_types_set: set[URIRef] = PROPERTY_TYPES.copy()
    # Copy of ALIAS_PROPERTIES mergeable with additional config values
    alias_properties_set: set[URIRef] = ALIAS_PROPERTIES.copy()
    # Copy of DESCRIPTION_PROPERTIES mergeable with additional config values
    description_properties_set: set[URIRef] = DESCRIPTION_PROPERTIES.copy()
    # Copy of EXTERNAL_LINK_PROPERTIES mergeable with additional config values
    external_link_properties_set: set[URIRef] = EXTERNAL_LINK_PROPERTIES.copy()
    # Resources that could not be resolved
    bad_resources: set[URIRef] = set()
    # Namespaces whose resources should be skipped instead of resolved
    skippable_namespaces: set[URIRef] = set()
    # Namespaces that could not be resolved
    bad_namespaces: set[str] = set()
    # Resources that are only stubs in the local graph
    stubbed_resources: set[URIRef] = set()
    # Resources that have already been processed
    processed_resources: set[URIRef] = set()
    # Queue to hold external resources that need to be processed
    external_resource_queue: SimpleQueue[URIRef] = SimpleQueue()
    # List of graphs that have been changed and need to be saved locally, by namespace
    namespaces_to_save: set[str] = set()
    # Base namespaces that have been retrieved already
    retrieved_namespaces: set[str] = set()


# NOTE: This is kind of hacky but adds sequence indentation to the YAML output
class IndentedSafeDumper(SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _initialize_logger(config: LoggingParamsConfig):
    file_handler = RotatingFileHandler(
        filename=Path(config.logging_file).resolve(),
        maxBytes=config.max_file_size,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    log_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s:%(filename)s:%(lineno)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    logger.propagate = False
    logger.setLevel(config.logging_level.value)


def _get_local_ontos(directory: Path):
    return {
        file_path.stem: file_path
        for file_path in directory.iterdir()
        if file_path.is_file() and file_path.suffix in ONTO_FILE_EXTENSIONS
    }


def _clean_file_name(file_name: str):
    # NOTE: Not completely sold on this format
    # Retain some form of the ending character (http://example.com/ vs http://example.com#)
    # This also makes the file name not end with an _ or #
    if file_name[-1] == "/":
        file_name = file_name[:-1] + "_s"
    elif file_name[-1] == "#":
        file_name = file_name[:-1] + "_h"
    return file_name.replace("/", "_").replace(".", "-")


def _namespace_to_file_name(namespace: str):
    parsed_namespace = urlparse(namespace)
    onto_file_name = parsed_namespace.netloc + parsed_namespace.path
    # Add back the fragment identifier if present for consistency
    onto_file_name += "#" if namespace[-1] == "#" else ""
    return _clean_file_name(onto_file_name)


def _is_not_deprecated(resource, g: RdfGraph) -> bool:
    # The value of owl:deprecated does not seem to be restricted to booleans, so check for presence
    return (resource, OWL.deprecated, None) not in g


def _is_resource_available(resource: URIRef, default_graph: RdfGraph) -> bool:
    logger.info("Checking for resource %s", resource)

    # Check if we can access the subject's data
    if resource in OTMGlobalConfig.skippable_resources:
        logger.info("Resource can be skipped")
        return False

    # Check if this resource previously failed to be loaded
    if resource in OTMGlobalConfig.bad_resources:
        logger.info("Resource previously failed to load")
        return False

    # Split the URIRef into the namespace and resource name
    namespace, _ = split_uri(resource)
    logger.debug("Namespace is %s", namespace)

    if URIRef(namespace) in OTMGlobalConfig.skippable_namespaces:
        # Update skippable_resources for faster failing in future checks
        OTMGlobalConfig.skippable_resources.add(resource)
        logger.info("Namespace can be skipped")
        return False

    # Check if namespace previously failed to be loaded
    if namespace in OTMGlobalConfig.bad_namespaces:
        # Update bad_resources for faster failing in future checks
        OTMGlobalConfig.bad_resources.add(resource)
        logger.info("Namespace previously failed to load")
        return False

    # If a default graph is provided, prioritize that version of the resource
    if default_graph:
        # Check if resource and label are present in graph
        if (resource, RDFS.label, None) in default_graph:
            logger.info("This is in the default graph")
            return True
        else:
            # Continue, but remove the stubbed version from queue if present
            OTMGlobalConfig.queued_resources.discard(resource)
            OTMGlobalConfig.stubbed_resources.add(resource)

    # Check if namespace has been loaded
    if namespace in OTMGlobalConfig.parsed_graphs:
        candidate_graph = OTMGlobalConfig.parsed_graphs[namespace]

        # Check if resource and label are present in graph
        if (resource, RDFS.label, None) in candidate_graph:
            # Add resource to queue if it needs to be processed
            if (
                resource not in OTMGlobalConfig.queued_resources
                and resource not in OTMGlobalConfig.processed_resources
            ):
                OTMGlobalConfig.external_resource_queue.put(resource)
                OTMGlobalConfig.queued_resources.add(resource)
                logger.debug("Added resource to queue")
            logger.info("Resource found in parsed graphs")
            return True

    onto_file_name = _namespace_to_file_name(namespace)
    logger.debug("Looking for local ontology file %s", onto_file_name)

    # Check if namespace is available locally
    if onto_file_name in OTMGlobalConfig.local_ontos.keys():
        candidate_graph = (
            OTMGlobalConfig.parsed_graphs[namespace]
            if namespace in OTMGlobalConfig.parsed_graphs
            else RdfGraph()
        )
        candidate_graph.parse(
            (
                OTMGlobalConfig.ontologies_directory
                / OTMGlobalConfig.local_ontos[onto_file_name]
            ).absolute()
        )

        if len(candidate_graph) > 0:
            # Add the local data to parsed graphs
            OTMGlobalConfig.parsed_graphs[namespace] = candidate_graph

            # Check if resource and label are present in graph
            if (resource, RDFS.label, None) in candidate_graph:
                # Add resource to queue if it needs to be processed
                if (
                    resource not in OTMGlobalConfig.queued_resources
                    and resource not in OTMGlobalConfig.processed_resources
                ):
                    OTMGlobalConfig.external_resource_queue.put(resource)
                    OTMGlobalConfig.queued_resources.add(resource)
                    logger.debug("Added resource to queue")
                logger.info("Resource found in local ontology file")
                return True

    # Check if resource is available remotely
    candidate_graph = (
        OTMGlobalConfig.parsed_graphs[namespace]
        if namespace in OTMGlobalConfig.parsed_graphs
        else RdfGraph()
    )

    logger.debug("Attempting to parse foreign resource %s", resource)
    # Attempt to parse the URI
    try:
        # Try parsing based without explicit format
        candidate_graph.parse(resource)
    # TODO: Specify exception
    except:
        # Try again with explicitly XML
        try:
            logger.info("Attempting to resolve foreign resource as xml")
            candidate_graph.parse(resource, format="xml")
        # TODO: Specify exception
        except:
            logger.warning("Unable to resolve resource: %s", resource)

    if len(candidate_graph) > 0:
        # Add the remote data to parsed graphs
        OTMGlobalConfig.parsed_graphs[namespace] = candidate_graph

        # Save info to serialize later
        OTMGlobalConfig.namespaces_to_save.add(namespace)

        # Check if resource and label are present in graph
        if (resource, RDFS.label, None) in candidate_graph:
            # Add resource to queue if it needs to be processed
            if (
                resource not in OTMGlobalConfig.queued_resources
                and resource not in OTMGlobalConfig.processed_resources
            ):
                OTMGlobalConfig.external_resource_queue.put(resource)
                OTMGlobalConfig.queued_resources.add(resource)
                logger.debug("Added resource to queue")
            logger.info("Resource found at foreign location")
            return True

    # Before resolving the namespace, check if this was previously attempted
    if namespace in OTMGlobalConfig.retrieved_namespaces:
        # This saves some time when the resulting graph would be large
        logger.info("Already retrieved namespace %s during this run", namespace)
        return False

    # Attempt to resolve only the namespace to check if the issue is just the resource
    try:
        logger.debug("Attempting to resolve just namespace %s", namespace)
        # Try parsing based without explicit format
        candidate_graph.parse(namespace)
    # TODO: Specify exception
    except:
        # Try again with explicitly XML
        try:
            logger.info("Attempting to resolve foreign namespace as xml")
            candidate_graph.parse(namespace, format="xml")
        # TODO: Specify exception
        except:
            logger.warning("Unable to resolve namespace: %s", namespace)

    if len(candidate_graph) > 0:
        # Add the remote data to parsed graphs
        OTMGlobalConfig.parsed_graphs[namespace] = candidate_graph

        # Save info to serialize later
        OTMGlobalConfig.namespaces_to_save.add(namespace)

        # Check one more time if resource and label are present in graph
        if (resource, RDFS.label, None) in candidate_graph:
            # Add resource to queue if it needs to be processed
            if (
                resource not in OTMGlobalConfig.queued_resources
                and resource not in OTMGlobalConfig.processed_resources
            ):
                OTMGlobalConfig.external_resource_queue.put(resource)
                OTMGlobalConfig.queued_resources.add(resource)
                logger.debug("Added resource to queue")
            logger.info("Resource found in foreign namespace")
            return True
        else:
            # There is an issue with the resource
            OTMGlobalConfig.bad_resources.add(resource)
            logger.warning("Resource %s has been added to bad resources list", resource)
            return False

    # There is an issue with the namespace
    OTMGlobalConfig.bad_namespaces.add(namespace)
    # Update bad_resources for faster failing in future checks
    OTMGlobalConfig.bad_resources.add(resource)
    logger.warning("Unable to resolve resource and namespace for %s", resource)
    return False


def _resource_type(s, g: RdfGraph) -> str:
    for category in OTMGlobalConfig.class_types_set:
        if (s, RDF.type, category) in g:
            return "Class"

    for category in OTMGlobalConfig.individual_types_set:
        if (s, RDF.type, category) in g:
            return "Individual"

    for category in OTMGlobalConfig.property_types_set:
        if (s, RDF.type, category) in g:
            return "Property"


def _resource_info(s: URIRef, g: RdfGraph) -> OntoResource:
    resource_info = OntoResource()
    resource_info.type = _resource_type(s, g)
    resource_info.resource = s

    for p, o in g.predicate_objects(s):
        if p in OTMGlobalConfig.alias_properties_set:
            resource_info.update_names(p, o)
        elif p in OTMGlobalConfig.description_properties_set:
            resource_info.update_descriptions(p, o)
        else:
            resource_info.update_others(p, o)

    return resource_info


def _resource_to_file_path(resource: URIRef) -> Path:
    # Strip the scheme and split into namespace and local name
    parsed_uri = urlparse(resource)
    namespace, local_name = split_uri(
        parsed_uri.geturl().replace(parsed_uri.scheme + "://", "", 1)
    )

    # Local name cannot be "index" or "log" since they are reserved in OKF
    if local_name == "index":
        local_name = "index_term"
    elif local_name == "log":
        local_name = "log_term"

    if OTMGlobalConfig.output_directory:
        return (
            OTMGlobalConfig.output_directory
            / _clean_file_name(namespace)
            / _clean_file_name(local_name)
        )
    else:
        return Path(_clean_file_name(namespace)) / _clean_file_name(local_name)


def _common_name(resource: URIRef, g: RdfGraph) -> str:
    for alias in OTMGlobalConfig.alias_properties_set:
        # Loop through potential aliases
        if (resource, alias, None) in g:
            results = g.objects(resource, alias)
            return str(next(results))

    # Fallback is the local name from the URIRef
    _, local_name = split_uri(resource)
    return local_name


def _parse_restriction(restriction: URIRef, g: RdfGraph):
    # Expect to have an onProperty relationship
    restricted_property = g.value(restriction, OWL.onProperty)

    # Possible restriction types checked below
    if (restriction, OWL.hasSelf, None) in g:
        # The value of owl:hasSelf does not seem to be restricted to booleans, so check for presence
        return f"({_stringify_term(restricted_property, g)} has self as a value)"
    elif (restriction, OWL.hasValue, None) in g:
        value = g.value(restriction, OWL.hasValue)
        return f"({_stringify_term(restricted_property, g)} has value {_stringify_term(value, g)})"
    # Unqualified cardinality
    elif (restriction, OWL.cardinality, None) in g:
        cardinality = g.value(restriction, OWL.cardinality)
        return f"({_stringify_term(restricted_property, g)} has cardinality of exactly {cardinality})"
    elif (restriction, OWL.minCardinality, None) in g:
        min_cardinality = g.value(restriction, OWL.minCardinality)
        max_cardinality = g.value(restriction, OWL.maxCardinality)

        if max_cardinality is not None:
            return f"({_stringify_term(restricted_property, g)} has cardinality between {min_cardinality} and {max_cardinality})"
        else:
            return f"({_stringify_term(restricted_property, g)} has cardinality of at least {min_cardinality})"
    elif (restriction, OWL.maxCardinality, None) in g:
        max_cardinality = g.value(restriction, OWL.maxCardinality)
        return f"({_stringify_term(restricted_property, g)} has cardinality of at most {max_cardinality})"
    # Qualified cardinality
    elif (restriction, OWL.qualifiedCardinality, None) in g:
        cardinality = g.value(restriction, OWL.qualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(
            restriction, OWL.onDataRange
        )
        return f"({_stringify_term(restricted_property, g)} has exactly {cardinality} {range})"
    elif (restriction, OWL.minQualifiedCardinality, None) in g:
        min_cardinality = g.value(restriction, OWL.minQualifiedCardinality)
        max_cardinality = g.value(restriction, OWL.maxQualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(
            restriction, OWL.onDataRange
        )

        if max_cardinality is not None:
            return f"({_stringify_term(restricted_property, g)} has between {min_cardinality} and {max_cardinality} {range})"
        else:
            return f"({_stringify_term(restricted_property, g)} has at least {min_cardinality} {range})"
    elif (restriction, OWL.maxQualifiedCardinality, None) in g:
        max_cardinality = g.value(restriction, OWL.maxQualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(
            restriction, OWL.onDataRange
        )
        return f"({_stringify_term(restricted_property, g)} has at most {max_cardinality} {range})"
    elif (restriction, OWL.hasValue, None) in g:
        value = g.value(restriction, OWL.hasValue)
        return f"({_stringify_term(restricted_property, g)} has value {_stringify_term(value, g)})"
    elif (restriction, OWL.someValuesFrom, None) in g:
        range = g.value(restriction, OWL.someValuesFrom)
        return f"({_stringify_term(restricted_property, g)} has some values from {_stringify_term(range, g)})"
    elif (restriction, OWL.allValuesFrom, None) in g:
        range = g.value(restriction, OWL.allValuesFrom)
        return f"({_stringify_term(restricted_property, g)} has only values from {_stringify_term(range, g)})"
    else:
        logger.warning("Unknown restriction type for %s", restriction)
        return (
            f"({_stringify_term(restricted_property, g)} has unknown restriction type)"
        )


def _is_list_node(subject, g: RdfGraph) -> bool:
    return (subject, RDF.first, None) in g and (subject, RDF.rest, None) in g


def _stringify_term(
    term, g: RdfGraph, list_joiner: str = " ", skip_property_chain: bool = False
) -> str:
    logger.debug("Stringify: %s | Type: %s", term, type(term))

    # NOTE: May need onDatatype in the future: withRestrictions minExclusive minInclusive maxExclusive maxInclusive
    if isinstance(term, URIRef):
        if _is_resource_available(term, g):
            namespace, _ = split_uri(term)
            # Check if in passed graph first
            if (term, RDFS.label, None) in g:
                return f"[{_common_name(term, g)}]({_resource_to_file_path(term)}.md)"
            else:
                return f"[{_common_name(term, OTMGlobalConfig.parsed_graphs[namespace])}]({_resource_to_file_path(term)}.md)"

        # Return URI as a backup
        return str(term)
    if isinstance(term, BNode):
        if (term, RDF.type, OWL.Restriction) in g:
            return _parse_restriction(term, g)
        elif (term, OWL.unionOf, None) in g:
            value = g.value(term, OWL.unionOf)
            return f"{_stringify_term(value, g, list_joiner=' or ')}"
        elif (term, OWL.intersectionOf, None) in g:
            value = g.value(term, OWL.intersectionOf)
            return f"{_stringify_term(value, g, list_joiner=' and ')}"
        elif (term, OWL.complementOf, None) in g:
            value = g.value(term, OWL.complementOf)
            return f"not {_stringify_term(value, g)}"
        elif (term, OWL.someValuesFrom, None) in g:
            value = g.value(term, OWL.someValuesFrom)
            return f"some values from {_stringify_term(value, g)}"
        elif (term, OWL.oneOf, None) in g:
            value = g.value(term, OWL.oneOf)
            return f"one of {_stringify_term(value, g, list_joiner=', ')}"
        elif (term, OWL.inverseOf, None) in g:
            value = g.value(term, OWL.inverseOf)
            return f"inverse of {_stringify_term(value, g)}"
        # This feels a little hacky, but seems to work
        elif not skip_property_chain and (None, OWL.propertyChainAxiom, term) in g:
            return f"{_stringify_term(term, g, list_joiner=' -> ', skip_property_chain=True)}"
        # General list check
        elif _is_list_node(term, g):
            list_items = []
            current = term
            while current != RDF.nil:
                first = g.value(current, RDF.first)
                list_items.append(_stringify_term(first, g))
                current = g.value(current, RDF.rest)
            return f"({list_joiner.join(list_items)})"
        else:
            logger.warning(
                "Current BNode is not a list node or a known collection type"
            )
            bnode_relations = []
            for p, o in g.predicate_objects(term):
                bnode_relations.append(p, o)
            logger.warning("BNode contains: %s", bnode_relations)
    if isinstance(term, Literal):
        # NOTE: Maybe add language logic here?
        return str(term)

    # Log unknown type
    logger.warning("Unable to stringify type %s", type(term))
    return str(term)


def _resource_axiom_annotations(s, p, o, g: RdfGraph):
    axiom_anotations: dict[URIRef, list[str]] = {}

    # Find axiom nodes associated with (s, p, o) triple
    for axiom in g.subjects(OWL.annotatedSource, s):
        if (axiom, OWL.annotatedProperty, p) not in g:
            continue
        if (axiom, OWL.annotatedTarget, o) not in g:
            continue

        # Get annotations
        for predicate, object in g.predicate_objects(axiom):
            if predicate in (
                OWL.annotatedSource,
                OWL.annotatedProperty,
                OWL.annotatedTarget,
                RDF.type,
            ):
                continue

            if predicate in axiom_anotations:
                axiom_anotations[predicate].append(object)
            else:
                axiom_anotations[predicate] = [object]

    return axiom_anotations


def _resource_page(resource: OntoResource, g: RdfGraph):
    # Create a directory for the namespace if needed
    resource_path = _resource_to_file_path(resource.resource)
    resource_path.parent.mkdir(parents=True, exist_ok=True)

    with open(f"{resource_path}.md", "w", encoding="utf-8") as file:
        # YAML frontmatter
        file.write("---\n")
        file.write(f"type: {resource.type}\n")
        file.write(f"title: {resource.title(OTMGlobalConfig.alias_properties_set)}\n")
        file.write(f"resource: {resource.resource}\n")
        if resource.name_properties:
            # Ignore duplicates here
            seen_aliases = set()

            file.write("aliases:\n")
            for alias_list in resource.name_properties.values():
                for alias in alias_list:
                    if str(alias) not in seen_aliases:
                        seen_aliases.add(str(alias))
                        file.write(f"  - {alias}\n")
        file.write("---\n")
        # Name properties
        if resource.name_properties:
            file.write("# Name Properties\n")
            for pk, pvs in resource.name_properties.items():
                file.write(f"- propertyKey: {_stringify_term(pk, g)}\n")
                for pv in pvs:
                    if pk not in OTMGlobalConfig.external_link_properties_set:
                        file.write(f"  - propertyValue: {_stringify_term(pv, g)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(
                        resource.resource, pk, pv, g
                    )
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(
                                f"    - annotationKey: {_stringify_term(ak, g)}\n"
                            )
                            for av in avs:
                                if (
                                    ak
                                    not in OTMGlobalConfig.external_link_properties_set
                                ):
                                    file.write(
                                        f"      - annotationValue: {_stringify_term(av, g)}\n"
                                    )
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")

        # Description properties
        if resource.description_properties:
            file.write("# Description Properties\n")
            for pk, pvs in resource.description_properties.items():
                file.write(f"- propertyKey: {_stringify_term(pk, g)}\n")
                for pv in pvs:
                    if pk not in OTMGlobalConfig.external_link_properties_set:
                        file.write(f"  - propertyValue: {_stringify_term(pv, g)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(
                        resource.resource, pk, pv, g
                    )
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(
                                f"    - annotationKey: {_stringify_term(ak, g)}\n"
                            )
                            for av in avs:
                                if (
                                    ak
                                    not in OTMGlobalConfig.external_link_properties_set
                                ):
                                    file.write(
                                        f"      - annotationValue: {_stringify_term(av, g)}\n"
                                    )
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")

        # Other properties
        if resource.other_properties:
            file.write("# Other Properties\n")
            for pk, pvs in resource.other_properties.items():
                file.write(f"- propertyKey: {_stringify_term(pk, g)}\n")
                for pv in pvs:
                    if pk not in OTMGlobalConfig.external_link_properties_set:
                        file.write(f"  - propertyValue: {_stringify_term(pv, g)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(
                        resource.resource, pk, pv, g
                    )
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(
                                f"    - annotationKey: {_stringify_term(ak, g)}\n"
                            )
                            for av in avs:
                                if (
                                    ak
                                    not in OTMGlobalConfig.external_link_properties_set
                                ):
                                    file.write(
                                        f"      - annotationValue: {_stringify_term(av, g)}\n"
                                    )
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")


def _url_to_uriref(url: AnyUrl) -> URIRef:
    return URIRef(str(url))


def preload_ontos(
    global_params: GlobalParamsConfig, preload: PreloadConfig
) -> CommandResult[int]:
    _initialize_logger(global_params.logging_params)
    logger.info("Preload script starting")

    total_preloads = 0

    # Check what local ontologies are known
    OTMGlobalConfig.local_ontos.update(
        _get_local_ontos(global_params.ontologies_directory)
    )

    # Merge the default preload namespaces with any additional targets
    preload_namespaces_set = set(
        PRELOAD_NAMESPACES + (preload.targets if preload.targets is not None else [])
    )
    for ns in track(preload_namespaces_set, description="Preloading namespaces..."):
        logger.info("Preloading namespace: %s", ns)

        graph = RdfGraph()

        onto_file_name = _namespace_to_file_name(ns)
        if (
            preload.overwrite_local_files
            or onto_file_name not in OTMGlobalConfig.local_ontos.keys()
        ):
            # Attempt to parse the URI
            try:
                # Try parsing based without explicit format
                graph.parse(ns)
            # TODO: Specify exception
            except:
                # Try again with explicitly XML
                try:
                    logger.info("Attempting to resolve foreign namespace as xml")
                    graph.parse(ns, format="xml")
                # TODO: Specify exception
                except:
                    logger.warning("Unable to resolve namespace: %s", ns)

            if len(graph) > 0:
                loc = (
                    global_params.ontologies_directory / f"{onto_file_name}.rdf"
                ).absolute()
                logger.info("Writing ontology to file %s", loc)
                graph.serialize(destination=loc, format="xml")
                total_preloads += 1
            else:
                logger.info("Ontology graph was empty after parsing")
        else:
            logger.info("Local onto found for namespace: %s", ns)

    logger.info(f"Script finished with {total_preloads} namespaces preloaded")
    return CommandResult[int](total_preloads)


def process_onto(
    global_params: GlobalParamsConfig, process: ProcessConfig
) -> CommandResult[OTMProcessSummary]:
    _initialize_logger(global_params.logging_params)
    logger.info("Process script starting")

    OTMGlobalConfig.ontologies_directory = global_params.ontologies_directory
    OTMGlobalConfig.output_directory = global_params.output_directory

    # Check what local ontologies are known
    OTMGlobalConfig.local_ontos.update(
        _get_local_ontos(OTMGlobalConfig.ontologies_directory)
    )

    g = RdfGraph()

    try:
        print(f"Parsing {process.target}")

        g.parse(process.target, format="xml")
        OTMGlobalConfig.parsed_graphs[process.target_namespace] = (
            g  # NOTE: no good way to determine this so must be passed in
        )

        # Make sure the graph is populated
        if len(g) == 0:
            error_message = "No resources found in target"
            logger.critical(error_message)
            return CommandResult[OTMProcessSummary](None, error_message=error_message)
    # TODO: Specify exception
    except:
        error_message = "Unable to parse primary target"
        logger.critical(error_message)
        return CommandResult[OTMProcessSummary](None, error_message=error_message)

    # Merge config values if present
    if process.skippable_resources is not None:
        OTMGlobalConfig.skippable_resources.update(
            list(map(_url_to_uriref, process.skippable_resources))
        )
    if process.skippable_namespaces is not None:
        OTMGlobalConfig.skippable_namespaces.update(
            list(map(_url_to_uriref, process.skippable_namespaces))
        )
    if process.do_not_create_resources is not None:
        OTMGlobalConfig.do_not_create_resources.update(
            list(map(_url_to_uriref, process.do_not_create_resources))
        )
    if process.class_types is not None:
        OTMGlobalConfig.class_types_set.update(
            list(map(_url_to_uriref, process.class_types))
        )
    if process.individual_types is not None:
        OTMGlobalConfig.individual_types_set.update(
            list(map(_url_to_uriref, process.individual_types))
        )
    if process.property_types is not None:
        OTMGlobalConfig.property_types_set.update(
            list(map(_url_to_uriref, process.property_types))
        )
    if process.alias_properties is not None:
        OTMGlobalConfig.alias_properties_set.update(
            list(map(_url_to_uriref, process.alias_properties))
        )
    if process.description_properties is not None:
        OTMGlobalConfig.description_properties_set.update(
            list(map(_url_to_uriref, process.description_properties))
        )
    if process.external_link_properties is not None:
        OTMGlobalConfig.external_link_properties_set.update(
            list(map(_url_to_uriref, process.external_link_properties))
        )

    # For summary
    class_count = 0
    individual_count = 0
    property_count = 0

    # Loop for all desired categories and add to queue for processing
    print("Searching for classes in primary onto")
    for category in OTMGlobalConfig.class_types_set:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description=f"Searching for {category}...", total=None)

            for s in g.subjects(RDF.type, category, unique=True):
                if isinstance(s, URIRef) and _is_not_deprecated(s, g):
                    logger.debug("Adding %s (%s) to queue for processing", s, category)
                    OTMGlobalConfig.resource_queue.put(s)
                    OTMGlobalConfig.queued_resources.add(s)
                    class_count += 1

    print("Searching for individuals in primary onto")
    for category in OTMGlobalConfig.individual_types_set:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description=f"Searching for {category}...", total=None)

            for s in g.subjects(RDF.type, category, unique=True):
                if isinstance(s, URIRef) and _is_not_deprecated(s, g):
                    logger.debug("Adding %s (%s) to queue for processing", s, category)
                    OTMGlobalConfig.resource_queue.put(s)
                    OTMGlobalConfig.queued_resources.add(s)
                    individual_count += 1

    print("Searching for properties in primary onto")
    for category in OTMGlobalConfig.property_types_set:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description=f"Searching for {category}...", total=None)

            for s in g.subjects(RDF.type, category, unique=True):
                if isinstance(s, URIRef) and _is_not_deprecated(s, g):
                    logger.debug("Adding %s (%s) to queue for processing", s, category)
                    OTMGlobalConfig.resource_queue.put(s)
                    OTMGlobalConfig.queued_resources.add(s)
                    property_count += 1

    logger.debug("Total classes found in primary target: %s", class_count)
    logger.debug("Total individuals found in primary target: %s", individual_count)
    logger.debug("Total properties found in primary target: %s", property_count)

    # For summary
    primary_skipped_count = 0
    stubbed_count = 0
    external_processed_count = 0
    external_skipped_count = 0

    # Process all subjects in queue
    logger.info("Processing resources from primary target")
    print("Processing resources from primary target")
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description="Processing resources...", total=None)

            while not OTMGlobalConfig.resource_queue.empty():
                s = OTMGlobalConfig.resource_queue.get()
                logger.debug("Processing: %s", s)

                # Do not create pages for these resources
                if (
                    s in OTMGlobalConfig.do_not_create_resources
                    or not _is_resource_available(s, g)
                ):
                    logger.debug("Skipping page creation")
                    # Update processed resources
                    OTMGlobalConfig.queued_resources.discard(s)
                    OTMGlobalConfig.processed_resources.add(s)
                    primary_skipped_count += 1
                    continue

                # Also skip if the local version is a stub
                if s in OTMGlobalConfig.stubbed_resources:
                    logger.debug("This stub will be processed later")
                    stubbed_count += 1
                    continue

                # Gather resource info
                onto_resource = _resource_info(s, g)
                _resource_page(onto_resource, g)

                # Update processed resources
                OTMGlobalConfig.queued_resources.discard(s)
                OTMGlobalConfig.processed_resources.add(s)

        logger.info("Processing external resources")
        print("Processing external resources")

        # Process any external resources that were used
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description="Processing resources...", total=None)

            while not OTMGlobalConfig.external_resource_queue.empty():
                s = OTMGlobalConfig.external_resource_queue.get()
                logger.debug("Processing: %s", s)

                # Find the right graph to use
                external_namespace, _ = split_uri(s)
                external_graph = OTMGlobalConfig.parsed_graphs[external_namespace]

                # Do not create pages for these resources
                if (
                    s in OTMGlobalConfig.do_not_create_resources
                    or not _is_resource_available(s, external_graph)
                ):
                    logger.debug("Skipping page creation")
                    # Update processed resources
                    OTMGlobalConfig.queued_resources.discard(s)
                    OTMGlobalConfig.processed_resources.add(s)
                    external_skipped_count += 1
                    continue

                # Gather resource info
                onto_resource = _resource_info(s, external_graph)
                _resource_page(onto_resource, external_graph)

                # Update processed resources
                OTMGlobalConfig.queued_resources.discard(s)
                OTMGlobalConfig.processed_resources.add(s)
                external_processed_count += 1
    # TODO: Specify exception
    except:
        error_message = (
            "A critical exception occurred during processing. Check logs for details"
        )
        logger.critical(error_message)
        return CommandResult[OTMProcessSummary](None, error_message=error_message)
    finally:
        print("Finalizing processing")

        # Save any new or updated graphs locally
        for namespace in track(
            OTMGlobalConfig.namespaces_to_save,
            "Saving discovered namespaces locally...",
        ):
            logger.info("Saving graph associated with namespace: %s", namespace)
            onto_file_name = _namespace_to_file_name(namespace)
            loc = (
                OTMGlobalConfig.ontologies_directory / f"{onto_file_name}.rdf"
            ).absolute()
            graph = OTMGlobalConfig.parsed_graphs[namespace]
            graph.serialize(destination=loc, format="xml")

        # Populate run details
        process_details = OTMSProcessDetails(
            namespaces_used=list(OTMGlobalConfig.parsed_graphs.keys()),
            bad_namespaces=list(OTMGlobalConfig.bad_namespaces),
            bad_resources=list(map(str, OTMGlobalConfig.bad_resources)),
            stubbed_resources=list(map(str, OTMGlobalConfig.stubbed_resources)),
            processed_resources=list(map(str, OTMGlobalConfig.processed_resources)),
        )

        # Include any resources that went unprocessed
        if not OTMGlobalConfig.resource_queue.empty():
            while not OTMGlobalConfig.resource_queue.empty():
                process_details.primary_unprocessed_resources.append(
                    str(OTMGlobalConfig.resource_queue.get())
                )
        if not OTMGlobalConfig.external_resource_queue.empty():
            while not OTMGlobalConfig.external_resource_queue.empty():
                process_details.external_unprocessed_resources.append(
                    str(OTMGlobalConfig.external_resource_queue.get())
                )

        # Dump details to file
        base_details_path = (
            OTMGlobalConfig.output_directory / "details.yaml"
            if OTMGlobalConfig.output_directory
            else Path("details.yaml")
        )
        with open(base_details_path, "w", encoding="utf-8") as base_details_file:
            # NOTE: I would like to use safe_dump here but I cannot pass the custom SafeDumper to it
            dump(
                asdict(process_details),
                base_details_file,
                Dumper=IndentedSafeDumper,
                allow_unicode=True,
                encoding="utf-8",
                sort_keys=False,
            )

        print("Creating index.md files")

        # Create top-level index.md file
        # Sort namespaces alphabetically
        # NOTE: This will not always produce an intuitive result (e.g. the expected name could appear later in the URI)
        sorted_namespaces = sorted(OTMGlobalConfig.parsed_graphs.keys())

        base_index_path = (
            OTMGlobalConfig.output_directory / "index.md"
            if OTMGlobalConfig.output_directory
            else Path("index.md")
        )
        with open(base_index_path, "w", encoding="utf-8") as base_index_file:
            base_index_file.write("# Namespaces\n")

            for namespace in sorted_namespaces:
                if OTMGlobalConfig.output_directory:
                    base_index_file.write(
                        f"- [{namespace}]({OTMGlobalConfig.output_directory / _namespace_to_file_name(namespace)})\n"
                    )
                else:
                    base_index_file.write(
                        f"- [{namespace}]({_namespace_to_file_name(namespace)})\n"
                    )

        # Create namespace-level index.md files
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(
                description="Creating namespace-level index.md files...", total=None
            )

            for directory_name in OTMGlobalConfig.output_directory.iterdir():
                if directory_name.is_file():
                    continue

                onto_directory_path = (
                    OTMGlobalConfig.output_directory / directory_name
                    if OTMGlobalConfig.output_directory
                    else Path(directory_name)
                )
                with open(
                    onto_directory_path / "index.md", "w", encoding="utf-8"
                ) as namespace_index_file:
                    namespace_index_file.write("# Resources\n")

                    for file_name in onto_directory_path.iterdir():
                        if file_name == "index.md" or directory_name == "log.md":
                            continue

                        resource_title = ""
                        with open(
                            onto_directory_path / file_name, "r", encoding="utf-8"
                        ) as resource_file:
                            for i, line in enumerate(resource_file):
                                # NOTE: Magic number, but that part of the frontmatter should be consistent
                                if i == 2:
                                    # NOTE: Also a little magical, but grab everything after "title: "
                                    resource_title = line[7:].strip()

                        if resource_title:
                            namespace_index_file.write(
                                f"- [{resource_title}]({file_name})\n"
                            )

    logger.info("Script completed")
    summary = OTMProcessSummary(
        primary_class_count=class_count,
        primary_individual_count=individual_count,
        primary_property_count=property_count,
        primary_skipped_count=primary_skipped_count,
        stubbed_count=stubbed_count,
        external_processed_count=external_processed_count,
        external_skipped_count=external_skipped_count,
    )
    return CommandResult[OTMProcessSummary](summary)
