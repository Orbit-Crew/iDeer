# Document Reader Tool

Extracts text from office documents and converts them to Markdown for agent consumption.

## Supported Formats

- PDF (`.pdf`) -- with optional page-range selection via pymupdf4llm
- Word (`.docx`, `.doc`)
- Excel (`.xlsx`, `.xls`)
- PowerPoint (`.pptx`, `.ppt`)

## Configuration

```yaml
tool_groups:
  - name: document

tools:
  - name: read_document
    group: document
    use: app.agentplatform.community.doc_reader.tools:read_document_tool
```

When upgrading an existing deployment, run `make config-upgrade` from the
repository root against the deployed configuration, then restart the backend
services. Set `DEER_FLOW_CONFIG_PATH` to the configuration file if it is outside
the default location. The upgrade migrates legacy `ideer.community.doc_reader.*`
paths even when `config_version` is already current. An import error suggesting
`uv add ideer` for this legacy path indicates stale configuration; installing an
`ideer` package does not migrate it.

## Usage

The tool accepts a `file_path` argument and an optional `page_range` (PDF only, e.g. `"1-5"` or `"1-3,7"`). Output is truncated to 50 000 characters by default.
