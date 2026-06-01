import typer


app = typer.Typer()


@app.callback()
def callback():
    """
    Obsidian OWL Importer
    """

# TODO The Typer parts need to be filled out once I have a better understanding of Owlready2
@app.command()
def load():
    """
    Import OWL ontology into Obsidian
    """
    typer.echo("Loading OWL ontology")