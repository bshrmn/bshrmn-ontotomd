import os
from os.path import splitext
from urllib.parse import urlparse
from rdflib import Graph as RdfGraph, URIRef, BNode, Literal
from rdflib.namespace import RDF, RDFS, OWL, SKOS, DC, DCTERMS, Namespace, split_uri
from dataclasses import dataclass, field
import queue

# Base path for links
BASE_PATH = "output"

# Directory where local ontos are stored
ONTO_DIRECTORY = "ontologies"

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

# TODO Might want these to be extendable in a config file for onto-specific cases
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
# TODO CONFIGURABLE
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
# TODO CONFIGURABLE
# Resources that should always be skipped instead of resolved
skippable_resources : set[URIRef] = set()
# TODO CONFIGURABLE
# Resources that should not have pages made for them
do_not_create_resources : set[URIRef] = set()
# List of graphs that have been changed and need to be saved locally, by namespace
namespaces_to_save : set[str] = set()
# TODO Remove
other_types = set()
# Queue to hold resources that need to be processed
resource_queue = queue.SimpleQueue()
# Queue to hold external resources that need to be processed
external_resource_queue = queue.SimpleQueue()
# Resources that have been added to the queue
queued_resources = set()
# Resources that have already been processed
processed_resources = set()
# TODO REMOVE
file_names : set[str] = set()

def _get_local_ontos(directory : str = ONTO_DIRECTORY, extensions : tuple[str] = ONTO_FILE_EXTENSIONS):
    return {splitext(file_name)[0]: file_name for file_name in os.listdir(directory) if file_name.endswith(extensions)}

def _clean_file_name(file_name : str):
    # TODO immplement better
    # Retain some form of the ending character (http://edamontology.org/ vs http://edamontology.org#)
    # This also makes the file name not end with an _ or #
    if file_name[-1] == "/":
        file_name = file_name[:-1] + "_s"
    elif file_name[-1] == "#":
        file_name = file_name[:-1] + "_h"
    return file_name.replace("/", "_").replace(".", "-")

def _namespace_to_file_name(namespace : str):
    parsed_namespace = urlparse(namespace)
    print(f"Converting: {namespace} -> {parsed_namespace}") # TODO REMOVE
    onto_file_name = parsed_namespace.netloc + parsed_namespace.path
    return _clean_file_name(onto_file_name)

def _resource_to_file_path(resource : URIRef, base_path = "") -> str:
    # Strip the scheme and split into namespace and local name
    parsed_uri = urlparse(resource)
    namespace, local_name = split_uri(parsed_uri.geturl().replace(parsed_uri.scheme + "://", "", 1))

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
    print("Prefetching ontologies")

    local_ontos.update(_get_local_ontos(ONTO_DIRECTORY, ONTO_FILE_EXTENSIONS))
    
    for ns in PRELOAD_NAMESPACES:
        # TODO log
        print(f"Preloading namespace: {ns}")

        try: # TODO Check if this is still needed
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
                        print("Attempting to resolve foreign resource as xml.")
                        graph.parse(ns, format="xml")
                    except:
                        # TODO log
                        print(f"Unable to resolve namespace: {ns}")

                if len(graph) > 0:
                    loc = os.path.abspath(os.path.join(ONTO_DIRECTORY, onto_file_name + ".rdf"))
                    print(loc)
                    graph.serialize(destination=loc, format="xml")
                else:
                    # TODO log
                    print(f"No results found for namespace: {ns}")
            else:
                print(f"Local onto found for namespace: {ns}")
        except:
            # TODO log
            print(f"Unable to fetch namespace: {ns}")
            continue
    
    print("Finished prefetching ontologies")

def _is_list_node(g : RdfGraph, subject) -> bool:
    return (subject, RDF.first, None) in g and (subject, RDF.rest, None) in g

def _parse_restriction(restriction : URIRef, g : RdfGraph):
    # Expect to have an onProperty relationship
    restricted_property = g.value(restriction, OWL.onProperty)

    # Possible restriction types checked below
    if (restriction, OWL.hasSelf, None) in g:
        # The value of owl:hasSelf does not seem to be restricted to booleans, so check for presence
        return f"({_stringify_term(g, restricted_property)} has self as a value)"
    elif (restriction, OWL.hasValue, None) in g:
        value = g.value(restriction, OWL.hasValue)
        return f"({_stringify_term(g, restricted_property)} has value {_stringify_term(g, value)})"
    # Unqualified cardinality
    elif (restriction, OWL.cardinality, None) in g:
        cardinality = g.value(restriction, OWL.cardinality)
        return f"({_stringify_term(g, restricted_property)} has cardinality of exactly {cardinality})"
    elif (restriction, OWL.minCardinality, None) in g:
        min_cardinality = g.value(restriction, OWL.minCardinality)
        max_cardinality = g.value(restriction, OWL.maxCardinality)

        if max_cardinality is not None:
            return f"({_stringify_term(g, restricted_property)} has cardinality between {min_cardinality} and {max_cardinality})"
        else:
            return f"({_stringify_term(g, restricted_property)} has cardinality of at least {min_cardinality})"
    elif (restriction, OWL.maxCardinality, None) in g:
        max_cardinality = g.value(restriction, OWL.maxCardinality)
        return f"({_stringify_term(g, restricted_property)} has cardinality of at most {max_cardinality})"
    # Qualified cardinality
    elif (restriction, OWL.qualifiedCardinality, None) in g:
        cardinality = g.value(restriction, OWL.qualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(restriction, OWL.onDataRange)
        return f"({_stringify_term(g, restricted_property)} has exactly {cardinality} {range})"
    elif (restriction, OWL.minQualifiedCardinality, None) in g:
        min_cardinality = g.value(restriction, OWL.minQualifiedCardinality)
        max_cardinality = g.value(restriction, OWL.maxQualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(restriction, OWL.onDataRange)

        if max_cardinality is not None:
            return f"({_stringify_term(g, restricted_property)} has between {min_cardinality} and {max_cardinality} {range})"
        else:
            return f"({_stringify_term(g, restricted_property)} has at least {min_cardinality} {range})"
    elif (restriction, OWL.maxQualifiedCardinality, None) in g:
        max_cardinality = g.value(restriction, OWL.maxQualifiedCardinality)
        range = g.value(restriction, OWL.onClass) or g.value(restriction, OWL.onDataRange)
        return f"({_stringify_term(g, restricted_property)} has at most {max_cardinality} {range})"
    elif (restriction, OWL.hasValue, None) in g:
        value = g.value(restriction, OWL.hasValue)
        return f"({_stringify_term(g, restricted_property)} has value {_stringify_term(g, value)})"
    elif (restriction, OWL.someValuesFrom, None) in g:
        range = g.value(restriction, OWL.someValuesFrom)
        return f"({_stringify_term(g, restricted_property)} has some values from {_stringify_term(g, range)})"
    elif (restriction, OWL.allValuesFrom, None) in g:
        range = g.value(restriction, OWL.allValuesFrom)
        return f"({_stringify_term(g, restricted_property)} has only values from {_stringify_term(g, range)})"
    else:
        # TODO log
        print(f"Unknown restriction type for {restriction.n3(g.namespace_manager)}")
        return f"({_stringify_term(g, restricted_property)} has unknown restriction type)"


def _stringify_term(g : RdfGraph, term, list_joiner : str = " ", skip_property_chain : bool = False) -> str:
    print(f"Stringify: {term} | Type: {type(term)}") # TODO REMOVE
    if isinstance(term, URIRef):
        if _is_resource_available(term, g):
            namespace, _ = split_uri(term)
            # Check if in passed graph first
            if (term, RDFS.label, None) in g:
                return f"[{_common_name(g, term)}]({_resource_to_file_path(term, BASE_PATH)}.md)"
            else:
                return f"[{_common_name(parsed_graphs[namespace], term)}]({_resource_to_file_path(term, BASE_PATH)}.md)"
        
        # Return URI as a backup
        return str(term)
    if isinstance(term, BNode):
        # OWL collections to watch out for
        # TODO class, individual, property
        # TODO obsolete/deprecated
        # TODO inverseOf
        # TODO equivalentClass
        # TODO onDatatype -> withRestrictions minExclusive minInclusive maxExclusive maxInclusive
        # TODO property chains
        # TODO seeAlso
        if (term, RDF.type, OWL.Restriction) in g:
            return _parse_restriction(term, g)
        elif (term, OWL.unionOf, None) in g:
            value = g.value(term, OWL.unionOf)
            return f"{_stringify_term(g, value, list_joiner=" or ")}"
        elif (term, OWL.intersectionOf, None) in g:
            value = g.value(term, OWL.intersectionOf)
            return f"{_stringify_term(g, value, list_joiner=" and ")}"
        elif (term, OWL.complementOf, None) in g:
            value = g.value(term, OWL.complementOf)
            return f"not {_stringify_term(g, value)}"
        elif (term, OWL.someValuesFrom, None) in g:
            value = g.value(term, OWL.someValuesFrom)
            return f"some values from {_stringify_term(g, value)}"
        elif (term, OWL.oneOf, None) in g:
            value = g.value(term, OWL.oneOf)
            return f"one of {_stringify_term(g, value, list_joiner=", ")}"
        elif (term, OWL.inverseOf, None) in g:
            value = g.value(term, OWL.inverseOf)
            return f"inverse of {_stringify_term(g, value)}"
        elif not skip_property_chain and (None, OWL.propertyChainAxiom, term) in g: # TODO Not sure if I like this
            return f"{_stringify_term(g, term, list_joiner=" -> ", skip_property_chain=True)}"
        # General list check
        elif _is_list_node(g, term):
            list_items = []
            current = term
            while current != RDF.nil:
                first = g.value(current, RDF.first)
                list_items.append(_stringify_term(g, first))
                current = g.value(current, RDF.rest)
            return f"({list_joiner.join(list_items)})"
        else:
            # TODO Remove once this is confirmed to happen
            print("NOTE: This BNode is not a list node or a known collection type!")
            for p, o in g.predicate_objects(term):
                print(f"  p:{p.n3(g.namespace_manager)} | o:{o.n3(g.namespace_manager)} {type(o)}")
            1/0 # TODO Remove
    if isinstance(term, Literal):
        # TODO maybe add language logic here?
        return str(term)
    
    # TODO Remove
    other_types.add(type(term))
    return str(term)

def _is_resource_available(resource, default_graph : RdfGraph = None) -> bool:
    print(f"Checking for: {resource}") # TODO REMOVE
    # TODO Maybe move this out of here so that it's only URIRefs
    # Check what type of resource it is
    if not isinstance(resource, URIRef):
        return True

    # Check if we can access the subject's data
    if resource in skippable_resources:
        print("Skipping this term.")
        return False
    
    # Check if this resource previously failed to be loaded
    if resource in bad_resources:
        return False
    
    # If a default graph is provided, prioritize that version of the resource
    if default_graph:
        # Check if resource and label are present in graph
        if (resource, RDFS.label, None) in default_graph:
            print("This is in the default graph.") # TODO REMOVE
            return True
    
    # Split the URIRef into the namespace and resource name
    namespace, _ = split_uri(resource)
    print(f"Namespace: {namespace}") # TODO REMOVE

    # Check if namespace previously failed to be loaded
    if namespace in bad_namespaces:
        return False

    # Check if namespace has been loaded
    if namespace in parsed_graphs:
        print("Namespace is in the parsed graphs.") # TODO REMOVE
        candidate_graph = parsed_graphs[namespace]

        # Check if resource and label are present in graph
        if (resource, RDFS.label, None) in candidate_graph:
            # Add resource to queue if it needs to be processed
            if resource not in queued_resources and resource not in processed_resources:
                external_resource_queue.put(resource)
                queued_resources.add(resource)
            return True
    
    onto_file_name = _namespace_to_file_name(namespace)
    print(f"Onto file name is: {onto_file_name}")

    # Check if namespace is available locally
    if onto_file_name in local_ontos.keys():
        # TODO revise
        candidate_graph = parsed_graphs[namespace] if namespace in parsed_graphs else RdfGraph()
        # TODO Check that this is pulling the right file
        print(os.path.abspath(os.path.join(ONTO_DIRECTORY, local_ontos[onto_file_name]))) # TODO REMOVE
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
                return True
    
    # Check if resource is available remotely
    candidate_graph = parsed_graphs[namespace] if namespace in parsed_graphs else RdfGraph()

    print(f"Attempt to parse foreign: {resource} | Type: {type(resource)}")
    # Attempt to parse the URI
    try:
        # Try parsing based without explicit format
        candidate_graph.parse(resource)
    except:
        # TODO Consider refining and adding to other parse calls such as prefetch
        # Try again with explicitly XML
        try:
            print("Attempting to resolve foreign resource as xml.")
            candidate_graph.parse(resource, format="xml")
        except:
            # TODO log
            print(f"Unable to parse resource: {resource}")

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
            return True

    # Before resolving the namespace, check if this was previously attempted
    if namespace in retrieved_namespaces:
        # This saves some time when the resulting graph would be large
        print(f"Namespace ({namespace}) was already retrieved during this run.")
        return False
    
    # Attempt to resolve only the namespace to check if the issue is just the resource
    try:
        print(f"Attempting to resolve just namespace: {namespace}")
        # Try parsing based without explicit format
        candidate_graph.parse(namespace)
    except:
        # TODO Consider refining and adding to other parse calls such as prefetch
        # Try again with explicitly XML
        try:
            print("Attempting to resolve just namespace as xml.")
            candidate_graph.parse(namespace, format="xml")
        except:
            # TODO log
            print(f"Unable to parse namespace: {namespace}")

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
            return True
        else:
            # There is an issue with the resource
            bad_resources.add(resource)

            return False
    
    # There is an issue with the namespace
    bad_namespaces.add(namespace)
    # TODO Logging
    print(f"Unable to resolve resource and namespace for: {str(resource)}")
    return False

def _print_axiom_for_triple(g, s, p, o):
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
            print(f"  [axiom-annotation] {_stringify_term(g, predicate)}  {_stringify_term(g, object)}") # TODO implement

def _resource_axiom_annotations(g : RdfGraph, s, p, o):
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

# def _print_subject(s, g):
#     # Will want to make a map of subjects so that multiple listings can be grouped
#     for s, p, o in g.triples((s, None, None)):
#         print(f"s:{_stringify_term(g, s)} | p:{_stringify_term(g, p)} | o:{_stringify_term(g, o)}")
#         _print_axiom_for_triple(g, s, p, o)

def _print_subject(s, g, indent=0):
    for s, p, o in g.triples((s, None, None)):
        print(f"{'-'*indent + '> '}s:{s} | p:{p} | o:{o} - {type(o)}")
        if isinstance(o, BNode):
            _print_subject(o, g, indent + 1)
            # TODO WRITE XML COLLECTION PARSER!

def _is_not_deprecated(g : RdfGraph, resource) -> bool:
    # The value of owl:deprecated does not seem to be restricted to booleans, so check for presence
    return (resource, OWL.deprecated, None) not in g

def _common_name(g : RdfGraph, resource : URIRef) -> str:
    for alias in ALIAS_PROPERTIES:
        # Loop through potential aliases
        if (resource, alias, None) in g:
            results = g.objects(resource, alias)
            return str(next(results))
    
    # Fallback is the local name from the URIRef
    _, local_name = split_uri(resource)
    return local_name

def _resource_type(g : RdfGraph, s) -> str:
    for category in CLASS_TYPES:
        if (s, RDF.type, category) in g:
            return "Class"
    
    for category in INDIVIDUAL_TYPES:
        if (s, RDF.type, category) in g:
            return "Individual"
    
    for category in PROPERTY_TYPES:
        if (s, RDF.type, category) in g:
            return "Property"

def _resource_info(g : RdfGraph, s : URIRef) -> OntoResource:
    resource_info = OntoResource()
    resource_info.type = _resource_type(g, s)
    resource_info.resource = s

    for p, o in g.predicate_objects(s):
        if p in ALIAS_PROPERTIES:
            resource_info.update_names(p, o)
        elif p in DESCRIPTION_PROPERTIES:
            resource_info.update_descriptions(p, o)
        else:
            resource_info.update_others(p, o)
    
    return resource_info

def _resource_page(g : RdfGraph, resource : OntoResource):
    #TODO REMOVE
    file_names.add(f"{_resource_to_file_path(resource.resource, BASE_PATH)}.md")

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
        # TODO aliases
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
                file.write(f"- propertyKey: {_stringify_term(g, pk)}\n")
                for pv in pvs:
                    if pk not in EXTERNAL_LINK_PROPERTIES:
                        file.write(f"  - propertyValue: {_stringify_term(g, pv)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(g, resource.resource, pk, pv)
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(f"    - annotationKey: {_stringify_term(g, ak)}\n")
                            for av in avs:
                                if ak not in EXTERNAL_LINK_PROPERTIES:
                                    file.write(f"      - annotationValue: {_stringify_term(g, av)}\n")
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")

        # Description properties
        if resource.description_properties:
            file.write("# Description Properties\n")
            for pk, pvs in resource.description_properties.items():
                file.write(f"- propertyKey: {_stringify_term(g, pk)}\n")
                for pv in pvs:
                    if pk not in EXTERNAL_LINK_PROPERTIES:
                        file.write(f"  - propertyValue: {_stringify_term(g, pv)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(g, resource.resource, pk, pv)
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(f"    - annotationKey: {_stringify_term(g, ak)}\n")
                            for av in avs:
                                if ak not in EXTERNAL_LINK_PROPERTIES:
                                    file.write(f"      - annotationValue: {_stringify_term(g, av)}\n")
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")
        
        # Other properties
        if resource.other_properties:
            file.write("# Other Properties\n")
            for pk, pvs in resource.other_properties.items():
                file.write(f"- propertyKey: {_stringify_term(g, pk)}\n")
                for pv in pvs:
                    if pk not in EXTERNAL_LINK_PROPERTIES:
                        file.write(f"  - propertyValue: {_stringify_term(g, pv)}\n")
                    else:
                        file.write(f"  - propertyValue: {str(pv)}\n")

                    # Include any annotations if present
                    annotations = _resource_axiom_annotations(g, resource.resource, pk, pv)
                    if annotations:
                        for ak, avs in annotations.items():
                            file.write(f"    - annotationKey: {_stringify_term(g, ak)}\n")
                            for av in avs:
                                if ak not in EXTERNAL_LINK_PROPERTIES:
                                    file.write(f"      - annotationValue: {_stringify_term(g, av)}\n")
                                else:
                                    file.write(f"      - annotationValue: {str(av)}\n")

def main():
    # Check what local ontologies are known
    local_ontos.update(_get_local_ontos(ONTO_DIRECTORY, ONTO_FILE_EXTENSIONS))

    g = RdfGraph()
    # TODO Wrap in try block
    g.parse(os.path.abspath(os.path.join("input", "swo.owl")), format="xml")
    parsed_graphs["http://www.ebi.ac.uk/swo/"] = g # TODO no good way to determine this so must be passed in
    print(f"Triples found: {len(g)}")
    # Make sure the graph is populated
    if len(g) == 0:
        # TODO log
        print(f"No resources found in target")
        return # TODO Implement
    print()

    # TODO REMOVE
    # test = URIRef("http://purl.obolibrary.org/obo/IAO_0000119")
    # test_info = _resource_info(g, test)
    # print(test_info)
    # _resource_page(g, test_info)
    # 1/0

    # Specified namespace aliases for testing
    # SWO = Namespace("http://www.ebi.ac.uk/swo/license/")
    # g.bind("swo", SWO)

    # TODO REMOVE and add to configuration
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
            if isinstance(s, URIRef) and _is_not_deprecated(g, s):
                print(f"Adding {_common_name(g, s)} ({category}) to queue for processing...")
                # _print_subject(s, g)
                # onto_resource = _resource_info(g, s)
                # _resource_page(g, onto_resource)
                resource_queue.put(s)
                queued_resources.add(s)
                class_count += 1
    
    for category in INDIVIDUAL_TYPES:
        for s in g.subjects(RDF.type, category, unique=True):
            if isinstance(s, URIRef) and _is_not_deprecated(g, s):
                print(f"Adding {_common_name(g, s)} ({category}) to queue for processing...")
                # _print_subject(s, g)
                # onto_resource = _resource_info(g, s)
                # _resource_page(g, onto_resource)
                resource_queue.put(s)
                queued_resources.add(s)
                individual_count += 1
    
    for category in PROPERTY_TYPES:
        for s in g.subjects(RDF.type, category, unique=True):
            if isinstance(s, URIRef) and _is_not_deprecated(g, s):
                print(f"Adding {_common_name(g, s)} ({category}) to queue for processing...")
                # _print_subject(s, g)
                # onto_resource = _resource_info(g, s)
                # _resource_page(g, onto_resource)
                resource_queue.put(s)
                queued_resources.add(s)
                property_count += 1
    
    print(f"Total Classes: {class_count} | Total Individuals: {individual_count} | Total Properties: {property_count}")
    print()
    print(f"Initial Queue Size: {resource_queue.qsize()}")
    
    # Process all subjects in queue
    try:
        while not resource_queue.empty():
            s = resource_queue.get()
            # TODO REMOVE
            print(f"Processing: {s}")

            # Do not create pages for these resources
            if s in do_not_create_resources:
                continue
            
            # Gather resource info
            onto_resource = _resource_info(g, s)
            _resource_page(g, onto_resource)
            
            # Update processed resources
            queued_resources.discard(s)
            processed_resources.add(s)
        
        print("Processing discovered external resources.") # TODO REMOVE
        
        # Process any external resources that were used
        while not external_resource_queue.empty():
            s = external_resource_queue.get()
            # TODO REMOVE
            print(f"Processing: {s}")

            # Do not create pages for these resources
            if s in do_not_create_resources:
                continue
            
            # Find the right graph to use
            external_namespace, _ = split_uri(s)
            external_graph = parsed_graphs[external_namespace]

            # Gather resource info
            onto_resource = _resource_info(external_graph, s)
            _resource_page(external_graph, onto_resource)
            
            # Update processed resources
            queued_resources.discard(s)
            processed_resources.add(s)
    finally:
        # Save any new or updated graphs locally
        for namespace in namespaces_to_save:
            # TODO log
            print(f"Saving graph associated with namespace: {namespace}")
            _serialize_graph(namespace)
    
    print()
    print("Done processing queue!")
    print(f"Initial queue size was {class_count + individual_count + property_count} resources!")
    print(f"{len(processed_resources)} total resources were processed!")
    # TODO this could be used for partial run recovery
    print(f"Processed resources: {list(map(str, processed_resources))}")
    print("Graphs Used:")
    for parsed_graph in  parsed_graphs.keys():
        print(f"  {parsed_graph}")
    print("Bad Namespaces:")
    for bad_namespace in bad_namespaces:
        print(f" {bad_namespace}")
    print("Bad Resources:")
    for bad_resource in bad_resources:
            print(f" {bad_resource}")
    print(f"File Names: {file_names}")
    
    # TODO log
    print()
    print("Script complete!")
    return

    # TODO for testing
    # test = URIRef("http://www.ebi.ac.uk/efo/obsoleted_in_version")
    # test_info = _resource_info(g, test)
    # print(test_info)
    # print(other_types)
    # _resource_page(g, test_info)
    # # TODO START REMOVE
    # print(parsed_graphs)

    # # Save any new or updated graphs locally
    # for namespace in namespaces_to_save:
    #     # TODO log
    #     print(f"Saving graph associated with namespace: {namespace}")
    #     _serialize_graph(namespace)
    # # TODO END REMOVE
    1/0

    for s in g.subjects(unique=True):
        print(f"Adding {s.n3(g.namespace_manager)} to queue for processing...")
        resource_queue.put(s)

    print()
    print(f"Initial Queue Size: {resource_queue.qsize()}")

    # Process all subjects in queue
    while not resource_queue.empty():
        s = resource_queue.get()
        print(f"Subject: {s.n3(g.namespace_manager)}")

        # TODO see how literals with lang or datatype get handled

        # Check if we can access the subject's data
        resource_available = _is_resource_available(s)

        if isinstance(s, URIRef):
            prefix, namespace, name = g.namespace_manager.compute_qname(s)

            parsed_namespace = urlparse(namespace)
            # TODO: May also want to convert . to _
            onto_file_name = parsed_namespace.netloc + parsed_namespace.path
            onto_file_name = onto_file_name.strip("/#").replace("/", "_").replace(".", "-")
            onto_file_path = os.path.join(ONTO_DIRECTORY, onto_file_name)
            print(f"---> File: {onto_file_path}")

            print(f"--> PX: {prefix} | NS: {namespace} | N: {name}")
            # This looks like it could be a way to see if the subject represents the onto itself
            print(f"--> Test? {s == namespace}")
            if name:
                print(f"--> QName: {name}")
            print
        # for label in g.objects(s, RDFS.label):
        #     print(f"--> Label: {label}")
        # for comment in g.objects(s, RDFS.comment):
        #     print(f"--> Comment: {comment}")

        for p, o in g.predicate_objects(s, unique=True):
            print(f"--> Predicate: {p.n3(g.namespace_manager)} | Object: {o.n3(g.namespace_manager)} {type(o)}")
    
    print()
    print("Done processing queue!")
    print(parsed_graphs)

    # Save any new or updated graphs locally
    for namespace in namespaces_to_save:
        # TODO log
        print(f"Saving graph associated with namespace: {namespace}")
        _serialize_graph(namespace)
    
    # TODO log
    print("Script complete!")

if __name__ == "__main__":
    main()
    
    # local_ontos = _get_local_ontos(ONTO_DIRECTORY, ONTO_FILE_EXTENSIONS)
    # print(local_ontos)
    # print([_namespace_to_file_name(ns) for ns in PRELOAD_NAMESPACES])
    
    # prefetch_ontos(should_force=False)



### EXTRA STUFF ###
# What namespaces do we know of?
# print([n for n in g.namespace_manager.namespaces()])

# parsed_graphs["http://purl.org/dc/dcam/"] = g

# Try binding some namespaces
# OBO = Namespace("http://purl.obolibrary.org/obo/")
# IAO = Namespace("http://purl.obolibrary.org/obo/IAO_")
# BFO = Namespace("http://purl.obolibrary.org/obo/BFO_")

# g.bind("obo", OBO)
# g.bind("iao", IAO)
# g.bind("bfo", BFO)

# obo_test1 = URIRef("http://purl.obolibrary.org/obo/valid_for_go_ontology")
# obo_test2 = URIRef("http://purl.obolibrary.org/obo/OMO_0002000")
# obo_test3 = URIRef("http://purl.obolibrary.org/obo/uberon/core#efo_slim")
# iao_test = URIRef("http://purl.obolibrary.org/obo/IAO_0000111")
# bfo_test = URIRef("http://purl.obolibrary.org/obo/BFO_0000179")

# # Namespace bindings above work as expected
# # Approach should probably just be to add to a single OBO graph (besides the uberon/core, etc. ones)

# print(obo_test1.n3(g.namespace_manager))
# print(obo_test2.n3(g.namespace_manager))
# print(obo_test3.n3(g.namespace_manager))
# print(iao_test.n3(g.namespace_manager))
# print(bfo_test.n3(g.namespace_manager))

# Can print triples directly from graph
# for s, p, o in g:
#     print(f"{s.n3(g.namespace_manager)} : {p.n3(g.namespace_manager)} : {o.n3(g.namespace_manager)}")