from typing import Any
from typing_extensions import Annotated
from typer_config.loaders import yaml_loader
from typer_config.callbacks import conf_callback_factory
import typer
from typer_config.decorators import use_config
from bshrmn_obsidian_owl_importer import GlobalParamsConfig, PreloadConfig, ProcessConfig, preload_ontos

def global_params_validator_loader(param_value: str) -> dict[str, Any]:
    yaml_conf = yaml_loader(param_value)
    global_params_conf = yaml_conf["global_params"]
    PreloadConfig.model_validate(global_params_conf)  # raises an exception if not valid
    return global_params_conf

def preload_validator_loader(param_value: str) -> dict[str, Any]:
    yaml_conf = yaml_loader(param_value)
    global_params_conf = yaml_conf["global_params"]
    PreloadConfig.model_validate(global_params_conf)  # raises an exception if not valid
    preload_conf = yaml_conf["preload"]
    PreloadConfig.model_validate(preload_conf)  # raises an exception if not valid
    return {"global_params": global_params_conf, "preload": preload_conf}

def process_validator_loader(param_value: str) -> dict[str, Any]:
    yaml_conf = yaml_loader(param_value)
    global_params_conf = yaml_conf["global_params"]
    PreloadConfig.model_validate(global_params_conf)  # raises an exception if not valid
    process_conf = yaml_conf["process"]
    PreloadConfig.model_validate(process_conf)  # raises an exception if not valid
    return {"global_params": global_params_conf, "process": process_conf}

global_params_validator_callback = conf_callback_factory(global_params_validator_loader)
preload_validator_callback = conf_callback_factory(preload_validator_loader)
process_validator_callback = conf_callback_factory(process_validator_loader)

app = typer.Typer()

def global_params_parser(data: dict[str, Any]) -> dict[str, Any]:
    return GlobalParamsConfig(**data)

def preload_parser(data: dict[str, Any]) -> dict[str, Any]:
    return PreloadConfig(**data)

def process_parser(data: dict[str, Any]) -> dict[str, Any]:
    return ProcessConfig(**data)

@app.command()
@use_config(preload_validator_callback)
def preload(
    global_params: Annotated[GlobalParamsConfig, typer.Argument(parser=global_params_parser, hidden=True)],
    preload: Annotated[PreloadConfig, typer.Argument(parser=preload_parser, hidden=True)],
):
    """
    Sample text TODO
    """
    typer.echo("Preload script starting")
    total_preloads = preload_ontos(global_params, preload)
    typer.echo(f"Finished preloading {total_preloads} namespaces")

@app.command()
@use_config(process_validator_callback)
def process(
    global_params: Annotated[GlobalParamsConfig, typer.Argument(parser=global_params_parser, hidden=True)],
    process: Annotated[ProcessConfig, typer.Argument(parser=process_parser, hidden=True)],
):
    """
    Sample text TODO
    """
    typer.echo(global_params)
    typer.echo(f"Log Level: {global_params.logging_params.logging_level}")
    typer.echo(f"Onto Dir: {global_params.ontologies_directory.resolve()} | Exists: {global_params.ontologies_directory.exists()}")
    typer.echo(f"Out Dir: {global_params.output_directory.resolve()} | Exists: {global_params.output_directory.exists()}")
    typer.echo(process)
    typer.echo(f"Target: {process.target.resolve()} | Exists: {process.target.exists()}")

if __name__ == "__main__":
    app()