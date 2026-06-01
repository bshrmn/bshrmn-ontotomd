# TODO Move this into a notebook for easier exploration

import os
from owlready2 import *

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

def _normalize_value(value) -> str:
    if isinstance(value, Thing):
        return _create_link(_normalize_class_name(value))
    elif isinstance(value, EntityClass):
        return _create_link(_normalize_class_name(value))
    elif isinstance(value, str):
        return value
    elif isinstance(value, int) or isinstance(value, float):
        return value
    elif isinstance(value, bool):
        return value
    elif isinstance(value, Not):
        return f"not ({_normalize_value(value.Class)})"
    elif isinstance(value, Or):
        return f"({' or '.join(_normalize_value(cls) for cls in value.Classes)})"
    elif isinstance(value, And):
        return f"({' and '.join(_normalize_value(cls) for cls in value.Classes)})"
    elif isinstance(value, OneOf): # TODO generated - needs to be tested
        return f"one of ({', '.join(_normalize_value(instance) for instance in value.instances)})"
    elif isinstance(value, Inverse): # TODO generated - needs to be tested
        return f"inverse of {_create_link(_normalize_class_name(value.property))} with value {_normalize_value(value.value)}"
    elif isinstance(value, ConstrainedDatatype): # TODO generated - needs to be tested
        return f"constrained datatype of {_create_link(_normalize_class_name(value.datatype))} with constraints {_normalize_value(value.constraints)}"
    elif isinstance(value, Restriction):
        return f"({_expand_restriction_txt(value)})"
    else:
        raise ValueError(f"Unhandled value type {type(value)} with value {value}")

 # TODO cardinality may also need to be considered in the future
def _expand_restriction_txt(restriction: Restriction) -> str:
    property_txt = _create_link(_normalize_class_name(restriction.property))
    type_txt = restriction_type_to_text.get(restriction.type, "UNKNOWN")
    value_txt = _normalize_value(restriction.value)

    return f"{property_txt} {type_txt} {value_txt}"

if __name__ == "__main__":
    onto : Ontology = get_ontology("input/swo.owl").load()
    
    # TODO Will need to specify what this property should be for each ontology
    definition_property = onto.search_one(iri = "http://purl.obolibrary.org/obo/IAO_0000115")

    # Print classes as list
    # print(list(onto.classes()))
    
    # Classes
    for i in onto.classes():
        i : ThingClass
        print(f"Class : {i} : {i.label.first() or i.name}")
        # print(i.name)
        parent_classes : CallbackList = i.is_a
        for parent in parent_classes:
            if isinstance(parent, Restriction):
                print(f"Restriction on property : {_expand_restriction_txt(parent)}")
            elif isinstance(parent, And):
                print(f"Intersection of : {parent.Classes}")
            elif isinstance(parent, Or): # TODO generated - needs to be tested
                print(f"Union of : {parent.Classes}")
            elif isinstance(parent, Not): # TODO generated - needs to be tested
                print(f"Negation of : {parent.Class}")
            elif isinstance(parent, OneOf): # TODO generated - needs to be tested
                print(f"One of : {parent.instances}")
            elif isinstance(parent, Inverse): # TODO generated - needs to be tested
                print(f"Inverse of : {parent.property} with value {parent.value}")
            elif isinstance(parent, ConstrainedDatatype): # TODO generated - needs to be tested
                print(f"Constrained Datatype : {parent.datatype} with constraints {parent.constraints}")
            else:
                print(f"Parent : {parent} : {parent.label.first() or parent.name}")

        properties : set[PropertyClass] = i.get_class_properties()
        has_definition = False
        for prop in properties:
            if prop == definition_property:
                has_definition = True
                continue
            
            if isinstance(prop, PropertyClass):
                # TODO Fix this to handle the values better
                prop_value = prop[i]
                # TODO This should probably be an option for a specific language
                # prop_value = prop_value.get_lang("all") or prop_value
                # Retrieve values for specified language if multiple languages are present
                prop_value = prop_value.get_lang("en") or prop_value
                if isinstance(prop_value, list):
                    if all(v is None for v in prop_value):
                        # Skip the property if all values are None
                        continue
                    else:
                        # Normalize value list elements
                        prop_value = [_normalize_value(v) for v in prop_value]
                        print(f"Property : {prop} : {_normalize_class_name(prop)} : {prop_value}")
                else:
                    # Assuming that this is either a single value or logical construct
                    print(f"Property: {prop} : {_normalize_class_name(prop)} : {_normalize_value(prop_value)}")
                    1/0
            elif isinstance(prop, Inverse):
                print(f"Property : Inverse of {_create_link(_normalize_class_name(prop.property))}")
            else:
                raise ValueError(f"Unhandled property type {type(prop)} for property {prop}")
        
        if has_definition:
            print(f"Definition : {definition_property[i]}")
        
        print()

    # Individuals
    # for i in onto.individuals():
    #     i : ThingClass
    #     print(f"Individual : {i} : {i.label.first() or i.name}")

    #     parent_classes : CallbackList = i.is_a
    #     parent : ThingClass = parent_classes.first()
    #     if parent:
    #         print(f"Parent : {parent} : {parent.label.first()}")
        
    #     properties : set[PropertyClass] = i.get_properties()
    #     has_definition = False
    #     print("Properties:")
    #     for prop in properties:
    #         if prop == definition_property:
    #             has_definition = True
            
    #         if getattr(prop, "label", None):
    #             print(f"Property : {prop} : {prop.label.first() or prop.name}")
    #         else:
    #             print(f"Property : {prop}")
        
    #     # TODO I might want to leave a placeholder if there is no definition or comment
    #     if has_definition:
    #         print(f"Definition : {getattr(i, definition_property.name, "Could not find definition")}")
    #     else: # Fallback to default rdfs comment
    #         print(f"Comment : {i.comment}")
    #     print()
    
    # How many classes and individuals are there?
    # print(len(list(onto.classes())))
    # print(len(list(onto.individuals())))

    # Create output directory
    # os.makedirs("output", exist_ok=True)

    # # Grab a slice of the classes for testing
    # class_sample = itertools.islice(onto.classes(), 5)

    # # Create a text file for each class
    # for onto_class in class_sample:
    #     onto_class : ThingClass
        
    #     # TODO remove
    #     print(f"Class : {onto_class} : {onto_class.label.first() or onto_class.name}")

    #     class_name_normed = _normalize_class_name(onto_class) # Replace spaces with underscores for file naming

    #     super_classes_dict = {}

    #     super_classes : CallbackList = onto_class.is_a
    #     for super_class in super_classes:
    #         if isinstance(super_class, Restriction):
    #             if "Restriction" not in super_classes_dict:
    #                 super_classes_dict["Restriction"] = []
                
    #             super_classes_dict["Restriction"].append(f"{_expand_restriction_txt(super_class)}\n")
    #         elif isinstance(super_class, And):
    #             if "Intersection Of" not in super_classes_dict:
    #                 super_classes_dict["Intersection Of"] = []
                
    #             super_classes_dict["Intersection Of"].append(f"{super_class.Classes}\n")
    #         elif isinstance(super_class, Or): # TODO generated - needs to be tested
    #             if "Union Of" not in super_classes_dict:
    #                 super_classes_dict["Union Of"] = []
                
    #             super_classes_dict["Union Of"].append(f"{super_class.Classes}\n")
    #         elif isinstance(super_class, Not): # TODO generated - needs to be tested
    #             if "Complement Of" not in super_classes_dict:
    #                 super_classes_dict["Complement Of"] = []
                
    #             super_classes_dict["Complement Of"].append(f"{super_class.Class}\n")
    #         elif isinstance(super_class, OneOf): # TODO generated - needs to be tested
    #             if "One Of" not in super_classes_dict:
    #                 super_classes_dict["One Of"] = []
                
    #             super_classes_dict["One Of"].append(f"{super_class.instances}\n")
    #         elif isinstance(super_class, Inverse): # TODO generated - needs to be tested
    #             if "Inverse Of" not in super_classes_dict:
    #                 super_classes_dict["Inverse Of"] = []
                
    #             super_classes_dict["Inverse Of"].append(f"{super_class.property} with value {super_class.value}\n")
    #         elif isinstance(super_class, ConstrainedDatatype): # TODO generated - needs to be tested
    #             if "Constrained By" not in super_classes_dict:
    #                 super_classes_dict["Constrained By"] = []
                
    #             super_classes_dict["Constrained By"].append(f"{super_class.datatype} with constraints {super_class.constraints}\n")
    #         else:
    #             if "Subclass Of" not in super_classes_dict:
    #                 super_classes_dict["Subclass Of"] = []
                
    #             super_classes_dict["Subclass Of"].append(f"{_create_link(_normalize_class_name(super_class))}\n")
            
    #         # Sort the super classes by key so that they print alphabetically in the output file
    #         super_classes_dict = dict(sorted(super_classes_dict.items()))

        # properties : set[PropertyClass] = onto_class.get_class_properties()
        # has_definition = False
        # print("Properties:")
        # for prop in properties:
        #     if prop == definition_property:
        #         has_definition = True
            
        #     if getattr(prop, "label", None):
        #         print(f"Property : {prop} : {prop.label.first() or prop.name}")
        #     else:
        #         print(f"Property : {prop}")
        
        # if has_definition:
        #     print(f"Definition : {getattr(onto_class, definition_property.name, "Could not find definition")}")
        # else: # Fallback to default rdfs comment
        #     print(f"Comment : {onto_class.comment}")
        
        # with open(f"output/{class_name_normed}.md", "w") as file:
        #     # Properties block
        #     # Include alias if different than pretty name
        #     if class_name_normed != _normalize_class_name(onto_class.name):
        #         file.write("---\n")
        #         file.write("aliases:\n")
        #         file.write(f"  - {onto_class.name}\n")
        #         file.write("ontologytype: Class\n")
        #         file.write("---\n")
            
        #     # Turn the super classes into headers
        #     for k, v in super_classes_dict.items():
        #         file.write(f"# {k}:\n")
        #         file.writelines(v)
        #         file.write("\n")
            
    
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
    # print(onto.search_one(label = "entity").label)