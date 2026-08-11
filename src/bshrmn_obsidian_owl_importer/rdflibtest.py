import os
from os.path import splitext
from urllib.parse import urlparse
from rdflib import Graph as RdfGraph, URIRef, BNode, Literal
from rdflib.namespace import RDF, RDFS, OWL, SKOS, DC, DCTERMS, split_uri
from dataclasses import dataclass, field
import queue
import logging
from logging.handlers import RotatingFileHandler

# Base path for links
BASE_PATH = "output"

# Directory where local ontos are stored
ONTO_DIRECTORY = "ontologies"

# Custom logger setup
logger = logging.getLogger(__name__)
file_handler = RotatingFileHandler(
    filename=os.path.abspath(os.path.join(BASE_PATH, "onto-to-md.log")),
    maxBytes=1_000_000,
    backupCount=5,
    encoding="utf-8"
)
log_format = logging.Formatter(
    fmt="%(asctime)s | %(levelname)s | %(name)s:%(filename)s:%(lineno)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ"
)
file_handler.setFormatter(log_format)
logger.addHandler(file_handler)
logger.propagate = False
logger.setLevel(logging.DEBUG)

# Namespaces to preload locally
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
ONTO_FILE_EXTENSIONS = (".owl", ".rdf", ".ttl", ".n3")

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
    URIRef("http://purl.obolibrary.org/obo/IAO_0000111"),
    SKOS.altLabel,
    URIRef("http://purl.obolibrary.org/obo/IAO_0000118"),
    # Additional properties (e.g. SKOS.hiddenLabel) could also be included
}

DESCRIPTION_PROPERTIES = {
    DCTERMS.abstract,
    RDFS.comment,
    SKOS.note,
    SKOS.definition,
    DC.description,
    DCTERMS.description,
    URIRef("http://purl.obolibrary.org/obo/IAO_0000115"),
    URIRef("http://purl.obolibrary.org/obo/IAO_0000119"),
    SKOS.historyNote,
    SKOS.scopeNote,
    SKOS.example,
    URIRef("http://purl.obolibrary.org/obo/IAO_0000112"),
    # Additional properties could also be included
}

# Some URIRef values should be left as raw links instead of aliased to another value
# Examples: ontologies, documentation, web pages, etc.
# Attempting to fetch them could result in long load times before falling back to the raw value
# Note: This is a rough list and should be expanded based on the use case
EXTERNAL_LINK_PROPERTIES = {
    RDFS.isDefinedBy,
    RDFS.seeAlso,
    OWL.versionIRI,
    DCTERMS.contributor,
    DCTERMS.creator,
    URIRef("http://purl.obolibrary.org/obo/IAO_0000412"),
    URIRef("http://purl.obolibrary.org/obo/IAO_0000117"),
    URIRef("http://purl.obolibrary.org/obo/IAO_0000119"),
    URIRef("http://purl.obolibrary.org/obo/IAO_0010000"),
    URIRef("http://purl.obolibrary.org/obo/IAO_0000233"),
    URIRef("http://www.geneontology.org/formats/oboInOwl#hasDbXref"),
    URIRef("http://www.geneontology.org/formats/oboInOwl#created_by"),
    URIRef("http://www.geneontology.org/formats/oboInOwl#inSubset"),
}

@dataclass
class OntoResource:
    type : str = ""
    resource : URIRef = None
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
    
    def title(self, title_priority_list : list[str]):
        for property in title_priority_list:
            if property in self.name_properties:
                return self.name_properties[property][0]
        
        _, local_name = split_uri(self.resource)
        return local_name

# NOTE: Do not reassign the following variables locally or as parameters
# Ontologies stored locally
local_ontos : dict[str, str] = {}
# Namespaces and their associated graphs
parsed_graphs : dict[str, RdfGraph]= {}
# Namespaces that could not be resolved
bad_namespaces : set[str] = set()
# Resources that could not be resolved
bad_resources : set[URIRef] = set()
# Base namespaces that have been retrieved already
retrieved_namespaces : set[str] = set()
# Resources that should be skipped instead of resolved
skippable_resources : set[URIRef] = set()
# Namespaces whose resources should be skipped instead of resolved
skippable_namespaces : set[URIRef] = set()
# Resources that should not have pages made for them
do_not_create_resources : set[URIRef] = set()
# List of graphs that have been changed and need to be saved locally, by namespace
namespaces_to_save : set[str] = set()
# Queue to hold resources that need to be processed
resource_queue = queue.SimpleQueue()
# Queue to hold external resources that need to be processed
external_resource_queue = queue.SimpleQueue()
# Resources that have been added to the queue
queued_resources = set()
# Resources that have already been processed
processed_resources = set()
# Resources that are only stubs in the local graph
stubbed_resources = set()

def _get_local_ontos(directory : str = ONTO_DIRECTORY, extensions : tuple[str] = ONTO_FILE_EXTENSIONS):
    return {splitext(file_name)[0]: file_name for file_name in os.listdir(directory) if file_name.endswith(extensions)}

def _clean_file_name(file_name : str):
    # NOTE: Not completely sold on this format
    # Retain some form of the ending character (http://edamontology.org/ vs http://edamontology.org#)
    # This also makes the file name not end with an _ or #
    if file_name[-1] == "/":
        file_name = file_name[:-1] + "_s"
    elif file_name[-1] == "#":
        file_name = file_name[:-1] + "_h"
    return file_name.replace("/", "_").replace(".", "-")

def _namespace_to_file_name(namespace : str):
    parsed_namespace = urlparse(namespace)
    onto_file_name = parsed_namespace.netloc + parsed_namespace.path
    # Add back the fragment identifier if present for consistency
    onto_file_name += "#" if namespace[-1] == "#" else ""
    return _clean_file_name(onto_file_name)

def _resource_to_file_path(resource : URIRef, base_path = "") -> str:
    # Strip the scheme and split into namespace and local name
    parsed_uri = urlparse(resource)
    namespace, local_name = split_uri(parsed_uri.geturl().replace(parsed_uri.scheme + "://", "", 1))

    # Local name cannot be "index" or "log" since they are reserved in OKF
    if local_name == "index":
        local_name = "index_term"
    elif local_name == "log":
        local_name = "log_term"

    if base_path:
        return f"{base_path}/{_clean_file_name(namespace)}/{_clean_file_name(local_name)}"
    else:
        return f"{_clean_file_name(namespace)}/{_clean_file_name(local_name)}"

def _serialize_graph(namespace : str):
    onto_file_name = _namespace_to_file_name(namespace)
    loc = os.path.abspath(os.path.join(ONTO_DIRECTORY, onto_file_name + ".rdf"))
    graph = parsed_graphs[namespace]
    graph.serialize(destination=loc, format="xml")

def prefetch_ontos(should_force : bool = True):
    """
    Prefetches ontologies and creates local copies.

    :param should_force: Flag for overwriting local versions.
    :type should_force: bool
    """
    local_ontos.update(_get_local_ontos(ONTO_DIRECTORY, ONTO_FILE_EXTENSIONS))
    
    for ns in PRELOAD_NAMESPACES:
        logger.info("Preloading namespace: %s", ns)
        
        graph = RdfGraph()

        onto_file_name = _namespace_to_file_name(ns)
        if should_force or onto_file_name not in local_ontos.keys():
            # Attempt to parse the URI
            try:
                # Try parsing based without explicit format
                graph.parse(ns)
            except:
                # Try again with explicitly XML
                try:
                    logger.info("Attempting to resolve foreign namespace as xml")
                    graph.parse(ns, format="xml")
                except:
                    logger.warning("Unable to resolve namespace: %s", ns)

            if len(graph) > 0:
                loc = os.path.abspath(os.path.join(ONTO_DIRECTORY, onto_file_name + ".rdf"))
                logger.info("Writing ontology to file %s", loc)
                graph.serialize(destination=loc, format="xml")
            else:
                logger.info("Ontology graph was empty after parsing")
        else:
            logger.info("Local onto found for namespace: %s", ns)

def _is_list_node(subject, g : RdfGraph) -> bool:
    return (subject, RDF.first, None) in g and (subject, RDF.rest, None) in g

def _parse_restriction(restriction : URIRef, g : RdfGraph):
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
        range = g.value(restriction, OWL.onClass) or g.value(restriction, OWL.onDataRange)
        return f"({_stringify_term(restricted_property, g)} has exactly {cardinality} {range})"
    elif (restriction, OWL.minQualifiedCardinality, None) in g:
        min_cardinality = g.value(restriction, OWL.minQualifiedCardinality)
        max_cardinality = g.value(restriction, OWL.maxQualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(restriction, OWL.onDataRange)

        if max_cardinality is not None:
            return f"({_stringify_term(restricted_property, g)} has between {min_cardinality} and {max_cardinality} {range})"
        else:
            return f"({_stringify_term(restricted_property, g)} has at least {min_cardinality} {range})"
    elif (restriction, OWL.maxQualifiedCardinality, None) in g:
        max_cardinality = g.value(restriction, OWL.maxQualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(restriction, OWL.onDataRange)
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
        return f"({_stringify_term(restricted_property, g)} has unknown restriction type)"

def _stringify_term(term, g : RdfGraph, list_joiner : str = " ", skip_property_chain : bool = False) -> str:
    logger.debug("Stringify: %s | Type: %s", term, type(term))

    # NOTE: May need onDatatype in the future: withRestrictions minExclusive minInclusive maxExclusive maxInclusive
    if isinstance(term, URIRef):
        if _is_resource_available(term, g):
            namespace, _ = split_uri(term)
            # Check if in passed graph first
            if (term, RDFS.label, None) in g:
                return f"[{_common_name(term, g)}]({_resource_to_file_path(term, BASE_PATH)}.md)"
            else:
                return f"[{_common_name(term, parsed_graphs[namespace])}]({_resource_to_file_path(term, BASE_PATH)}.md)"
        
        # Return URI as a backup
        return str(term)
    if isinstance(term, BNode):
        if (term, RDF.type, OWL.Restriction) in g:
            return _parse_restriction(term, g)
        elif (term, OWL.unionOf, None) in g:
            value = g.value(term, OWL.unionOf)
            return f"{_stringify_term(value, g, list_joiner=" or ")}"
        elif (term, OWL.intersectionOf, None) in g:
            value = g.value(term, OWL.intersectionOf)
            return f"{_stringify_term(value, g, list_joiner=" and ")}"
        elif (term, OWL.complementOf, None) in g:
            value = g.value(term, OWL.complementOf)
            return f"not {_stringify_term(value, g)}"
        elif (term, OWL.someValuesFrom, None) in g:
            value = g.value(term, OWL.someValuesFrom)
            return f"some values from {_stringify_term(value, g)}"
        elif (term, OWL.oneOf, None) in g:
            value = g.value(term, OWL.oneOf)
            return f"one of {_stringify_term(value, g, list_joiner=", ")}"
        elif (term, OWL.inverseOf, None) in g:
            value = g.value(term, OWL.inverseOf)
            return f"inverse of {_stringify_term(value, g)}"
        # This feels a little hacky, but seems to work
        elif not skip_property_chain and (None, OWL.propertyChainAxiom, term) in g:
            return f"{_stringify_term(term, g, list_joiner=" -> ", skip_property_chain=True)}"
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
            logger.warning("Current BNode is not a list node or a known collection type")
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

def _is_resource_available(resource : URIRef, default_graph : RdfGraph = None) -> bool:
    logger.info("Checking for resource %s", resource)

    # Check if we can access the subject's data
    if resource in skippable_resources:
        logger.info("Resource can be skipped")
        return False
    
    # Check if this resource previously failed to be loaded
    if resource in bad_resources:
        logger.info("Resource previously failed to load")
        return False
    
    # Split the URIRef into the namespace and resource name
    namespace, _ = split_uri(resource)
    logger.debug("Namespace is %s", namespace)

    if resource in skippable_namespaces:
        # Update skippable_resources for faster failing in future checks
        skippable_resources.add(resource)
        logger.info("Namespace can be skipped")
        return False

    # Check if namespace previously failed to be loaded
    if namespace in bad_namespaces:
        # Update bad_resources for faster failing in future checks
        bad_resources.add(resource)
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
            queued_resources.discard(resource)
            stubbed_resources.add(resource)

    # Check if namespace has been loaded
    if namespace in parsed_graphs:
        candidate_graph = parsed_graphs[namespace]

        # Check if resource and label are present in graph
        if (resource, RDFS.label, None) in candidate_graph:
            # Add resource to queue if it needs to be processed
            if resource not in queued_resources and resource not in processed_resources:
                external_resource_queue.put(resource)
                queued_resources.add(resource)
                logger.debug("Added resource to queue")
            logger.info("Resource found in parsed graphs")
            return True
    
    onto_file_name = _namespace_to_file_name(namespace)
    logger.debug("Looking for local ontology file %s", onto_file_name)

    # Check if namespace is available locally
    if onto_file_name in local_ontos.keys():
        candidate_graph = parsed_graphs[namespace] if namespace in parsed_graphs else RdfGraph()
        candidate_graph.parse(os.path.abspath(os.path.join(ONTO_DIRECTORY, local_ontos[onto_file_name])))

        if len(candidate_graph) > 0:
            # Add the local data to parsed graphs
            parsed_graphs[namespace] = candidate_graph

            # Check if resource and label are present in graph
            if (resource, RDFS.label, None) in candidate_graph:
                # Add resource to queue if it needs to be processed
                if resource not in queued_resources and resource not in processed_resources:
                    external_resource_queue.put(resource)
                    queued_resources.add(resource)
                    logger.debug("Added resource to queue")
                logger.info("Resource found in local ontology file")
                return True
    
    # Check if resource is available remotely
    candidate_graph = parsed_graphs[namespace] if namespace in parsed_graphs else RdfGraph()

    logger.debug("Attempting to parse foreign resource %s", resource)
    # Attempt to parse the URI
    try:
        # Try parsing based without explicit format
        candidate_graph.parse(resource)
    except:
        # Try again with explicitly XML
        try:
            logger.info("Attempting to resolve foreign resource as xml")
            candidate_graph.parse(resource, format="xml")
        except:
            logger.warning("Unable to resolve resource: %s", resource)

    if len(candidate_graph) > 0:
        # Add the remote data to parsed graphs
        parsed_graphs[namespace] = candidate_graph

        # Save info to serialize later
        namespaces_to_save.add(namespace)

        # Check if resource and label are present in graph
        if (resource, RDFS.label, None) in candidate_graph:
            # Add resource to queue if it needs to be processed
            if resource not in queued_resources and resource not in processed_resources:
                external_resource_queue.put(resource)
                queued_resources.add(resource)
                logger.debug("Added resource to queue")
            logger.info("Resource found at foreign location")
            return True

    # Before resolving the namespace, check if this was previously attempted
    if namespace in retrieved_namespaces:
        # This saves some time when the resulting graph would be large
        logger.info("Already retrieved namespace %s during this run", namespace)
        return False
    
    # Attempt to resolve only the namespace to check if the issue is just the resource
    try:
        logger.debug("Attempting to resolve just namespace %s", namespace)
        # Try parsing based without explicit format
        candidate_graph.parse(namespace)
    except:
        # Try again with explicitly XML
        try:
            logger.info("Attempting to resolve foreign namespace as xml")
            candidate_graph.parse(namespace, format="xml")
        except:
            logger.warning("Unable to resolve namespace: %s", namespace)

    if len(candidate_graph) > 0:
        # Add the remote data to parsed graphs
        parsed_graphs[namespace] = candidate_graph

        # Save info to serialize later
        namespaces_to_save.add(namespace)

        # Check one more time if resource and label are present in graph
        if (resource, RDFS.label, None) in candidate_graph:
            # Add resource to queue if it needs to be processed
            if resource not in queued_resources and resource not in processed_resources:
                external_resource_queue.put(resource)
                queued_resources.add(resource)
                logger.debug("Added resource to queue")
            logger.info("Resource found in foreign namespace")
            return True
        else:
            # There is an issue with the resource
            bad_resources.add(resource)
            logger.warning("Resource %s has been added to bad resources list", resource)
            return False
    
    # There is an issue with the namespace
    bad_namespaces.add(namespace)
    # Update bad_resources for faster failing in future checks
    bad_resources.add(resource)
    logger.warning("Unable to resolve resource and namespace for %s", resource)
    return False

def _resource_axiom_annotations(s, p, o, g : RdfGraph):
    axiom_anotations : dict[URIRef, list[str]] = {}

    # Find axiom nodes associated with (s, p, o) triple
    for axiom in g.subjects(OWL.annotatedSource, s):
        if (axiom, OWL.annotatedProperty, p) not in g:
            continue
        if (axiom, OWL.annotatedTarget, o) not in g:
            continue

        # Get annotations
        for predicate, object in g.predicate_objects(axiom):
            if predicate in (OWL.annotatedSource, OWL.annotatedProperty, OWL.annotatedTarget, RDF.type):
                continue

            if predicate in axiom_anotations:
                axiom_anotations[predicate].append(object)
            else:
                axiom_anotations[predicate] = [object]
    
    return axiom_anotations

def _is_not_deprecated(resource, g : RdfGraph) -> bool:
    # The value of owl:deprecated does not seem to be restricted to booleans, so check for presence
    return (resource, OWL.deprecated, None) not in g

def _common_name(resource : URIRef, g : RdfGraph) -> str:
    for alias in ALIAS_PROPERTIES:
        # Loop through potential aliases
        if (resource, alias, None) in g:
            results = g.objects(resource, alias)
            return str(next(results))
    
    # Fallback is the local name from the URIRef
    _, local_name = split_uri(resource)
    return local_name

def _resource_type(s, g : RdfGraph) -> str:
    for category in CLASS_TYPES:
        if (s, RDF.type, category) in g:
            return "Class"
    
    for category in INDIVIDUAL_TYPES:
        if (s, RDF.type, category) in g:
            return "Individual"
    
    for category in PROPERTY_TYPES:
        if (s, RDF.type, category) in g:
            return "Property"

def _resource_info(s : URIRef, g : RdfGraph) -> OntoResource:
    resource_info = OntoResource()
    resource_info.type = _resource_type(s, g)
    resource_info.resource = s

    for p, o in g.predicate_objects(s):
        if p in ALIAS_PROPERTIES:
            resource_info.update_names(p, o)
        elif p in DESCRIPTION_PROPERTIES:
            resource_info.update_descriptions(p, o)
        else:
            resource_info.update_others(p, o)
    
    return resource_info

def _resource_page(resource : OntoResource, g : RdfGraph):
    # Create a directory for the namespace if needed
    resource_path = _resource_to_file_path(resource.resource, BASE_PATH)
    namespace_path, _ = resource_path.rsplit('/', 1)
    os.makedirs(namespace_path, exist_ok=True)

    with open(f"{resource_path}.md", "w", encoding="utf-8") as file:
        # YAML frontmatter
        file.write("---\n")
        file.write(f"type: {resource.type}\n")
        file.write(f"title: {resource.title(ALIAS_PROPERTIES)}\n")
        file.write(f"resource: {resource.resource}\n")
        if resource.name_properties:
            # Ignore duplicates here
            seen_aliases = set()

            file.write(f"aliases:\n")
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
                    if pk not in EXTERNAL_LINK_PROPERTIES:
                        file.write(f"  - propertyValue: {_stringify_term(pv, g)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(resource.resource, pk, pv, g)
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(f"    - annotationKey: {_stringify_term(ak, g)}\n")
                            for av in avs:
                                if ak not in EXTERNAL_LINK_PROPERTIES:
                                    file.write(f"      - annotationValue: {_stringify_term(av, g)}\n")
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")

        # Description properties
        if resource.description_properties:
            file.write("# Description Properties\n")
            for pk, pvs in resource.description_properties.items():
                file.write(f"- propertyKey: {_stringify_term(pk, g)}\n")
                for pv in pvs:
                    if pk not in EXTERNAL_LINK_PROPERTIES:
                        file.write(f"  - propertyValue: {_stringify_term(pv, g)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(resource.resource, pk, pv, g)
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(f"    - annotationKey: {_stringify_term(ak, g)}\n")
                            for av in avs:
                                if ak not in EXTERNAL_LINK_PROPERTIES:
                                    file.write(f"      - annotationValue: {_stringify_term(av, g)}\n")
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")
        
        # Other properties
        if resource.other_properties:
            file.write("# Other Properties\n")
            for pk, pvs in resource.other_properties.items():
                file.write(f"- propertyKey: {_stringify_term(pk, g)}\n")
                for pv in pvs:
                    if pk not in EXTERNAL_LINK_PROPERTIES:
                        file.write(f"  - propertyValue: {_stringify_term(pv, g)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(resource.resource, pk, pv, g)
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(f"    - annotationKey: {_stringify_term(ak, g)}\n")
                            for av in avs:
                                if ak not in EXTERNAL_LINK_PROPERTIES:
                                    file.write(f"      - annotationValue: {_stringify_term(av, g)}\n")
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")

def main():
    logger.info("Script starting")
    1/0

    # Check what local ontologies are known
    local_ontos.update(_get_local_ontos(ONTO_DIRECTORY, ONTO_FILE_EXTENSIONS))

    g = RdfGraph()

    try:
        g.parse(os.path.abspath(os.path.join("input", "swo.owl")), format="xml")
        parsed_graphs["http://www.ebi.ac.uk/swo/"] = g # NOTE: no good way to determine this so must be passed in
        # print(f"Triples found: {len(g)}")
        # Make sure the graph is populated
        if len(g) == 0:
            logger.critical("No resources found in target")
            return
    except:
        logger.critical("Unable to parse primary target")
        return

    # Configurable
    skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0002575"))
    skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0001900"))
    skippable_resources.add(URIRef("http://edamontology.org#subset"))
    skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0001901"))
    skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0004050"))
    skippable_resources.add(URIRef("http://www.w3.org/2001/XMLSchema#string"))
    skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0004049"))
    skippable_resources.add(URIRef("http://www.geneontology.org/formats/oboInOwl#SubsetProperty"))
    skippable_resources.add(URIRef("http://www.w3.org/2001/XMLSchema#boolean"))
    skippable_resources.add(URIRef("http://www.geneontology.org/formats/oboInOwl#created_by"))
    skippable_resources.add(URIRef("http://edamontology.org#namespace"))
    skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0002579"))
    skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0040042"))
    skippable_resources.add(URIRef("http://www.geneontology.org/formats/oboInOwl#creation_date"))
    skippable_resources.add(URIRef("http://edamontology.org#def"))

    # Loop for all desired categories and add to queue for processing
    class_count = 0
    individual_count = 0
    property_count = 0

    for category in CLASS_TYPES:
        for s in g.subjects(RDF.type, category, unique=True):
            if isinstance(s, URIRef) and _is_not_deprecated(s, g):
                logger.debug("Adding %s (%s) to queue for processing", s, category)
                resource_queue.put(s)
                queued_resources.add(s)
                class_count += 1
    
    for category in INDIVIDUAL_TYPES:
        for s in g.subjects(RDF.type, category, unique=True):
            if isinstance(s, URIRef) and _is_not_deprecated(s, g):
                logger.debug("Adding %s (%s) to queue for processing", s, category)
                resource_queue.put(s)
                queued_resources.add(s)
                individual_count += 1
    
    for category in PROPERTY_TYPES:
        for s in g.subjects(RDF.type, category, unique=True):
            if isinstance(s, URIRef) and _is_not_deprecated(s, g):
                logger.debug("Adding %s (%s) to queue for processing", s, category)
                resource_queue.put(s)
                queued_resources.add(s)
                property_count += 1
    
    logger.debug("Total classes in primary target: %s", class_count)
    logger.debug("Total individuals in primary target: %s", individual_count)
    logger.debug("Total properties in primary target: %s", property_count)
    
    # Process all subjects in queue
    logger.info("Processing resources from primary target")
    try:
        while not resource_queue.empty():
            s = resource_queue.get()
            logger.debug("Processing: %s", s)

            # Do not create pages for these resources
            if s in do_not_create_resources or not _is_resource_available(s, g):
                logger.debug("Skipping page creation")
                # Update processed resources
                queued_resources.discard(s)
                processed_resources.add(s)
                continue

            # Also skip if the local version is a stub
            if s in stubbed_resources:
                logger.debug("This stub will be processed later")
                continue
            
            # Gather resource info
            onto_resource = _resource_info(s, g)
            _resource_page(onto_resource, g)
            
            # Update processed resources
            queued_resources.discard(s)
            processed_resources.add(s)
        
        logger.info("Processing discovered external resources")
        
        # Process any external resources that were used
        while not external_resource_queue.empty():
            s = external_resource_queue.get()
            logger.debug("Processing: %s", s)

            # Find the right graph to use
            external_namespace, _ = split_uri(s)
            external_graph = parsed_graphs[external_namespace]

            # Do not create pages for these resources
            if s in do_not_create_resources or not _is_resource_available(s, external_graph):
                logger.debug("Skipping page creation")
                # Update processed resources
                queued_resources.discard(s)
                processed_resources.add(s)
                
                continue

            # Gather resource info
            onto_resource = _resource_info(s, external_graph)
            _resource_page(onto_resource, external_graph)
            
            # Update processed resources
            queued_resources.discard(s)
            processed_resources.add(s)
    finally:
        # Save any new or updated graphs locally
        for namespace in namespaces_to_save:
            logger.info("Saving graph associated with namespace: %s", namespace)
            _serialize_graph(namespace)

        # TODO Print information useful for future runs
        print()
        print(f"Initial queue size was {class_count + individual_count + property_count} resources!")
        print(f"{len(processed_resources)} total resources were processed!")
        print("Graphs Used:")
        for parsed_graph in  parsed_graphs.keys():
            print(f"  {parsed_graph}")
        print("Bad Namespaces:")
        for bad_namespace in bad_namespaces:
            print(f" {bad_namespace}")
        print("Bad Resources:")
        for bad_resource in bad_resources:
                print(f" {bad_resource}")
        print("Stubbed Resources:")
        for stubbed_resource in stubbed_resources:
                print(f" {stubbed_resource}")
        # TODO this could be used for partial run recovery
        print(f"Processed resources: {list(map(str, processed_resources))}")
        if not resource_queue.empty():
            print("Unprocessed resources in main file:")
            while not resource_queue.empty():
                print(resource_queue.get())
        if not external_resource_queue.empty():
            print("Unprocessed external resources:")
            while not external_resource_queue.empty():
                print(external_resource_queue.get())

        # Create top-level index.md file
        # Sort namespaces alphabetically
        # NOTE: This will not always produce an intuitive result (e.g. the expected name could appear later in the URI)
        sorted_namespaces = sorted(parsed_graphs.keys())

        base_index_path = f"{BASE_PATH}/index.md" if BASE_PATH else "index.md"
        with open(base_index_path, "w", encoding="utf-8") as base_index_file:
            base_index_file.write("# Namespaces\n")

            for namespace in sorted_namespaces:
                if BASE_PATH:
                    base_index_file.write(f"- [{namespace}]({BASE_PATH}/{_namespace_to_file_name(namespace)}/)\n")
                else:
                    base_index_file.write(f"- [{namespace}]({_namespace_to_file_name(namespace)}/)\n")

        # Create namespace-level index.md files
        for directory_name in os.listdir(BASE_PATH):
            if directory_name == "index.md" or directory_name == "log.md":
                continue
    
            onto_directory_path = f"{BASE_PATH + "/" if BASE_PATH else ""}{directory_name}"
            with open(f"{onto_directory_path}/index.md", "w", encoding="utf-8") as namespace_index_file:
                namespace_index_file.write("# Resources\n")
    
                for file_name in os.listdir(onto_directory_path):
                        if file_name == "index.md" or directory_name == "log.md":
                            continue
    
                        resource_title = ""
                        with open(f"{onto_directory_path}/{file_name}", "r", encoding="utf-8") as resource_file:
                            for i, line in enumerate(resource_file):
                                # NOTE: Magic number, but that part of the frontmatter should be consistent
                                if i == 2:
                                    # Grab everything after "title: "
                                    resource_title = line[7:].strip()
    
                        if resource_title:
                            namespace_index_file.write(f"- [{resource_title}]({onto_directory_path}/{file_name})\n")
    
    logger.info("Script completed")
    return

if __name__ == "__main__":
    main()