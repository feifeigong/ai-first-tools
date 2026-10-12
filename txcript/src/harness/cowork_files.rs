//! Explicit Cowork attachment carriers. Ordinary tool paths are not attachments.
use crate::common::{Artifact, ArtifactSource};
use crate::{Error, Result};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub(super) struct FileRef {
    pub key: String,
    pub name: String,
    pub path: Option<String>,
    pub uuid: Option<String>,
}

// Keep the observed attachment shapes together for review.
#[allow(clippy::too_many_lines)]
pub(super) fn references(payload: &Value) -> Vec<FileRef> {
    let mut files = BTreeMap::new();
    let mut add_path = |path: &str, name: Option<&str>| {
        let path = path.strip_prefix("computer://").unwrap_or(path);
        if path.is_empty() {
            return;
        }
        let name = name
            .filter(|name| !name.is_empty())
            .unwrap_or_else(|| path.rsplit(['/', '\\']).next().unwrap_or("file"));
        files.insert(
            format!("path:{path}"),
            FileRef {
                key: format!("path:{path}"),
                name: name.to_string(),
                path: Some(path.into()),
                uuid: None,
            },
        );
    };
    if let Some(blocks) = payload
        .pointer("/message/content")
        .and_then(Value::as_array)
    {
        for block in blocks {
            if block["type"] == "tool_use" {
                let name = block["name"].as_str().unwrap_or_default();
                let input = &block["input"];
                if matches!(name, "Artifact" | "SendUserFile") {
                    if let Some(path) = input["file_path"]
                        .as_str()
                        .or_else(|| input["path"].as_str())
                    {
                        add_path(path, None);
                    }
                } else if name == "present_files" || name.ends_with("__present_files") {
                    for path in input["filepaths"]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .filter_map(Value::as_str)
                    {
                        add_path(path, None);
                    }
                }
            }
        }
    }
    // The app prefixes the user prompt with its attachment manifest. Never
    // scan arbitrary prose, shell commands, or Read/Write tool arguments.
    let content = payload.pointer("/message/content");
    let texts: Vec<&str> = match content {
        Some(Value::String(text)) => vec![text],
        Some(Value::Array(blocks)) => blocks
            .iter()
            .filter(|b| b["type"] == "text")
            .filter_map(|b| b["text"].as_str())
            .collect(),
        _ => Vec::new(),
    };
    for text in texts {
        if let Some(manifest) =
            text.trim_start()
                .strip_prefix("<uploaded_files>")
                .and_then(|text| {
                    text.split_once("</uploaded_files>")
                        .map(|(manifest, _)| manifest)
                })
        {
            for tail in manifest.split("<file_path>").skip(1) {
                if let Some((path, _)) = tail.split_once("</file_path>") {
                    add_path(path.trim(), None);
                }
            }
        }
    }
    for file in payload["file_attachments"].as_array().into_iter().flatten() {
        // Images already have their exact bytes in SDK image blocks.
        if file["is_image"] == true {
            continue;
        }
        if let (Some(uuid), Some(name)) = (file["file_uuid"].as_str(), file["file_name"].as_str()) {
            let key = format!("file:{uuid}");
            files.insert(
                key.clone(),
                FileRef {
                    key,
                    name: name.into(),
                    uuid: Some(uuid.into()),
                    path: None,
                },
            );
        }
    }
    let values: Vec<_> = files.into_values().collect();
    values
        .iter()
        .filter(|file| {
            !file.path.as_deref().is_some_and(|path| {
                values.iter().any(|other| {
                    other.key != file.key
                        && other.name == file.name
                        && (other.uuid.is_some()
                            || (!path.contains(['/', '\\'])
                                && other
                                    .path
                                    .as_deref()
                                    .is_some_and(|path| path.contains(['/', '\\']))))
                })
            })
        })
        .cloned()
        .collect()
}

pub(super) fn attach(payload: &mut Value, files: &BTreeMap<String, Artifact>) -> Result<()> {
    let refs = references(payload);
    if refs.is_empty() {
        return Ok(());
    }
    let mut blocks = match payload.pointer("/message/content") {
        Some(Value::Array(blocks)) => blocks.clone(),
        Some(Value::String(text)) => vec![serde_json::json!({"type":"text","text":text})],
        _ => Vec::new(),
    };
    for file in refs {
        let Some(artifact) = files.get(&file.key) else {
            continue;
        };
        let (kind, data, media_type) = match &artifact.source {
            ArtifactSource::Text { text, media_type } => ("text", text, media_type),
            ArtifactSource::Base64 { data, media_type } => ("base64", data, media_type),
            ArtifactSource::Path { .. } => return Err(error("hydrated file contains a host path")),
        };
        let document = serde_json::json!({"type":"document","id":artifact.id,"title":artifact.name,
            "source":{"type":kind,"data":data,"media_type":media_type}});
        if let Some(block) = blocks.iter_mut().find(|block| {
            block["type"] == "tool_use"
                && block["name"] == "Artifact"
                && block.pointer("/input/file_path").and_then(Value::as_str) == file.path.as_deref()
        }) {
            *block = document;
        } else {
            blocks.push(document);
        }
    }
    payload["message"]["content"] = Value::Array(blocks);
    Ok(())
}

pub(super) fn error(detail: &str) -> Error {
    Error::Malformed {
        harness: "cowork",
        detail: detail.into(),
    }
}

/// A fallback for local cache files, whose attachment manifests omit MIME types.
pub(super) fn media_type(name: &str) -> Option<&'static str> {
    let extension = std::path::Path::new(name)
        .extension()?
        .to_str()?
        .to_ascii_lowercase();
    Some(match extension.as_str() {
        "pdf" => "application/pdf",
        "xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx" => "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx" => "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "csv" => "text/csv",
        "md" => "text/markdown",
        "txt" => "text/plain",
        "json" => "application/json",
        "html" => "text/html",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    #[test]
    fn relocated_windows_attachment_replaces_the_old_manifest_name() {
        let payload = serde_json::json!({"message":{"content":[
            {"type":"text","text":"<uploaded_files><file_path>terms.pdf</file_path></uploaded_files>"},
            {"type":"tool_use","name":"Artifact","input":{"file_path":r"C:\Users\test\uploads\copy\terms.pdf"}}
        ]}});
        let files = super::references(&payload);
        assert_eq!(files.len(), 1);
        assert_eq!(files[0].name, "terms.pdf");
        assert!(
            files[0]
                .path
                .as_ref()
                .is_some_and(|path| path.starts_with("C:"))
        );
    }

    #[test]
    fn uploaded_manifest_and_file_id_are_one_attachment() {
        let payload = serde_json::json!({
            "type":"user", "message":{"content":"<uploaded_files><file><file_path>terms.pdf</file_path></file></uploaded_files>Read this"},
            "file_attachments":[{"file_uuid":"file-id","file_name":"terms.pdf","is_image":false}]
        });
        let files = super::references(&payload);
        assert_eq!(files.len(), 1);
        assert_eq!(files[0].uuid.as_deref(), Some("file-id"));
    }
}
