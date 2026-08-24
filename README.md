# OntoToMd
A CLI tool for parsing ontologies into directories of Markdown files by mapping their resource graphs using Markdown links between files.

## Rationale
I have enjoyed using Obsidian for note-taking but found the process of linking parts of my notes to existing concepts that I have yet to document a bit tedious. This is especially the case for general "vocabulary" terms that I want linked so that I can see shared connections between my notes in the graph view. I thought that it would be nice to be able to jumpstart this process for a particular domain by importing a set of notes that already have appropriate connections established between them. New notes could then be inserted into this prepopulated knowledge graph by definining their connections to the existing notes. This does not eliminate the need to manually link my new notes or add new connections between existing notes as I see relevant, but it hopefully facilitates some initial setup.

## Limitations
The ontologies have rich definitions for connections that get somewhat lost when converting them to Markdown links. Thinking of them as big graphs with labeled edges between resources, the conversion process essentially removes the labels and only shows the connections. I try to mitigate this by providing context around links in the notes, but there is still a loss of information and query potential.

I am not implementing all the features of RDF or OWL at this time. The coverage of those specifications may increase in the future if I find it desirable, but the primary goal is minimal usability for my knowledge base. Features enabling reasoners are especially unlikely to have support.

## Future Work
I chose to focus on OWL/XML ontologies as my input, but a similar process could be used for importing other representations or even more general concept maps.

This tool was designed with Obsidian notes in mind, but it could still be useful outside of that use case. The output is primarily Markdown files so its portability should be strong minus some opinionated choices such as link style.