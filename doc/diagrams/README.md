# Diagrams

UML sumber PlantUML dijana oleh `omh codegraph uml` (codebase_uml/v1) —
package view (`codebase.puml`) dan module view (`modules.puml`).

Render semula (perlu `java` + plantuml.jar):

```bat
java -jar plantuml.jar -tpng codebase.puml modules.puml
```

PNG TIDAK disimpan dalam repo: `tools/make_source_zip.py` menolak fail
binary (keselamatan source zip). Hasil render simpan di luar repo.
