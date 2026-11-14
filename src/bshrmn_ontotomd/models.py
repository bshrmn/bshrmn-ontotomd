from enum import Enum
from pathlib import Path
from typing import Annotated, Optional, Union

from pydantic import AnyUrl, BaseModel, UrlConstraints


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LoggingParamsConfig(BaseModel):
    logging_level: LogLevel = "DEBUG"
    logging_file: Path = Path("onto-to-md.log")
    max_file_size: int = 1_000_000
    backup_count: int = 5


class GlobalParamsConfig(BaseModel):
    logging_params: LoggingParamsConfig
    ontologies_directory: Path
    output_directory: Path


class PreloadConfig(BaseModel):
    targets: Optional[list[Union[Path, AnyUrl]]] = None
    overwrite_local_files: bool = True


class ProcessConfig(BaseModel):
    target: Union[Path, AnyUrl]
    target_namespace: str
    skippable_resources: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    skippable_namespaces: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    do_not_create_resources: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    class_types: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    individual_types: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    property_types: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    alias_properties: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    description_properties: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
    external_link_properties: Optional[
        list[Annotated[AnyUrl, UrlConstraints(preserve_empty_path=True)]]
    ] = None
