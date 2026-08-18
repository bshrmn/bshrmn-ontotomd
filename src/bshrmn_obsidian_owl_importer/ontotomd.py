import os
from pathlib import Path
from os.path import splitext
from urllib.parse import urlparse
from rdflib import Graph as RdfGraph, URIRef, BNode, Literal
from rdflib.namespace import RDF, RDFS, OWL, SKOS, DC, DCTERMS, split_uri
from dataclasses import dataclass, field
import queue
import logging
from logging.handlers import RotatingFileHandler
from bshrmn_obsidian_owl_importer import LoggingParamsConfig, GlobalParamsConfig, PreloadConfig
from rich.progress import track

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
ONTO_FILE_EXTENSIONS = (".owl", ".rdf", ".ttl", ".n3")

# NOTE: Do not reassign the following variables locally or as parameters
# Ontologies stored locally
local_ontos : dict[str, str] = {}

def _initialize_logger(config : LoggingParamsConfig):
    file_handler = RotatingFileHandler(
        filename=Path(config.logging_file).resolve(),
        maxBytes=config.max_file_size,
        backupCount=config.backup_count,
        encoding="utf-8"
    )
    log_format = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s:%(filename)s:%(lineno)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ"
    )
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    logger.propagate = False
    logger.setLevel(config.logging_level.value)

def _get_local_ontos(directory : str, extensions : tuple[str] = ONTO_FILE_EXTENSIONS):
    return {splitext(file_name)[0]: file_name for file_name in os.listdir(directory) if file_name.endswith(extensions)}

def _clean_file_name(file_name : str):
    # NOTE: Not completely sold on this format
    # Retain some form of the ending character (http://example.com/ vs http://example.com#)
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

def preload_ontos(global_params : GlobalParamsConfig, preload : PreloadConfig):
    _initialize_logger(global_params.logging_params)
    logger.info("Preload script starting")

    total_preloads = 0

    local_ontos.update(_get_local_ontos(global_params.ontologies_directory, ONTO_FILE_EXTENSIONS))

    # Merge the default preload namespaces with any additional targets
    preload_set = set(PRELOAD_NAMESPACES + (preload.targets if preload.targets is not None else []))
    for ns in track(preload_set, description="Preloading namespaces..."):
        logger.info("Preloading namespace: %s", ns)
        
        graph = RdfGraph()

        onto_file_name = _namespace_to_file_name(ns)
        if preload.overwrite_local_files or onto_file_name not in local_ontos.keys():
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
                loc = os.path.abspath(os.path.join(global_params.ontologies_directory, onto_file_name + ".rdf"))
                logger.info("Writing ontology to file %s", loc)
                graph.serialize(destination=loc, format="xml")
                total_preloads += 1
            else:
                logger.info("Ontology graph was empty after parsing")
        else:
            logger.info("Local onto found for namespace: %s", ns)

    logger.info(f"Script finished with {total_preloads} namespaces preloaded")
    return total_preloads

def main():
    # Check what local ontologies are known
    # local_ontos.update(_get_local_ontos(ONTO_DIRECTORY, ONTO_FILE_EXTENSIONS))

    # g = RdfGraph()

    # try:
    #     g.parse(os.path.abspath(os.path.join("input", "swo.owl")), format="xml")
    #     parsed_graphs["http://www.ebi.ac.uk/swo/"] = g # NOTE: no good way to determine this so must be passed in
    #     # print(f"Triples found: {len(g)}")
    #     # Make sure the graph is populated
    #     if len(g) == 0:
    #         logger.critical("No resources found in target")
    #         return
    # except:
    #     logger.critical("Unable to parse primary target")
    #     return

    # # Configurable
    # skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0002575"))
    # skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0001900"))
    # skippable_resources.add(URIRef("http://edamontology.org#subset"))
    # skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0001901"))
    # skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0004050"))
    # skippable_resources.add(URIRef("http://www.w3.org/2001/XMLSchema#string"))
    # skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0004049"))
    # skippable_resources.add(URIRef("http://www.geneontology.org/formats/oboInOwl#SubsetProperty"))
    # skippable_resources.add(URIRef("http://www.w3.org/2001/XMLSchema#boolean"))
    # skippable_resources.add(URIRef("http://www.geneontology.org/formats/oboInOwl#created_by"))
    # skippable_resources.add(URIRef("http://edamontology.org#namespace"))
    # skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0002579"))
    # skippable_resources.add(URIRef("http://purl.obolibrary.org/obo/RO_0040042"))
    # skippable_resources.add(URIRef("http://www.geneontology.org/formats/oboInOwl#creation_date"))
    # skippable_resources.add(URIRef("http://edamontology.org#def"))

    # # Loop for all desired categories and add to queue for processing
    # class_count = 0
    # individual_count = 0
    # property_count = 0

    # for category in CLASS_TYPES:
    #     for s in g.subjects(RDF.type, category, unique=True):
    #         if isinstance(s, URIRef) and _is_not_deprecated(s, g):
    #             logger.debug("Adding %s (%s) to queue for processing", s, category)
    #             resource_queue.put(s)
    #             queued_resources.add(s)
    #             class_count += 1
    
    # for category in INDIVIDUAL_TYPES:
    #     for s in g.subjects(RDF.type, category, unique=True):
    #         if isinstance(s, URIRef) and _is_not_deprecated(s, g):
    #             logger.debug("Adding %s (%s) to queue for processing", s, category)
    #             resource_queue.put(s)
    #             queued_resources.add(s)
    #             individual_count += 1
    
    # for category in PROPERTY_TYPES:
    #     for s in g.subjects(RDF.type, category, unique=True):
    #         if isinstance(s, URIRef) and _is_not_deprecated(s, g):
    #             logger.debug("Adding %s (%s) to queue for processing", s, category)
    #             resource_queue.put(s)
    #             queued_resources.add(s)
    #             property_count += 1
    
    # logger.debug("Total classes in primary target: %s", class_count)
    # logger.debug("Total individuals in primary target: %s", individual_count)
    # logger.debug("Total properties in primary target: %s", property_count)
    
    # # Process all subjects in queue
    # logger.info("Processing resources from primary target")
    # try:
    #     while not resource_queue.empty():
    #         s = resource_queue.get()
    #         logger.debug("Processing: %s", s)

    #         # Do not create pages for these resources
    #         if s in do_not_create_resources or not _is_resource_available(s, g):
    #             logger.debug("Skipping page creation")
    #             # Update processed resources
    #             queued_resources.discard(s)
    #             processed_resources.add(s)
    #             continue

    #         # Also skip if the local version is a stub
    #         if s in stubbed_resources:
    #             logger.debug("This stub will be processed later")
    #             continue
            
    #         # Gather resource info
    #         onto_resource = _resource_info(s, g)
    #         _resource_page(onto_resource, g)
            
    #         # Update processed resources
    #         queued_resources.discard(s)
    #         processed_resources.add(s)
        
    #     logger.info("Processing discovered external resources")
        
    #     # Process any external resources that were used
    #     while not external_resource_queue.empty():
    #         s = external_resource_queue.get()
    #         logger.debug("Processing: %s", s)

    #         # Find the right graph to use
    #         external_namespace, _ = split_uri(s)
    #         external_graph = parsed_graphs[external_namespace]

    #         # Do not create pages for these resources
    #         if s in do_not_create_resources or not _is_resource_available(s, external_graph):
    #             logger.debug("Skipping page creation")
    #             # Update processed resources
    #             queued_resources.discard(s)
    #             processed_resources.add(s)
                
    #             continue

    #         # Gather resource info
    #         onto_resource = _resource_info(s, external_graph)
    #         _resource_page(onto_resource, external_graph)
            
    #         # Update processed resources
    #         queued_resources.discard(s)
    #         processed_resources.add(s)
    # finally:
    #     # Save any new or updated graphs locally
    #     for namespace in namespaces_to_save:
    #         logger.info("Saving graph associated with namespace: %s", namespace)
    #         _serialize_graph(namespace)

    #     # TODO Print information useful for future runs
    #     print()
    #     print(f"Initial queue size was {class_count + individual_count + property_count} resources!")
    #     print(f"{len(processed_resources)} total resources were processed!")
    #     print("Graphs Used:")
    #     for parsed_graph in  parsed_graphs.keys():
    #         print(f"  {parsed_graph}")
    #     print("Bad Namespaces:")
    #     for bad_namespace in bad_namespaces:
    #         print(f" {bad_namespace}")
    #     print("Bad Resources:")
    #     for bad_resource in bad_resources:
    #             print(f" {bad_resource}")
    #     print("Stubbed Resources:")
    #     for stubbed_resource in stubbed_resources:
    #             print(f" {stubbed_resource}")
    #     # TODO this could be used for partial run recovery
    #     print(f"Processed resources: {list(map(str, processed_resources))}")
    #     if not resource_queue.empty():
    #         print("Unprocessed resources in main file:")
    #         while not resource_queue.empty():
    #             print(resource_queue.get())
    #     if not external_resource_queue.empty():
    #         print("Unprocessed external resources:")
    #         while not external_resource_queue.empty():
    #             print(external_resource_queue.get())

    #     # Create top-level index.md file
    #     # Sort namespaces alphabetically
    #     # NOTE: This will not always produce an intuitive result (e.g. the expected name could appear later in the URI)
    #     sorted_namespaces = sorted(parsed_graphs.keys())

    #     base_index_path = f"{BASE_PATH}/index.md" if BASE_PATH else "index.md"
    #     with open(base_index_path, "w", encoding="utf-8") as base_index_file:
    #         base_index_file.write("# Namespaces\n")

    #         for namespace in sorted_namespaces:
    #             if BASE_PATH:
    #                 base_index_file.write(f"- [{namespace}]({BASE_PATH}/{_namespace_to_file_name(namespace)}/)\n")
    #             else:
    #                 base_index_file.write(f"- [{namespace}]({_namespace_to_file_name(namespace)}/)\n")

    #     # Create namespace-level index.md files
    #     for directory_name in os.listdir(BASE_PATH):
    #         if directory_name == "index.md" or directory_name == "log.md":
    #             continue
    
    #         onto_directory_path = f"{BASE_PATH + "/" if BASE_PATH else ""}{directory_name}"
    #         with open(f"{onto_directory_path}/index.md", "w", encoding="utf-8") as namespace_index_file:
    #             namespace_index_file.write("# Resources\n")
    
    #             for file_name in os.listdir(onto_directory_path):
    #                     if file_name == "index.md" or directory_name == "log.md":
    #                         continue
    
    #                     resource_title = ""
    #                     with open(f"{onto_directory_path}/{file_name}", "r", encoding="utf-8") as resource_file:
    #                         for i, line in enumerate(resource_file):
    #                             # NOTE: Magic number, but that part of the frontmatter should be consistent
    #                             if i == 2:
    #                                 # Grab everything after "title: "
    #                                 resource_title = line[7:].strip()
    
    #                     if resource_title:
    #                         namespace_index_file.write(f"- [{resource_title}]({onto_directory_path}/{file_name})\n")
    
    # logger.info("Script completed")
    return