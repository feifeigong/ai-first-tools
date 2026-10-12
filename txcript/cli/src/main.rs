//! The `txcript` binary: the library's command line plus `init`, the shell
//! integration. The library's [`txcript_cli::Cli`] is mounted as is into other
//! binaries, so what only this one offers is composed here, the same way.
//!
//! ```text
//! txcript init <zsh|bash>               # print the shell integration; add
//!                                       #   eval "$(txcript init zsh)" to your rc
//! ```

use clap::{CommandFactory, Parser, Subcommand};

/// The `txcript` command line: the library's commands plus the binary's own.
#[derive(Parser)]
#[command(
    name = "txcript",
    version,
    about = "List, search, and continue local AI coding sessions in any harness",
    after_help = txcript_cli::HARNESSES
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
    /// Keep a persistent search cache at this path, so `query` (and the MCP
    /// search tool) re-read only the sessions that changed since the last
    /// run. Without it every run parses every session afresh.
    #[arg(
        long,
        global = true,
        env = "TXCRIPT_CACHE",
        value_name = "PATH",
        value_hint = clap::ValueHint::FilePath
    )]
    cache: Option<std::path::PathBuf>,
}

#[derive(Subcommand)]
enum Command {
    /// The library's commands, mounted as this binary's. Maintained there.
    #[command(flatten)]
    Lib(txcript_cli::Command),
    /// Print the shell integration (add `eval "$(txcript init zsh)"` to your shell config)
    ///
    /// Completions, plus ctrl+shift+r to pick a session recorded in the
    /// current folder.
    Init {
        #[arg(value_enum)]
        shell: Shell,
    },
}

/// Shells `init` integrates with.
#[derive(Clone, Copy, clap::ValueEnum)]
enum Shell {
    Zsh,
    Bash,
}

fn main() -> std::process::ExitCode {
    let cli = Cli::parse();
    let command = match cli.command {
        Command::Init { shell } => {
            // A failed stdout write means the reader is gone (`… | head`);
            // end quietly.
            let _ = std::io::Write::write_all(&mut std::io::stdout(), &shell_init(shell));
            return std::process::ExitCode::SUCCESS;
        }
        // Completions come from this binary's command line, so `init`
        // completes too; the library only knows its own.
        Command::Lib(txcript_cli::Command::Completion { shell }) => {
            let mut script = Vec::new();
            clap_complete::generate(shell, &mut Cli::command(), "txcript", &mut script);
            let _ = std::io::Write::write_all(&mut std::io::stdout(), &script);
            return std::process::ExitCode::SUCCESS;
        }
        Command::Lib(command) => command,
    };
    txcript_cli::run(txcript_cli::Cli {
        command,
        cache: cli.cache,
    })
}

/// The script `init` prints for `shell`: the completion script (guarded, in
/// zsh, on compinit having run), then the ctrl+shift+r session picker.
///
/// The picker snippets live in `cli/shell/` so they can be linted and
/// sourced as files. In legacy terminal encoding ctrl+shift+r and ctrl+r
/// send the same byte, so they enable the kitty keyboard protocol
/// (progressive enhancement flag 1, "disambiguate escape codes") only while
/// the line editor is reading, using the stateless `CSI = u` set form (the
/// same mechanism fish 4 uses). Ghostty, kitty, and `WezTerm` speak the
/// protocol; terminals that don't ignore the sequences, and ctrl+shift+r
/// degrades to plain ctrl+r.
fn shell_init(shell: Shell) -> Vec<u8> {
    let (completion_shell, guard, picker) = match shell {
        Shell::Zsh => (
            clap_complete::Shell::Zsh,
            Some(("if (( $+functions[compdef] )); then\n", "fi\n")),
            include_str!("../shell/init.zsh"),
        ),
        Shell::Bash => (
            clap_complete::Shell::Bash,
            None,
            include_str!("../shell/init.bash"),
        ),
    };
    let mut out = Vec::new();
    if let Some((open, _)) = guard {
        out.extend_from_slice(open.as_bytes());
    }
    clap_complete::generate(completion_shell, &mut Cli::command(), "txcript", &mut out);
    if let Some((_, close)) = guard {
        out.extend_from_slice(close.as_bytes());
    }
    out.extend_from_slice(b"\n");
    out.extend_from_slice(picker.as_bytes());
    out
}
