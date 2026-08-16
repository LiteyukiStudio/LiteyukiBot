//! The Cordis child executable bootstrap boundary.

use std::process::ExitCode;

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn main() -> ExitCode {
    if std::env::args_os().nth(1).as_deref() == Some(std::ffi::OsStr::new("--version")) {
        println!("liteyuki-cordis {VERSION}");
        return ExitCode::SUCCESS;
    }

    eprintln!(
        "liteyuki-cordis bootstrap unavailable: the LYIP v2 child transport is not implemented in this package-core slice"
    );
    ExitCode::from(78)
}
