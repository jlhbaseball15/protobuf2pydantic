from collections import defaultdict
from os import linesep
from typing import List, Set
from unittest import skip

from google.protobuf.descriptor import Descriptor, EnumDescriptor, FieldDescriptor
from google.protobuf.reflection import GeneratedProtocolMessageType

TAB = " " * 4
ONE_LINE, TWO_LINES = linesep * 2, linesep * 3

TYPE_MAPPING = {
    FieldDescriptor.TYPE_DOUBLE: float,
    FieldDescriptor.TYPE_FLOAT: float,
    FieldDescriptor.TYPE_INT64: int,
    FieldDescriptor.TYPE_UINT64: int,
    FieldDescriptor.TYPE_INT32: int,
    FieldDescriptor.TYPE_FIXED64: float,
    FieldDescriptor.TYPE_FIXED32: float,
    FieldDescriptor.TYPE_BOOL: bool,
    FieldDescriptor.TYPE_STRING: str,
    FieldDescriptor.TYPE_BYTES: str,
    FieldDescriptor.TYPE_UINT32: int,
    FieldDescriptor.TYPE_SFIXED32: float,
    FieldDescriptor.TYPE_SFIXED64: float,
    FieldDescriptor.TYPE_SINT32: int,
    FieldDescriptor.TYPE_SINT64: int,
}


def get_python_type(field: FieldDescriptor) -> str:
    """Returns the python type for a field .

    Args:
        field (FieldDescriptor): protobuf field descriptor

    Returns:
        str: name of the python type
    """
    return TYPE_MAPPING[field.type].__name__


def convert_field(field: FieldDescriptor, level: int, class_names: Set[str],
                  class_name_prefix: str) -> str:
    """Convert a field into a pydantic representation.

    Args:
        field (FieldDescriptor): protobuf field descriptor
        level (int): level of indentation
        class_names (Set[str]): current set of class_names
        class_name_prefix (str): prefix for the current class if nested classes are necessary

    Returns:
        str: pydantic model class code
    """
    level += 1
    field_type = field.type
    field_label = field.label
    extra = None

    if field_type == FieldDescriptor.TYPE_ENUM:
        enum_type: EnumDescriptor = field.enum_type
        type_statement = enum_type.name
        class_statement = f"{TAB * level}class {enum_type.name}(IntEnum):"
        field_statements = map(
            lambda value: f"{TAB * (level + 1)}{value.name} = {value.index}",
            enum_type.values,
        )
        extra = linesep.join([class_statement, *field_statements])
        factory = "int"
    elif field_type == FieldDescriptor.TYPE_MESSAGE:
        type_statement: str = field.message_type.name
        if type_statement.endswith("Entry"):
            key, value = field.message_type.fields
            type_statement = f"Dict[{get_python_type(key)}, {get_python_type(value)}]"
            factory = "dict"
        elif type_statement == "Struct":
            type_statement = "Dict[str, Any]"
            factory = "dict"
        else:
            if field.message_type.name not in class_names:
                extra = msg2pydantic(level, field.message_type, class_names,
                                     class_name_prefix)
            factory = type_statement
    else:
        type_statement = get_python_type(field)
        factory = type_statement

    if field_label == FieldDescriptor.LABEL_REPEATED:
        type_statement = f"List[{type_statement}]"
        factory = "list"

    default_statement = f" = Field(default_factory={factory})"
    if field_label == FieldDescriptor.LABEL_REQUIRED:
        default_statement = ""

    field_statement = f"{TAB * level}{field.name}: {type_statement}{default_statement}"
    if not extra:
        return field_statement
    return linesep + extra + ONE_LINE + field_statement


def msg2pydantic(level: int,
                 msg: Descriptor,
                 class_names: Set[str],
                 class_name_prefix: str = "",
                 skip_name_check: bool = False) -> str:
    prefixed_class_name = f"{class_name_prefix}{msg.name}"
    if prefixed_class_name in class_names and not skip_name_check:
        return ""
    class_names.add(prefixed_class_name)

    class_statement = f"{TAB * level}class {msg.name}(BaseModel):"
    field_statements = [
        convert_field(field, level, class_names, f"{prefixed_class_name}-")
        for field in msg.fields
    ]
    return linesep.join([class_statement, *field_statements])


def get_config(level: int):
    level += 1
    class_statement = f"{TAB * level}class Config:"
    attribute_statement = f"{TAB * (level + 1)}arbitrary_types_allowed = True"
    return linesep + class_statement + linesep + attribute_statement


# TODO: add class dependency tracking to define classes in the right order


def pb2_to_pydantic(module) -> str:
    pydantic_models: List[str] = []
    class_names: Set[str] = set()

    descriptors = [
        getattr(module, m).DESCRIPTOR for m in dir(module)
        if isinstance(getattr(module, m), GeneratedProtocolMessageType)
    ]

    class_names.update(d.name for d in descriptors)

    pydantic_models = [
        msg2pydantic(0, descriptor, class_names, skip_name_check=True)
        for descriptor in descriptors
    ]
    pydantic_models = [m for m in pydantic_models if m != ""]

    header = """from typing import List, Dict, Any
from enum import IntEnum

from pydantic import BaseModel, Field


"""
    return header + TWO_LINES.join(pydantic_models)
