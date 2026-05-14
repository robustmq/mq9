/// Errors returned by the mq9 client.
///
/// `async_nats::Error` is a type alias for
/// `Box<dyn std::error::Error + Send + Sync + 'static>`, so the `#[from]`
/// impl covers all async-nats error kinds via `.map_err(|e| Mq9Error::Nats(Box::new(e)))`.
#[derive(Debug, thiserror::Error)]
pub enum Mq9Error {
    /// The broker returned a non-empty error string.
    #[error("server error: {0}")]
    Server(String),

    /// An error from the underlying async-nats transport.
    #[error("nats error: {0}")]
    Nats(#[from] async_nats::Error),

    /// A JSON serialisation/deserialisation error.
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),

    /// The client is not connected (reserved for future connection-state tracking).
    #[error("not connected")]
    NotConnected,
}

/// Convenience `Result` alias.
pub type Result<T> = std::result::Result<T, Mq9Error>;
