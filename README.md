# Obsidian OWL Importer
Imports OWL ontologies into Obsidian by treating them as sets of linked notes.

## Rationale
I have enjoyed using Obsidian for note-taking but found the process of linking parts of my notes to existing concepts that I have yet to document a bit tedious. This is especially the case for general "vocabulary" terms that I want linked so that I can see shared connections between my notes in the graph view. I thought that it would be nice to be able to jumpstart this process for a particular domain by importing a set of notes that already have appropriate connections established between them. New notes could then be inserted into this prepopulated knowledge graph by definining their connections to the existing notes. This does not eliminate the need to manually link my new notes or add new connections between existing notes as I see relevant, but it hopefully facilitates some initial setup.

## Limitations
The ontologies have rich definitions for connections that get somewhat lost when converting them to file links. Thinking of them as big graphs with labeled edges between topics, the conversion process essentially removes the labels and only shows the connections. I try to mitigate this by labeling headers in the notes, but there is probably still a loss of information and query potential.

I also am not duplicating properties to subclasses which could make querying harder but reduces complexity and file size. This may be revisited if I find that the omission limits my day-to-day use.

## Future Work
I chose to use OWL/XML as my input type, but a similar process could be used for importing other representations or even more general concept maps.

The text-based nature of Obsidian notes is also beneficial for potential application outside of Obsidian. The output of this tool is just Markdown files so its portability should be strong.