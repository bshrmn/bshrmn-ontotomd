from typing import Any

import typer
from rich import print
from rich.console import Console
from rich.table import Table
from typer_config.callbacks import conf_callback_factory
from typer_config.decorators import use_config
from typer_config.loaders import yaml_loader
from typing_extensions import Annotated

from bshrmn_ontotomd import (
    GlobalParamsConfig,
    OTMProcessSummary,
    PreloadConfig,
    ProcessConfig,
    preload_ontos,
    process_onto,
)


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

console = Console()
app = typer.Typer(
    no_args_is_help=True,
    help="A CLI tool for converting ontology graphs into Markdown directories.",
)


def global_params_parser(data: dict[str, Any]) -> dict[str, Any]:
    return GlobalParamsConfig(**data)


def preload_parser(data: dict[str, Any]) -> dict[str, Any]:
    return PreloadConfig(**data)


def process_parser(data: dict[str, Any]) -> dict[str, Any]:
    return ProcessConfig(**data)


@app.command()
@use_config(preload_validator_callback)
def preload(
    global_params: Annotated[
        GlobalParamsConfig, typer.Argument(parser=global_params_parser, hidden=True)
    ],
    preload: Annotated[
        PreloadConfig, typer.Argument(parser=preload_parser, hidden=True)
    ],
):
    """
    Preload ontology files locally based on default list and user configurations.

    Specify configuration in a YAML file and pass it with the --config option!
    """
    print("Preload script starting")
    command_result = preload_ontos(global_params, preload)
    # NOTE: Currently unused failure path
    if command_result.error_message:
        print(f"Finished with exception: {command_result.error_message}")
    else:
        print(f"Finished preloading {command_result.result} namespaces")


@app.command()
@use_config(process_validator_callback)
def process(
    global_params: Annotated[
        GlobalParamsConfig, typer.Argument(parser=global_params_parser, hidden=True)
    ],
    process: Annotated[
        ProcessConfig, typer.Argument(parser=process_parser, hidden=True)
    ],
):
    """
    Process target ontology by creating directories of Markdown files from its resource graph.

    Specify configuration in a YAML file and pass it with the --config option!
    """
    print("Process script starting")
    command_result = process_onto(global_params, process)
    if command_result.error_message:
        print(f"Finished with exception: {command_result.error_message}")
    else:
        print("Finished processing resources")

        summary: OTMProcessSummary = command_result.result
        table = Table("Name", "Count", title="Run Summary")
        table.add_row("Classes Found in Primary Onto", str(summary.primary_class_count))
        table.add_row(
            "Individuals Found in Primary Onto", str(summary.primary_individual_count)
        )
        table.add_row(
            "Properties Found in Primary Onto", str(summary.primary_property_count)
        )
        table.add_row(
            "Resources Skipped in Primary Onto", str(summary.primary_skipped_count)
        )
        table.add_row(
            "Stubbed Resources Found in Primary Onto", str(summary.stubbed_count)
        )
        table.add_row(
            "Processed External Resources", str(summary.external_processed_count)
        )
        table.add_row("Skipped External Resources", str(summary.external_skipped_count))
        console.print(table)


# In case I want to call the script directly
if __name__ == "__main__":
    app()
