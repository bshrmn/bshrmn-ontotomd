import os
from owlready2 import *
from owlready2.base import _universal_abbrev_2_iri
from datetime import datetime
import json

restriction_type_to_text = {
    SOME    : "some",
    ONLY    : "only",
    MIN     : "min",
    MAX     : "max",
    EXACTLY : "exactly",
    VALUE   : "value",
    HAS_SELF: "has_self",
}

def _convert_space_to_underscore(txt: str) -> str:
    return txt.replace(" ", "_")

def _get_simplest_class_name(cls: ThingClass) -> str:
    if getattr(cls, "label", None):
        return cls.label.first() or cls.name
    elif getattr(cls, "name", None):
        return cls.name
    else:
        return str(cls)

def _normalize_class_name(cls: ThingClass | str) -> str:
    return _convert_space_to_underscore(_get_simplest_class_name(cls))

# TODO Make this into a template so I can allow for other link styles
# TODO Prefix the link with the output folder in case there are notes with the same name in the vault already
def _create_link(txt: str) -> str:
    return f"[[{txt}]]"

# Found onto._parse_list which hopefully avoids having to do this
# def _expand_blank_node_txt(value) -> str:
#     value_triples = onto._get_obj_triples_s_po(value.storid)
#     print(f"Triple results: {value_triples}")

#     blank_node_txt = "("

#     for value_triple in value_triples:
#         (value_predicate, value_object) = value_triple

#         if value_predicate > 0:
#             blank_node_txt += onto._unabbreviate(value_predicate)
#             print(f"Cur txt1: {blank_node_txt}")
#         else:
#             print("HERE1")
#             blank_node_txt += _expand_blank_node_txt(default_world._get_by_storid(value_predicate))
#             print(f"Cur txt2: {blank_node_txt}")
        
#         # TODO Figure out how I want to delimit this
#         blank_node_txt += " o "
#         print(f"Cur txt3: {blank_node_txt}")

#         if value_object > 0:
#             blank_node_txt += onto._unabbreviate(value_object)
#             print(f"Cur txt4: {blank_node_txt}")
#         else:
#             print("HERE2")
#             blank_node_txt += _expand_blank_node_txt(default_world._parse_bnode(value_object))
#             print(f"Cur txt5: {blank_node_txt}")
        
#         blank_node_txt += ", "
    
#     blank_node_txt += ")"
#     print(f"Cur txt6: {blank_node_txt}")
#     return blank_node_txt

def _normalize_value(value) -> str:
    if isinstance(value, Thing):
        # Check if this is actually a blank node
        if value.storid < 0:
            elements = []

            for element in onto._parse_list(value.storid):
                elements.append(_normalize_value(element))
            
            if len(elements) == 0:
                # TODO See if this might occur depending on the bnode type
                print("Unhandled type of bnode!")
                1/0
            else:
                return "(" + ", ".join(elements) + ")"
        else:
            return _create_link(_normalize_class_name(value))
    elif isinstance(value, EntityClass):
        if getattr(value, "label", None) is None or not value.label:
            # This is probably a foreign declaration
            # get_iri was occasionally throwing errors about the passed arguments so attempt both ways
            try:
                return value.get_iri(value)
            except:
                return value.get_iri()
        else:
            return _create_link(_normalize_class_name(value))
    elif isinstance(value, str):
        return value
    elif isinstance(value, int) or isinstance(value, float):
        return value
    elif isinstance(value, bool):
        return value
    elif isinstance(value, datetime):
        # The datetime format could be an option but ISO seems fine
        return value.isoformat()
    elif isinstance(value, Not):
        return f"not ({_normalize_value(value.Class)})"
    elif isinstance(value, Or):
        return f"({' or '.join(_normalize_value(cls) for cls in value.Classes)})"
    elif isinstance(value, And):
        return f"({' and '.join(_normalize_value(cls) for cls in value.Classes)})"
    elif isinstance(value, OneOf): # TODO generated - needs to be tested
        1/0 # TODO remove after testing to see if it should occur
        return f"one of ({', '.join(_normalize_value(instance) for instance in value.instances)})"
    elif isinstance(value, Inverse):
        return f"inverse of {_normalize_value(value.property)}"
    elif isinstance(value, ConstrainedDatatype): # TODO generated - needs to be tested
        1/0 # TODO remove after testing to see if it should occur
        return f"constrained datatype of {_create_link(_normalize_class_name(value.datatype))} with constraints {_normalize_value(value.constraints)}"
    elif isinstance(value, Restriction):
        return f"({_expand_restriction_txt(value)})"
    elif isinstance(value, type):
        return value.__name__
    else:
        raise ValueError(f"Unhandled value type {type(value)} with value {value}")

 # TODO cardinality may also need to be considered in the future
def _get_restriction_triple(restriction: Restriction) -> tuple[str, str, str]:
    property_txt = _normalize_class_name(restriction.property)
    type_txt = restriction_type_to_text.get(restriction.type, "UNKNOWN")
    
    # TODO For some reason has_self can have an owl.Thing value instead of a boolean
    if type_txt == "has_self":
        value_txt = _normalize_value(True if restriction.value else False)
    else:
        value_txt = _normalize_value(restriction.value)

    return (property_txt, type_txt, value_txt)

def _expand_restriction_txt(restriction: Restriction) -> str:
    (property_txt, type_txt, value_txt) = _get_restriction_triple(restriction)
    return f"{property_txt} {type_txt} {value_txt}"

if __name__ == "__main__":
    onto : Ontology = get_ontology("input/swo.owl").load()
    
    # Look up some of the ontology objects ahead of time
    # TODO Will need to specify what this property should be for each ontology
    definition_property = onto.search_one(iri = "http://purl.obolibrary.org/obo/IAO_0000115")

    # TODO Consider if I want to handle checks involving rdf:type differently
    rdf_type_iri = _universal_abbrev_2_iri.get(rdf_type)
    rdf_type_object = onto.search_one(iri = rdf_type_iri)

    # TODO Exploration to see if I can find the base ontology for when I do foreign lookups
    # results = list(default_world.sparql("""
    #        SELECT ?x
    #        { ?x a owl:Ontology . }
    # """))

    # print(results)
    # for r in results:
    #     if r[0].iri == "http://anonymous":
    #         continue
    #     print(f"Ontology found : {r[0]} - {r[0].iri}")

    # Print classes as list
    # print(list(onto.classes()))
    
    # Track namespaces we come across
    namespaces = {}

    # Track deprecated classes
    # deprecated_class_count = 0

    # # Classes
    # for i in onto.classes():
    #     i : ThingClass
    #     # TODO consider multiple labels and multiple languages
    #     print(f"Class : {i} : {i.label.first() or i.name}")

    #     if deprecated[i]:
    #         deprecated_class_count += 1
    #         print("Skipping deprecated class...")
    #         print()
    #         continue

    #     # Add namespace to set of namespaces
    #     namespaces[i.namespace.name] = i.namespace.get_base_iri()

    #     # Track property restrictions listed under subClassOf
    #     property_map = {}

    #     parent_classes : CallbackList = i.is_a
    #     for parent in parent_classes:
    #         if isinstance(parent, Restriction):
    #             # print(f"Restriction on property : {_expand_restriction_txt(parent)}")

    #             # Track property restrictions and use later when printing properties
    #             (property_name, property_type, property_value) = _get_restriction_triple(parent)
    #             if property_name not in property_map:
    #                 property_map[property_name] = []
                
    #             property_map[property_name].append(f"{property_type} {property_value}")
    #         elif isinstance(parent, And):
    #             print(f"Intersection of : {parent.Classes}")
    #         elif isinstance(parent, Or): # TODO generated - needs to be tested
    #             print(f"Union of : {parent.Classes}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, Not): # TODO generated - needs to be tested
    #             print(f"Negation of : {parent.Class}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, OneOf): # TODO generated - needs to be tested
    #             print(f"One of : {parent.instances}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, Inverse): # TODO generated - needs to be tested
    #             print(f"Inverse of : {parent.property} with value {parent.value}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, ConstrainedDatatype): # TODO generated - needs to be tested
    #             print(f"Constrained Datatype : {parent.datatype} with constraints {parent.constraints}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         else:
    #             print(f"Parent : {parent} : {parent.label.first() or parent.name}")
        
    #     # Check what properties we found through restrictions
    #     # print(property_map)

    #     properties : set[PropertyClass] = i.get_class_properties()
    #     has_definition = False
    #     for prop in properties:
    #         if prop == definition_property:
    #             has_definition = True
    #             continue

    #         # Skip properties that were already processed through restrictions
    #         if _normalize_class_name(prop) in property_map:
    #             continue
            
    #         property_name = _normalize_class_name(prop)

    #         if isinstance(prop, PropertyClass):
    #             prop_value = prop[i]
    #             # TODO This should probably be an option for a specific language
    #             # prop_value = prop_value.get_lang("all") or prop_value
    #             # Retrieve values for specified language if multiple languages are present
    #             prop_value = prop_value.get_lang("en") or prop_value
    #             if isinstance(prop_value, list):
    #                 if all(v is None for v in prop_value):
    #                     # Skip the property if all values are None
    #                     continue
    #                 else:
    #                     # Normalize value list elements
    #                     # prop_value = [_normalize_value(v) for v in prop_value]
    #                     # print(f"Property : {prop} : {_create_link(_normalize_class_name(prop))} : {prop_value}")

    #                     property_map[property_name] = []

    #                     for v in prop_value:
    #                         property_map[property_name].append(_normalize_value(v))
    #             else:
    #                 # Assuming that this is either a single value or logical construct
    #                 # print(f"Property: {prop} : {_create_link(_normalize_class_name(prop))} : {_normalize_value(prop_value)}")

    #                 property_map[property_name] = []
    #                 property_map[property_name].append(_normalize_value(prop_value))

    #                 1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(prop, Inverse):
    #             # print(f"Property : Inverse of {_create_link(_normalize_class_name(prop.property))}")

    #             property_map[property_name] = []
    #             property_map[property_name].append(f"inverse of {_normalize_value(prop.property)}")
    #         else:
    #             raise ValueError(f"Unhandled property type {type(prop)} for property {prop}")
        
    #     # Check what properties we found
    #     for k, v in property_map.items():
    #         if isinstance(v, list):
    #             for v_i in v:
    #                 print(f"Property : {k} : {v_i}")
    #         else:
    #             print(f"Property : {k} : {v}")
        
    #     if has_definition:
    #         definition_value = definition_property[i]

    #         if isinstance(definition_value, list):
    #             for definition in definition_value:
    #                 definition_lang = getattr(definition, "lang", None)

    #                 # TODO Decide on how I want to handle multiple languages in locstrs
    #                 if definition_lang == "en":
    #                     print(f"Definition : {str(definition)}")
    #                 elif definition_lang is None:
    #                     print(f"Definition : {definition}")
    #                 else:
    #                     print(f"Definition : {definition} : Unsupported language")
    #         else:
    #             print(f"Definition : {definition_value.get_lang("en") or definition_value}")
        
    #     print()
    
    # print(namespaces)
    # print(f"Deprecated: {deprecated_class_count}")

    # # Track deprecated individuals
    # deprecated_individual_count = 0
    
    # # Individuals
    # for i in onto.individuals():
    #     i : NamedIndividual
    #     # TODO consider multiple labels and multiple languages
    #     print(f"Individual : {i} : {i.label.first() or i.name}")

    #     if deprecated[i]:
    #         deprecated_individual_count += 1
    #         print("Skipping deprecated individual...")
    #         print()
    #         continue

    #     # Add namespace to set of namespaces
    #     namespaces[i.namespace.name] = i.namespace.get_base_iri()

    #     # Track property restrictions listed under subClassOf
    #     property_map = {}

    #     parent_classes : CallbackList = i.is_a
    #     for parent in parent_classes:
    #         if isinstance(parent, Restriction):
    #             # print(f"Restriction on property : {_expand_restriction_txt(parent)}")

    #             # Track property restrictions and use later when printing properties
    #             (property_name, property_type, property_value) = _get_restriction_triple(parent)
    #             if property_name not in property_map:
    #                 property_map[property_name] = []
                
    #             property_map[property_name].append(f"{property_type} {property_value}")
    #         elif isinstance(parent, And):
    #             print(f"Intersection of : {parent.Classes}")
    #         elif isinstance(parent, Or): # TODO generated - needs to be tested
    #             print(f"Union of : {parent.Classes}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, Not): # TODO generated - needs to be tested
    #             print(f"Negation of : {parent.Class}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, OneOf): # TODO generated - needs to be tested
    #             print(f"One of : {parent.instances}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, Inverse): # TODO generated - needs to be tested
    #             print(f"Inverse of : {parent.property} with value {parent.value}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(parent, ConstrainedDatatype): # TODO generated - needs to be tested
    #             print(f"Constrained Datatype : {parent.datatype} with constraints {parent.constraints}")
    #             1/0 # TODO remove after testing to see if it should occur
    #         else:
    #             print(f"Parent : {parent} : {parent.label.first() or parent.name}")
        
    #     # Check what properties we found through restrictions
    #     # print(property_map)

    #     properties : set[PropertyClass] = i.get_properties()
    #     has_definition = False
    #     for prop in properties:
    #         if prop == definition_property:
    #             has_definition = True
    #             continue

    #         # Skip properties that were already processed through restrictions
    #         if _normalize_class_name(prop) in property_map:
    #             continue
            
    #         property_name = _normalize_class_name(prop)

    #         if prop == rdf_type_object:
    #             # Skip rdf type as it should already be handled by the parent classes
    #             print(f"Skipping {prop}: {prop[i]}")
    #             continue
    #         elif isinstance(prop, PropertyClass):
    #             prop_value = prop[i]
    #             # TODO This should probably be an option for a specific language
    #             # prop_value = prop_value.get_lang("all") or prop_value
    #             # Retrieve values for specified language if multiple languages are present
    #             prop_value = prop_value.get_lang("en") or prop_value
    #             if isinstance(prop_value, list):
    #                 if all(v is None for v in prop_value):
    #                     # Skip the property if all values are None
    #                     continue
    #                 else:
    #                     # Normalize value list elements
    #                     # prop_value = [_normalize_value(v) for v in prop_value]
    #                     # print(f"Property : {prop} : {_create_link(_normalize_class_name(prop))} : {prop_value}")

    #                     property_map[property_name] = []

    #                     for v in prop_value:
    #                         property_map[property_name].append(_normalize_value(v))
    #             else:
    #                 # Assuming that this is either a single value or logical construct
    #                 # print(f"Property: {prop} : {_create_link(_normalize_class_name(prop))} : {_normalize_value(prop_value)}")

    #                 property_map[property_name] = []
    #                 property_map[property_name].append(_normalize_value(prop_value))

    #                 1/0 # TODO remove after testing to see if it should occur
    #         elif isinstance(prop, Inverse):
    #             # print(f"Property : Inverse of {_create_link(_normalize_class_name(prop.property))}")

    #             property_map[property_name] = []
    #             property_map[property_name].append(f"inverse of {_normalize_value(prop.property)}")
    #         else:
    #             raise ValueError(f"Unhandled property type {type(prop)} for property {prop}")
        
    #     # Check what properties we found
    #     for k, v in property_map.items():
    #         if isinstance(v, list):
    #             for v_i in v:
    #                 print(f"Property : {k} : {v_i}")
    #         else:
    #             print(f"Property : {k} : {v}")
        
    #     if has_definition:
    #         definition_value = definition_property[i]

    #         if isinstance(definition_value, list):
    #             for definition in definition_value:
    #                 definition_lang = getattr(definition, "lang", None)

    #                 # TODO Decide on how I want to handle multiple languages in locstrs
    #                 if definition_lang == "en":
    #                     print(f"Definition : {str(definition)}")
    #                 elif definition_lang is None:
    #                     print(f"Definition : {definition}")
    #                 else:
    #                     print(f"Definition : {definition} : Unsupported language")
    #         else:
    #             print(f"Definition : {definition_value.get_lang("en") or definition_value}")
        
    #     print()

    # print(namespaces)
    # print(f"Deprecated: {deprecated_individual_count}")

    # # Track deprecated properties
    # deprecated_property_count = 0

    # # Properties
    # for prop in onto.properties():
    #     print(f"Property : {prop} : {prop.label.first() or prop.name}")

    #     if deprecated[prop]:
    #         deprecated_property_count += 1
    #         print("Skipping deprecated property...")
    #         print()
    #         continue

    #     # Add namespace to set of namespaces
    #     namespaces[prop.namespace.name] = prop.namespace.get_base_iri()

    #     # Ignore rdf:type so that I can identify where foreign lookups are needed
    #     query = """
    #         SELECT ?predicate ?object
    #         {{ <{property}> ?predicate ?object . FILTER(?predicate != rdf:type) }}
    #     """.format(property=prop.get_iri())

    #     results = list(default_world.sparql(query))

    #     # TODO check if empty
    #     if len(results) == 0:
    #         print("Foreign link")
        
    #     for r in results:
    #         r_predicate = r[0]
    #         r_object = r[1]

    #         if isinstance(r_predicate, int):
    #             predicate_iri = _universal_abbrev_2_iri.get(r_predicate, r_predicate)
    #             predicate_object = onto.search_one(iri = predicate_iri)

    #             r_predicate = predicate_iri if predicate_object is None else predicate_object
            
    #         # Handle this in value resolution instead
    #         # if isinstance(r_object, type):
    #         #     r_object = r_object.__name__

    #             # The below code can get the abbreviation, but the IRI itself seems to be irretrievable
    #             # type_abbrev = _universal_datatype_2_abbrev.get(r_object, None)
            
    #         # print(f"Raw Result : {r_predicate} : {r_object}")
    #         # print(f"Type of predicate: {type(r_predicate)}")
    #         # print(f"Type of object: {type(r_object)}")
    #         print(f"Relation : {_normalize_value(r_predicate)} : {_normalize_value(r_object)}")
        
    #     print()
    
    # print(namespaces)
    # print(f"Deprecated: {deprecated_property_count}")

    
    # How many classes, properties, and individuals are there?
    # print(len(list(onto.classes())))
    # print(len(list(onto.properties())))
    # print(len(list(onto.individuals())))

    ############
    ### MAIN ###
    ############
    # Create output directory
    output_path = "output" # TODO this should be an input option
    os.makedirs(output_path, exist_ok=True)

    # Track namespaces we come across
    namespace_dict = {}

    # Track deprecated resources
    deprecated_class_count = 0
    deprecated_individual_count = 0
    deprecated_property_count = 0

    # Grab a slice of the classes for testing
    class_sample = itertools.islice(onto.classes(), 5)

    # Create a text file for each Class
    for onto_class in class_sample:
        onto_class : ThingClass
        
        # TODO remove
        print(f"Class : {onto_class} : {onto_class.label.first() or onto_class.name}")

        if deprecated[onto_class]:
            deprecated_class_count += 1
            continue

        class_name_normed = _normalize_class_name(onto_class) # Replace spaces with underscores for file naming
        class_namespace_name = onto_class.namespace.name

        # Add namespace to set of namespaces
        namespace_dict[class_namespace_name] = onto_class.namespace.get_base_iri()

        # Track property restrictions listed under subClassOf
        property_dict = {}

        # Track super classes to print them later
        super_classes_dict = {}

        super_classes : CallbackList = onto_class.is_a
        for super_class in super_classes:
            if isinstance(super_class, Restriction):
                # Track property restrictions and use later when printing properties
                (property_name, property_type, property_value) = _get_restriction_triple(super_class)
                if property_name not in property_dict:
                    property_dict[property_name] = []
                
                property_dict[property_name].append(f"{property_type} {property_value}")
            elif isinstance(super_class, And):
                if "Intersection Of" not in super_classes_dict:
                    super_classes_dict["Intersection Of"] = []
                
                super_classes_dict["Intersection Of"].append(f"{super_class.Classes}\n")
            elif isinstance(super_class, Or): # TODO generated - needs to be tested
                if "Union Of" not in super_classes_dict:
                    super_classes_dict["Union Of"] = []
                
                super_classes_dict["Union Of"].append(f"{super_class.Classes}\n")
            elif isinstance(super_class, Not): # TODO generated - needs to be tested
                if "Complement Of" not in super_classes_dict:
                    super_classes_dict["Complement Of"] = []
                
                super_classes_dict["Complement Of"].append(f"{super_class.Class}\n")
            elif isinstance(super_class, OneOf): # TODO generated - needs to be tested
                if "One Of" not in super_classes_dict:
                    super_classes_dict["One Of"] = []
                
                super_classes_dict["One Of"].append(f"{super_class.instances}\n")
            elif isinstance(super_class, Inverse): # TODO generated - needs to be tested
                if "Inverse Of" not in super_classes_dict:
                    super_classes_dict["Inverse Of"] = []
                
                super_classes_dict["Inverse Of"].append(f"{super_class.property} with value {super_class.value}\n")
            elif isinstance(super_class, ConstrainedDatatype): # TODO generated - needs to be tested
                if "Constrained By" not in super_classes_dict:
                    super_classes_dict["Constrained By"] = []
                
                super_classes_dict["Constrained By"].append(f"{super_class.datatype} with constraints {super_class.constraints}\n")
            else:
                if "Subclass Of" not in super_classes_dict:
                    super_classes_dict["Subclass Of"] = []
                
                super_classes_dict["Subclass Of"].append(f"{_create_link(_normalize_class_name(super_class))}\n")
            
        # Sort the super classes by key so that they print alphabetically in the output file
        super_classes_dict = dict(sorted(super_classes_dict.items()))

        properties : set[PropertyClass] = onto_class.get_class_properties()
        has_definition = False

        for prop in properties:
            # Skip properties that were already processed through restrictions
            if _normalize_class_name(prop) in property_dict:
                continue
            
            property_name = _normalize_class_name(prop)

            if prop == definition_property:
                has_definition = True
                property_dict[property_name] = []
                continue

            if isinstance(prop, PropertyClass):
                prop_value = prop[onto_class]
                prop_value = prop_value.get_lang("en") or prop_value

                if isinstance(prop_value, list):
                    if all(v is None for v in prop_value):
                        # Skip the property if all values are None
                        continue
                    else:
                        property_dict[property_name] = []

                        for v in prop_value:
                            property_dict[property_name].append(f"{_normalize_value(v)}\n")
                else:
                    # Assuming that this is either a single value or logical construct
                    property_dict[property_name] = []
                    property_dict[property_name].append(f"{_normalize_value(prop_value)}\n")
            elif isinstance(prop, Inverse):
                property_dict[property_name] = []
                property_dict[property_name].append(f"inverse of {_normalize_value(prop.property)}\n")
            else:
                raise ValueError(f"Unhandled property type {type(prop)} for property {prop}")
        
        # TODO Not sure if I want to handle this separately from the other properties anymore
        if has_definition:
            definition_value = definition_property[onto_class]
            definition_property_name = _normalize_class_name(definition_property)

            if isinstance(definition_value, list):
                for definition in definition_value:
                    definition_lang = getattr(definition, "lang", None)

                    # TODO Decide on how I want to handle multiple languages in locstrs
                    if definition_lang == "en":
                        property_dict[definition_property_name].append(f"{str(definition)}\n")
                    elif definition_lang is None:
                        property_dict[definition_property_name].append(f"{definition}\n")
            else:
                property_dict[definition_property_name].append(f"{definition_value.get_lang("en") or definition_value}\n")
        
        # Sort the properties by key so that they print alphabetically in the output file
        property_dict = dict(sorted(property_dict.items()))
        
        # Create a directory for the namespace
        namespace_directory = os.path.join(output_path, class_namespace_name)
        os.makedirs(namespace_directory, exist_ok=True)
        
        with open(os.path.join(namespace_directory, f"{class_name_normed}.md"), "w") as file:
            # Metadata block
            file.write("---\n")
            # Include alias if different than pretty name
            if class_name_normed != _normalize_class_name(onto_class.name):
                file.write("aliases:\n")
                file.write(f"  - {onto_class.name}\n")
            file.write("ontologytype: Class\n")
            file.write("---\n")
            
            # Turn the super classes into headers
            if len(super_classes_dict) > 0:
                file.write("# Super Classes\n")
                for k, v in super_classes_dict.items():
                    file.write(f"## {k}\n")
                    file.writelines(v)
                    file.write("\n")
            
            # Turn the class properties into headers
            if len(property_dict) > 0:
                file.write("# Properties\n")
                for k, v in property_dict.items():
                    file.write(f"## {k}\n")
                    file.writelines(v)
                    file.write("\n")
    
    # Grab a slice of the individuals for testing
    individuals_sample = itertools.islice(onto.individuals(), 5)
    
    # Individuals
    for onto_individual in individuals_sample:
        onto_individual : NamedIndividual

        # TODO remove
        print(f"Individual : {onto_individual} : {onto_individual.label.first() or onto_individual.name}")

        if deprecated[onto_individual]:
            deprecated_individual_count += 1
            continue

        individual_name_normed = _normalize_class_name(onto_individual) # Replace spaces with underscores for file naming
        individual_namespace_name = onto_individual.namespace.name

        # Add namespace to set of namespaces
        namespace_dict[individual_namespace_name] = onto_individual.namespace.get_base_iri()

        # Track property restrictions listed under subClassOf
        property_dict = {}

        # Track super classes to print them later
        super_classes_dict = {}

        super_classes : CallbackList = onto_individual.is_a
        for super_class in super_classes:
            if isinstance(super_class, Restriction):
                # Track property restrictions and use later when printing properties
                (property_name, property_type, property_value) = _get_restriction_triple(super_class)
                if property_name not in property_dict:
                    property_dict[property_name] = []
                
                property_dict[property_name].append(f"{property_type} {property_value}")
            elif isinstance(super_class, And):
                if "Intersection Of" not in super_classes_dict:
                    super_classes_dict["Intersection Of"] = []
                
                super_classes_dict["Intersection Of"].append(f"{super_class.Classes}\n")
            elif isinstance(super_class, Or): # TODO generated - needs to be tested
                if "Union Of" not in super_classes_dict:
                    super_classes_dict["Union Of"] = []
                
                super_classes_dict["Union Of"].append(f"{super_class.Classes}\n")
            elif isinstance(super_class, Not): # TODO generated - needs to be tested
                if "Complement Of" not in super_classes_dict:
                    super_classes_dict["Complement Of"] = []
                
                super_classes_dict["Complement Of"].append(f"{super_class.Class}\n")
            elif isinstance(super_class, OneOf): # TODO generated - needs to be tested
                if "One Of" not in super_classes_dict:
                    super_classes_dict["One Of"] = []
                
                super_classes_dict["One Of"].append(f"{super_class.instances}\n")
            elif isinstance(super_class, Inverse): # TODO generated - needs to be tested
                if "Inverse Of" not in super_classes_dict:
                    super_classes_dict["Inverse Of"] = []
                
                super_classes_dict["Inverse Of"].append(f"{super_class.property} with value {super_class.value}\n")
            elif isinstance(super_class, ConstrainedDatatype): # TODO generated - needs to be tested
                if "Constrained By" not in super_classes_dict:
                    super_classes_dict["Constrained By"] = []
                
                super_classes_dict["Constrained By"].append(f"{super_class.datatype} with constraints {super_class.constraints}\n")
            else:
                if "Subclass Of" not in super_classes_dict:
                    super_classes_dict["Subclass Of"] = []
                
                super_classes_dict["Subclass Of"].append(f"{_create_link(_normalize_class_name(super_class))}\n")
        
        # Sort the super classes by key so that they print alphabetically in the output file
        super_classes_dict = dict(sorted(super_classes_dict.items()))

        properties : set[PropertyClass] = onto_individual.get_properties()
        has_definition = False

        for prop in properties:
            # Skip properties that were already processed through restrictions
            if _normalize_class_name(prop) in property_dict:
                continue
            
            property_name = _normalize_class_name(prop)

            if prop == definition_property:
                has_definition = True
                property_dict[property_name] = []
                continue

            if prop == rdf_type_object:
                # Skip rdf type as it should already be handled by the parent classes
                continue
            elif isinstance(prop, PropertyClass):
                prop_value = prop[onto_individual]
                prop_value = prop_value.get_lang("en") or prop_value

                if isinstance(prop_value, list):
                    if all(v is None for v in prop_value):
                        # Skip the property if all values are None
                        continue
                    else:
                        property_dict[property_name] = []

                        for v in prop_value:
                            property_dict[property_name].append(f"{_normalize_value(v)}\n")
                else:
                    # Assuming that this is either a single value or logical construct
                    property_dict[property_name] = []
                    property_dict[property_name].append(f"{_normalize_value(prop_value)}\n")
            elif isinstance(prop, Inverse):
                property_dict[property_name] = []
                property_dict[property_name].append(f"inverse of {_normalize_value(prop.property)}\n")
            else:
                raise ValueError(f"Unhandled property type {type(prop)} for property {prop}")
        
        # TODO Not sure if I want to handle this separately from the other properties anymore
        if has_definition:
            definition_value = definition_property[onto_individual]
            definition_property_name = _normalize_class_name(definition_property)

            if isinstance(definition_value, list):
                for definition in definition_value:
                    definition_lang = getattr(definition, "lang", None)

                    # TODO Decide on how I want to handle multiple languages in locstrs
                    if definition_lang == "en":
                        property_dict[definition_property_name].append(f"{str(definition)}\n")
                    elif definition_lang is None:
                        property_dict[definition_property_name].append(f"{definition}\n")
            else:
                property_dict[definition_property_name].append(f"{definition_value.get_lang("en") or definition_value}\n")

        # Sort the properties by key so that they print alphabetically in the output file
        property_dict = dict(sorted(property_dict.items()))
        
        # Create a directory for the namespace
        namespace_directory = os.path.join(output_path, individual_namespace_name)
        os.makedirs(namespace_directory, exist_ok=True)
        
        with open(os.path.join(namespace_directory, f"{individual_name_normed}.md"), "w") as file:
            # Properties block
            # Include alias if different than pretty name
            if individual_name_normed != _normalize_class_name(onto_individual.name):
                file.write("---\n")
                file.write("aliases:\n")
                file.write(f"  - {onto_individual.name}\n")
                file.write("ontologytype: Individual\n")
                file.write("---\n")
            
            # Turn the super classes into headers
            file.write("# Super Classes\n")
            for k, v in super_classes_dict.items():
                file.write(f"## {k}\n")
                file.writelines(v)
                file.write("\n")
            
            # Turn the properties into headers
            file.write("# Properties\n")
            for k, v in property_dict.items():
                file.write(f"## {k}\n")
                file.writelines(v)
                file.write("\n")

    # Grab a slice of the classes for testing
    properties_sample = itertools.islice(onto.properties(), 5)

    # Create a text file for each Property
    for onto_prop in properties_sample:
        onto_prop : PropertyClass

        print(f"Property : {onto_prop} : {onto_prop.label.first() or onto_prop.name}")

        if deprecated[onto_prop]:
            deprecated_property_count += 1
            continue

        prop_name_normed = _normalize_class_name(onto_prop) # Replace spaces with underscores for file naming
        prop_namespace_name = onto_prop.namespace.name

        # Add namespace to set of namespaces
        namespace_dict[prop_namespace_name] = onto_prop.namespace.get_base_iri()

        # Ignore rdf:type so that I can identify where foreign lookups are needed
        query = """
            SELECT ?predicate ?object
            {{ <{property}> ?predicate ?object . FILTER(?predicate != rdf:type) }}
        """.format(property=onto_prop.get_iri())

        subproperties = list(default_world.sparql(query))

        # If there are no results, the property probably has a foreign declaration
        if len(subproperties) == 0:
            # TODO Add special logic for foreign declarations here
            print(f"{onto_prop} appears to be a foreign declaration")

            # Create a directory for the namespace
            namespace_directory = os.path.join(output_path, prop_namespace_name)
            os.makedirs(namespace_directory, exist_ok=True)

            with open(os.path.join(namespace_directory, f"{prop_name_normed}.md"), "w") as file:
                # TODO Placeholder for now
                file.write(f"This property is defined at {onto_prop.iri}.\n")
            
            continue

        # Track subpropertoes to print them later
        subprop_dict = {}
        
        for subprop in subproperties:
            (subprop_predicate, subprop_object) = subprop

            # Owlready2 abbreviates some common resources so I need to unabbreviate them
            if isinstance(subprop_predicate, int):
                predicate_iri = _universal_abbrev_2_iri.get(subprop_predicate, subprop_predicate)
                predicate_object = onto.search_one(iri = predicate_iri)

                # TODO If the object can't be found, I'll want to handle this as a foreign key
                subprop_predicate = predicate_iri if predicate_object is None else predicate_object
            
            subprop_dict_key = _normalize_value(subprop_predicate)
            if subprop_dict_key not in subprop_dict:
                subprop_dict[subprop_dict_key] = []
            
            subprop_dict[_normalize_value(subprop_predicate)].append(f"{_normalize_value(subprop_object)}\n")
        
        # Sort the subproperties by key so that they print alphabetically in the output file
        subprop_dict = dict(sorted(subprop_dict.items()))

        # Create a directory for the namespace
        namespace_directory = os.path.join(output_path, prop_namespace_name)
        os.makedirs(namespace_directory, exist_ok=True)

        with open(os.path.join(namespace_directory, f"{prop_name_normed}.md"), "w") as file:
            # Metadata block
            file.write("---\n")
            # Include alias if different than pretty name
            if prop_name_normed != _normalize_class_name(onto_prop.name):
                file.write("aliases:\n")
                file.write(f"  - {onto_prop.name}\n")
            file.write("ontologytype: Property\n")
            file.write("---\n")
            
            # Turn the subproperties into headers
            if len(subprop_dict) > 0:
                file.write("# Properties\n")
                for k, v in subprop_dict.items():
                    file.write(f"## {k}\n")
                    file.writelines(v)
                    file.write("\n")
    
    # Add a file at the top level that maps the directory names to IRIs
    with open(os.path.join(output_path, "namespaces.json"), "w") as file:
        json.dump(namespace_dict, file)
    
    # Check how many resources were not used (deprecated)
    print("Deprecated Resources:")
    print(f"Classes: {deprecated_class_count}")
    print(f"Individuals: {deprecated_individual_count}")
    print(f"Properties: {deprecated_property_count}")
    ############
    #/# MAIN #/#
    ############

    # my_class = next(onto.classes())
    # attrs = vars(my_class)
    # print(', '.join("%s: %s" % item for item in attrs.items()))
    
    # Annotation Properties
    # for i in onto.annotation_properties():
    #     print(i.label)

    # Object Properties
    # for i in onto.object_properties():
    #     print(i.label)
    
    # Search for specific class
    # search_result = onto.search_one(label = "single generalization algorithm")
    # print(search_result.comment)
    # print(onto.imported_ontologies)