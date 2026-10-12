//! The crate's error type.

/// Errors raised while parsing, converting, or persisting transcripts.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    /// A name that doesn't correspond to any implemented harness.
    #[error("unknown harness `{0}`")]
    UnknownHarness(String),

    /// A native record was structurally invalid or missing a required field.
    #[error("malformed {harness} transcript: {detail}")]
    Malformed {
        harness: &'static str,
        detail: String,
    },

    /// A conversion couldn't represent something in the target.
    #[error("cannot convert to {harness}: {detail}")]
    Unconvertible {
        harness: &'static str,
        detail: String,
    },

    /// A live harness backend rejected a request or changed its protocol.
    #[error("{harness} remote access failed: {detail}")]
    Remote {
        harness: &'static str,
        detail: String,
    },

    /// Underlying I/O failure (reading a session file, writing a rollout).
    #[error(transparent)]
    Io(#[from] std::io::Error),

    /// JSON (de)serialization failure.
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, Error>;
