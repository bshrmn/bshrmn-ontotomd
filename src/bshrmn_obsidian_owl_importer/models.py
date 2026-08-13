from typing import Any, Optional, Union
from typing_extensions import Annotated
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, AnyUrl
from typer_config.loaders import yaml_loader
from typer_config.callbacks import conf_callback_factory
import typer
from typer_config.decorators import use_config

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class GlobalsConfig(BaseModel):
    log_level : LogLevel = "DEBUG"
    ontologies_directory : Path
    output_directory : Path

class PreloadConfig(BaseModel):
    targets : Optional[list[Union[Path, AnyUrl]]] = None
    overwrite_local_files : bool = True

class ProcessConfig(BaseModel):
    target : Union[Path, AnyUrl]
    target_namespace : str
    skippable_resources : Optional[list[Union[Path, AnyUrl]]] = None
    skippable_namespaces : Optional[list[Union[Path, AnyUrl]]] = None
    do_not_create_resources : Optional[list[Union[Path, AnyUrl]]] = None
    class_types : Optional[list[Union[Path, AnyUrl]]] = None
    individual_types : Optional[list[Union[Path, AnyUrl]]] = None
    property_types : Optional[list[Union[Path, AnyUrl]]] = None
    alias_properties : Optional[list[Union[Path, AnyUrl]]] = None
    description_properties : Optional[list[Union[Path, AnyUrl]]] = None
    external_link_properties : Optional[list[Union[Path, AnyUrl]]] = None

def globals_validator_loader(param_value: str) -> dict[str, Any]:
    yaml_conf = yaml_loader(param_value)
    globals_conf = yaml_conf["globals"]
    PreloadConfig.model_validate(globals_conf)  # raises an exception if not valid
    return globals_conf

def preload_validator_loader(param_value: str) -> dict[str, Any]:
    yaml_conf = yaml_loader(param_value)
    globals_conf = yaml_conf["globals"]
    PreloadConfig.model_validate(globals_conf)  # raises an exception if not valid
    preload_conf = yaml_conf["preload"]
    PreloadConfig.model_validate(preload_conf)  # raises an exception if not valid
    return {"globals": globals_conf, "preload": preload_conf}

def process_validator_loader(param_value: str) -> dict[str, Any]:
    yaml_conf = yaml_loader(param_value)
    globals_conf = yaml_conf["globals"]
    PreloadConfig.model_validate(globals_conf)  # raises an exception if not valid
    process_conf = yaml_conf["process"]
    PreloadConfig.model_validate(process_conf)  # raises an exception if not valid
    return {"globals": globals_conf, "process": process_conf}

globals_validator_callback = conf_callback_factory(globals_validator_loader)
preload_validator_callback = conf_callback_factory(preload_validator_loader)
process_validator_callback = conf_callback_factory(process_validator_loader)

app = typer.Typer()

def globals_parser(data: dict[str, Any]) -> dict[str, Any]:
    return GlobalsConfig(**data)

def preload_parser(data: dict[str, Any]) -> dict[str, Any]:
    return PreloadConfig(**data)

def process_parser(data: dict[str, Any]) -> dict[str, Any]:
    return ProcessConfig(**data)

@app.command()
@use_config(preload_validator_callback)
def preload(
    globals: Annotated[GlobalsConfig, typer.Argument(parser=globals_parser)],
    preload: Annotated[PreloadConfig, typer.Argument(parser=preload_parser)],
):
    """
    Sample text
    """
    typer.echo(globals)
    typer.echo(f"Onto Dir: {globals.ontologies_directory.resolve()} | Exists: {globals.ontologies_directory.exists()}")
    typer.echo(f"Out Dir: {globals.output_directory.resolve()} | Exists: {globals.output_directory.exists()}")
    typer.echo(preload)

@app.command()
@use_config(process_validator_callback)
def process(
    globals: Annotated[GlobalsConfig, typer.Argument(parser=globals_parser)],
    process: Annotated[ProcessConfig, typer.Argument(parser=process_parser)],
):
    """
    Sample text
    """
    typer.echo(globals)
    typer.echo(f"Onto Dir: {globals.ontologies_directory.resolve()} | Exists: {globals.ontologies_directory.exists()}")
    typer.echo(f"Out Dir: {globals.output_directory.resolve()} | Exists: {globals.output_directory.exists()}")
    typer.echo(process)
    typer.echo(f"Target: {process.target.resolve()} | Exists: {process.target.exists()}")

if __name__ == "__main__":
    app()