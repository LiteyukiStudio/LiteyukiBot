//! Closed, first-party Cordis catcher planning.
//!
//! This crate owns no socket, runtime process management, or extension ABI.
//! Its PyO3 surface accepts and returns JSON strings so the Python kernel can
//! keep the cross-process contract protocol-neutral and JSON-safe.

use std::collections::{BTreeMap, BTreeSet};

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

const MAX_ACTIONS: usize = 8;

#[derive(Clone, Copy)]
struct Catcher {
    id: &'static str,
    dependencies: &'static [&'static str],
    match_text: &'static str,
    reply_text: &'static str,
    continue_after_match: bool,
}

const CATCHERS: &[Catcher] = &[
    Catcher {
        id: "core.greeting",
        dependencies: &[],
        match_text: "hello",
        reply_text: "Hello from Cordis.",
        continue_after_match: true,
    },
    Catcher {
        id: "core.help",
        dependencies: &["core.greeting"],
        match_text: "/cordis help",
        reply_text: "Cordis accepts its built-in exact commands.",
        continue_after_match: true,
    },
    Catcher {
        id: "core.status",
        dependencies: &["core.help"],
        match_text: "/cordis status",
        reply_text: "Cordis is ready.",
        continue_after_match: false,
    },
];

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct RuntimeConfig {
    enabled: Vec<String>,
    overrides: BTreeMap<String, CatcherOverride>,
}

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct CatcherOverride {
    match_text: Option<String>,
    reply_text: Option<String>,
}

#[derive(Serialize)]
struct EffectiveCatcher<'a> {
    id: &'a str,
    dependencies: &'a [&'a str],
    match_text: String,
    reply_text: String,
    #[serde(rename = "continue")]
    continue_after_match: bool,
}

#[derive(Serialize)]
struct ActionPlan {
    delivery_id: String,
    max_actions: usize,
    actions: Vec<PlannedAction>,
}

#[derive(Serialize)]
struct PlannedAction {
    catcher_id: String,
    correlation_id: String,
    #[serde(rename = "type")]
    action_type: &'static str,
    payload: SendMessagePayload,
    #[serde(rename = "continue")]
    continue_after_match: bool,
}

#[derive(Serialize)]
struct SendMessagePayload {
    text: String,
}

fn manifest() -> Result<Vec<&'static Catcher>, String> {
    let by_id: BTreeMap<_, _> = CATCHERS.iter().map(|catcher| (catcher.id, catcher)).collect();
    if by_id.len() != CATCHERS.len() {
        return Err("Cordis built-in manifest contains duplicate catcher IDs".to_owned());
    }

    for catcher in CATCHERS {
        for dependency in catcher.dependencies {
            if !by_id.contains_key(dependency) {
                return Err(format!(
                    "Cordis built-in manifest has missing dependency {dependency:?} for {:?}",
                    catcher.id
                ));
            }
        }
    }

    fn visit(
        id: &'static str,
        by_id: &BTreeMap<&'static str, &'static Catcher>,
        visiting: &mut BTreeSet<&'static str>,
        visited: &mut BTreeSet<&'static str>,
    ) -> Result<(), String> {
        if visited.contains(id) {
            return Ok(());
        }
        if !visiting.insert(id) {
            return Err(format!("Cordis built-in manifest has dependency cycle at {id:?}"));
        }
        let catcher = by_id[id];
        for dependency in catcher.dependencies {
            visit(dependency, by_id, visiting, visited)?;
        }
        visiting.remove(id);
        visited.insert(id);
        Ok(())
    }

    let mut visiting = BTreeSet::new();
    let mut visited = BTreeSet::new();
    for catcher in CATCHERS {
        visit(catcher.id, &by_id, &mut visiting, &mut visited)?;
    }
    Ok(CATCHERS.iter().collect())
}

fn effective_config(raw: &str) -> Result<Vec<EffectiveCatcher<'static>>, String> {
    let config: RuntimeConfig = serde_json::from_str(raw)
        .map_err(|error| format!("Cordis configuration must be a valid closed JSON object: {error}"))?;
    let catchers = manifest()?;
    let by_id: BTreeMap<_, _> = catchers.iter().map(|catcher| (catcher.id, *catcher)).collect();

    let mut enabled = BTreeSet::new();
    for id in &config.enabled {
        if !enabled.insert(id.as_str()) {
            return Err(format!("Cordis configuration enables catcher {id:?} more than once"));
        }
        if !by_id.contains_key(id.as_str()) {
            return Err(format!("Cordis configuration enables unknown catcher {id:?}"));
        }
    }
    for id in config.overrides.keys() {
        if !enabled.contains(id.as_str()) {
            return Err(format!("Cordis configuration overrides non-enabled catcher {id:?}"));
        }
        if !by_id.contains_key(id.as_str()) {
            return Err(format!("Cordis configuration overrides unknown catcher {id:?}"));
        }
    }
    for id in &enabled {
        let catcher = by_id[*id];
        for dependency in catcher.dependencies {
            if !enabled.contains(dependency) {
                return Err(format!(
                    "Cordis configuration enables {id:?} without required dependency {dependency:?}"
                ));
            }
        }
    }

    let mut effective = Vec::new();
    for catcher in catchers {
        if !enabled.contains(catcher.id) {
            continue;
        }
        let override_value = config.overrides.get(catcher.id);
        let match_text = non_empty_override(
            override_value.and_then(|value| value.match_text.as_deref()),
            catcher.match_text,
            catcher.id,
            "match_text",
        )?;
        let reply_text = non_empty_override(
            override_value.and_then(|value| value.reply_text.as_deref()),
            catcher.reply_text,
            catcher.id,
            "reply_text",
        )?;
        effective.push(EffectiveCatcher {
            id: catcher.id,
            dependencies: catcher.dependencies,
            match_text,
            reply_text,
            continue_after_match: catcher.continue_after_match,
        });
    }
    Ok(effective)
}

fn non_empty_override(
    value: Option<&str>,
    default: &str,
    catcher_id: &str,
    field: &str,
) -> Result<String, String> {
    match value {
        Some(value) if value.trim().is_empty() => Err(format!(
            "Cordis override {field:?} for catcher {catcher_id:?} must be non-empty"
        )),
        Some(value) => Ok(value.to_owned()),
        None => Ok(default.to_owned()),
    }
}

fn correlation_id(delivery_id: &str, catcher_id: &str) -> String {
    let mut digest = Sha256::new();
    digest.update(b"liteyuki-cordis-v1\0");
    digest.update(delivery_id.as_bytes());
    digest.update([0]);
    digest.update(catcher_id.as_bytes());
    format!("cordis:{}", hex::encode(&digest.finalize()[..16]))
}

#[pyfunction]
fn builtin_catchers_json() -> PyResult<String> {
    let catchers = manifest().map_err(PyValueError::new_err)?;
    let value = catchers
        .into_iter()
        .map(|catcher| {
            let mut item = Map::new();
            item.insert("id".to_owned(), Value::String(catcher.id.to_owned()));
            item.insert(
                "dependencies".to_owned(),
                Value::Array(
                    catcher
                        .dependencies
                        .iter()
                        .map(|dependency| Value::String((*dependency).to_owned()))
                        .collect(),
                ),
            );
            item.insert("match_text".to_owned(), Value::String(catcher.match_text.to_owned()));
            item.insert("reply_text".to_owned(), Value::String(catcher.reply_text.to_owned()));
            item.insert(
                "continue".to_owned(),
                Value::Bool(catcher.continue_after_match),
            );
            Value::Object(item)
        })
        .collect::<Vec<_>>();
    serde_json::to_string(&value).map_err(|error| PyValueError::new_err(error.to_string()))
}

#[pyfunction]
fn validate_config_json(config_json: &str) -> PyResult<String> {
    let effective = effective_config(config_json).map_err(PyValueError::new_err)?;
    serde_json::to_string(&effective).map_err(|error| PyValueError::new_err(error.to_string()))
}

#[pyfunction]
fn plan_actions_json(delivery_id: &str, text: &str, config_json: &str) -> PyResult<String> {
    if delivery_id.trim().is_empty() {
        return Err(PyValueError::new_err("Cordis delivery_id must be non-empty"));
    }
    let mut actions = Vec::new();
    for catcher in effective_config(config_json).map_err(PyValueError::new_err)? {
        if catcher.match_text != text {
            continue;
        }
        if actions.len() == MAX_ACTIONS {
            return Err(PyValueError::new_err("Cordis action plan exceeds max_actions=8"));
        }
        actions.push(PlannedAction {
            catcher_id: catcher.id.to_owned(),
            correlation_id: correlation_id(delivery_id, catcher.id),
            action_type: "SendMessage",
            payload: SendMessagePayload {
                text: catcher.reply_text,
            },
            continue_after_match: catcher.continue_after_match,
        });
        if !catcher.continue_after_match {
            break;
        }
    }
    serde_json::to_string(&ActionPlan {
        delivery_id: delivery_id.to_owned(),
        max_actions: MAX_ACTIONS,
        actions,
    })
    .map_err(|error| PyValueError::new_err(error.to_string()))
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(builtin_catchers_json, module)?)?;
    module.add_function(wrap_pyfunction!(validate_config_json, module)?)?;
    module.add_function(wrap_pyfunction!(plan_actions_json, module)?)?;
    Ok(())
}
