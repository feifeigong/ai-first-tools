//! Inline images for `txcript view` over the kitty graphics protocol.
//!
//! The terminal is asked directly whether it speaks the protocol: a graphics
//! query followed by a primary device attributes request, so a terminal that
//! answers the second without the first has said no without a timeout.
//! Ghostty, kitty, `WezTerm`, and Konsole answer yes; everything else keeps the
//! `omitted` label.
//!
//! Each image is transmitted once, ahead of the pager, as a *virtual
//! placement*. The rendered view then carries Unicode placeholder cells —
//! U+10EEEE with the image id in the foreground color and row/column
//! diacritics — that the terminal paints the image over wherever they land.
//! To the pager they are ordinary colored text, so scrolling, searching, and
//! jumping in `less` need no cooperation from it beyond `-R`. `less` must
//! also be told the placeholder is printable (`LESSUTFCHARDEF`); the caller
//! sets that up.

use std::fmt::Write as _;
use std::io::Cursor;
use std::process::Command;

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64;
use flate2::Compression;
use flate2::write::ZlibEncoder;
use image::{ImageFormat, ImageReader};

/// Cell the terminal replaces with a slice of the referenced image.
const PLACEHOLDER: char = '\u{10EEEE}';

/// Combining characters that spell row and column numbers on placeholder
/// cells, in protocol order (kitty's `rowcolumn-diacritics.txt`).
const DIACRITICS: [char; 297] = [
    '\u{0305}',
    '\u{030D}',
    '\u{030E}',
    '\u{0310}',
    '\u{0312}',
    '\u{033D}',
    '\u{033E}',
    '\u{033F}',
    '\u{0346}',
    '\u{034A}',
    '\u{034B}',
    '\u{034C}',
    '\u{0350}',
    '\u{0351}',
    '\u{0352}',
    '\u{0357}',
    '\u{035B}',
    '\u{0363}',
    '\u{0364}',
    '\u{0365}',
    '\u{0366}',
    '\u{0367}',
    '\u{0368}',
    '\u{0369}',
    '\u{036A}',
    '\u{036B}',
    '\u{036C}',
    '\u{036D}',
    '\u{036E}',
    '\u{036F}',
    '\u{0483}',
    '\u{0484}',
    '\u{0485}',
    '\u{0486}',
    '\u{0487}',
    '\u{0592}',
    '\u{0593}',
    '\u{0594}',
    '\u{0595}',
    '\u{0597}',
    '\u{0598}',
    '\u{0599}',
    '\u{059C}',
    '\u{059D}',
    '\u{059E}',
    '\u{059F}',
    '\u{05A0}',
    '\u{05A1}',
    '\u{05A8}',
    '\u{05A9}',
    '\u{05AB}',
    '\u{05AC}',
    '\u{05AF}',
    '\u{05C4}',
    '\u{0610}',
    '\u{0611}',
    '\u{0612}',
    '\u{0613}',
    '\u{0614}',
    '\u{0615}',
    '\u{0616}',
    '\u{0617}',
    '\u{0657}',
    '\u{0658}',
    '\u{0659}',
    '\u{065A}',
    '\u{065B}',
    '\u{065D}',
    '\u{065E}',
    '\u{06D6}',
    '\u{06D7}',
    '\u{06D8}',
    '\u{06D9}',
    '\u{06DA}',
    '\u{06DB}',
    '\u{06DC}',
    '\u{06DF}',
    '\u{06E0}',
    '\u{06E1}',
    '\u{06E2}',
    '\u{06E4}',
    '\u{06E7}',
    '\u{06E8}',
    '\u{06EB}',
    '\u{06EC}',
    '\u{0730}',
    '\u{0732}',
    '\u{0733}',
    '\u{0735}',
    '\u{0736}',
    '\u{073A}',
    '\u{073D}',
    '\u{073F}',
    '\u{0740}',
    '\u{0741}',
    '\u{0743}',
    '\u{0745}',
    '\u{0747}',
    '\u{0749}',
    '\u{074A}',
    '\u{07EB}',
    '\u{07EC}',
    '\u{07ED}',
    '\u{07EE}',
    '\u{07EF}',
    '\u{07F0}',
    '\u{07F1}',
    '\u{07F3}',
    '\u{0816}',
    '\u{0817}',
    '\u{0818}',
    '\u{0819}',
    '\u{081B}',
    '\u{081C}',
    '\u{081D}',
    '\u{081E}',
    '\u{081F}',
    '\u{0820}',
    '\u{0821}',
    '\u{0822}',
    '\u{0823}',
    '\u{0825}',
    '\u{0826}',
    '\u{0827}',
    '\u{0829}',
    '\u{082A}',
    '\u{082B}',
    '\u{082C}',
    '\u{082D}',
    '\u{0951}',
    '\u{0953}',
    '\u{0954}',
    '\u{0F82}',
    '\u{0F83}',
    '\u{0F86}',
    '\u{0F87}',
    '\u{135D}',
    '\u{135E}',
    '\u{135F}',
    '\u{17DD}',
    '\u{193A}',
    '\u{1A17}',
    '\u{1A75}',
    '\u{1A76}',
    '\u{1A77}',
    '\u{1A78}',
    '\u{1A79}',
    '\u{1A7A}',
    '\u{1A7B}',
    '\u{1A7C}',
    '\u{1B6B}',
    '\u{1B6D}',
    '\u{1B6E}',
    '\u{1B6F}',
    '\u{1B70}',
    '\u{1B71}',
    '\u{1B72}',
    '\u{1B73}',
    '\u{1CD0}',
    '\u{1CD1}',
    '\u{1CD2}',
    '\u{1CDA}',
    '\u{1CDB}',
    '\u{1CE0}',
    '\u{1DC0}',
    '\u{1DC1}',
    '\u{1DC3}',
    '\u{1DC4}',
    '\u{1DC5}',
    '\u{1DC6}',
    '\u{1DC7}',
    '\u{1DC8}',
    '\u{1DC9}',
    '\u{1DCB}',
    '\u{1DCC}',
    '\u{1DD1}',
    '\u{1DD2}',
    '\u{1DD3}',
    '\u{1DD4}',
    '\u{1DD5}',
    '\u{1DD6}',
    '\u{1DD7}',
    '\u{1DD8}',
    '\u{1DD9}',
    '\u{1DDA}',
    '\u{1DDB}',
    '\u{1DDC}',
    '\u{1DDD}',
    '\u{1DDE}',
    '\u{1DDF}',
    '\u{1DE0}',
    '\u{1DE1}',
    '\u{1DE2}',
    '\u{1DE3}',
    '\u{1DE4}',
    '\u{1DE5}',
    '\u{1DE6}',
    '\u{1DFE}',
    '\u{20D0}',
    '\u{20D1}',
    '\u{20D4}',
    '\u{20D5}',
    '\u{20D6}',
    '\u{20D7}',
    '\u{20DB}',
    '\u{20DC}',
    '\u{20E1}',
    '\u{20E7}',
    '\u{20E9}',
    '\u{20F0}',
    '\u{2CEF}',
    '\u{2CF0}',
    '\u{2CF1}',
    '\u{2DE0}',
    '\u{2DE1}',
    '\u{2DE2}',
    '\u{2DE3}',
    '\u{2DE4}',
    '\u{2DE5}',
    '\u{2DE6}',
    '\u{2DE7}',
    '\u{2DE8}',
    '\u{2DE9}',
    '\u{2DEA}',
    '\u{2DEB}',
    '\u{2DEC}',
    '\u{2DED}',
    '\u{2DEE}',
    '\u{2DEF}',
    '\u{2DF0}',
    '\u{2DF1}',
    '\u{2DF2}',
    '\u{2DF3}',
    '\u{2DF4}',
    '\u{2DF5}',
    '\u{2DF6}',
    '\u{2DF7}',
    '\u{2DF8}',
    '\u{2DF9}',
    '\u{2DFA}',
    '\u{2DFB}',
    '\u{2DFC}',
    '\u{2DFD}',
    '\u{2DFE}',
    '\u{2DFF}',
    '\u{A66F}',
    '\u{A67C}',
    '\u{A67D}',
    '\u{A6F0}',
    '\u{A6F1}',
    '\u{A8E0}',
    '\u{A8E1}',
    '\u{A8E2}',
    '\u{A8E3}',
    '\u{A8E4}',
    '\u{A8E5}',
    '\u{A8E6}',
    '\u{A8E7}',
    '\u{A8E8}',
    '\u{A8E9}',
    '\u{A8EA}',
    '\u{A8EB}',
    '\u{A8EC}',
    '\u{A8ED}',
    '\u{A8EE}',
    '\u{A8EF}',
    '\u{A8F0}',
    '\u{A8F1}',
    '\u{AAB0}',
    '\u{AAB2}',
    '\u{AAB3}',
    '\u{AAB7}',
    '\u{AAB8}',
    '\u{AABE}',
    '\u{AABF}',
    '\u{AAC1}',
    '\u{FE20}',
    '\u{FE21}',
    '\u{FE22}',
    '\u{FE23}',
    '\u{FE24}',
    '\u{FE25}',
    '\u{FE26}',
    '\u{10A0F}',
    '\u{10A38}',
    '\u{1D185}',
    '\u{1D186}',
    '\u{1D187}',
    '\u{1D188}',
    '\u{1D189}',
    '\u{1D1AA}',
    '\u{1D1AB}',
    '\u{1D1AC}',
    '\u{1D1AD}',
    '\u{1D242}',
    '\u{1D243}',
    '\u{1D244}',
];

/// Largest row or column a placeholder can address.
const MAX_EXTENT: u16 = 297;
const _: () = assert!(DIACRITICS.len() == MAX_EXTENT as usize);

/// Base64 bytes per transmission chunk, the protocol's maximum.
const CHUNK: usize = 4096;

/// Images taller or wider than this are not decoded.
const MAX_PIXELS: u32 = 8192;

/// The first `less` release that honors `LESSUTFCHARDEF`.
const LESS_PLACEHOLDER_VERSION: u32 = 632;

/// Value of `LESSUTFCHARDEF` that keeps `less` from rendering the placeholder
/// as `<U+10EEEE>`; appended to any definitions the user already has.
#[must_use]
pub fn less_char_definitions(existing: Option<&str>) -> String {
    match existing.map(str::trim).filter(|value| !value.is_empty()) {
        Some(existing) => format!("{existing},10EEEE:p"),
        None => "10EEEE:p".to_string(),
    }
}

/// Whether the `less` at `program` is new enough to honor `LESSUTFCHARDEF`.
#[must_use]
pub fn less_supports_placeholders(program: &str) -> bool {
    Command::new(program)
        .arg("--version")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| less_version(&String::from_utf8_lossy(&output.stdout)))
        .is_some_and(|version| version >= LESS_PLACEHOLDER_VERSION)
}

/// The release number in the first line of `less --version`.
fn less_version(banner: &str) -> Option<u32> {
    let mut words = banner.lines().next()?.split_whitespace();
    if words.next()? != "less" {
        return None;
    }
    words.next()?.parse().ok()
}

/// Terminal geometry: the screen in cells and the size of one cell in pixels.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Cells {
    pub cell_width: u32,
    pub cell_height: u32,
    pub columns: u16,
    pub rows: u16,
}

/// The terminal's answer to the support query and, if the window size did
/// not carry pixels, to the cell-size report.
#[cfg(unix)]
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Answer {
    supported: bool,
    cell: Option<(u32, u32)>,
}

#[cfg(unix)]
const QUERY: &[u8] = b"\x1b_Gi=31,s=1,v=1,a=q,t=d,f=24;AAAA\x1b\\";
#[cfg(unix)]
const CELL_SIZE_QUERY: &[u8] = b"\x1b[16t";
#[cfg(unix)]
const DEVICE_ATTRIBUTES: &[u8] = b"\x1b[c";

/// The graphics reply (`ESC _ G i=31;OK ESC \`) and cell-size report
/// (`CSI 6 ; height ; width t`) in what the terminal sent back.
#[cfg(unix)]
fn parse_answer(reply: &[u8]) -> Answer {
    let supported = reply
        .windows(b"\x1b_Gi=31;OK".len())
        .any(|window| window == b"\x1b_Gi=31;OK");
    let cell = reply
        .windows(b"\x1b[6;".len())
        .zip(0..)
        .find(|(window, _)| *window == b"\x1b[6;")
        .and_then(|(_, at)| {
            let rest = &reply[at + b"\x1b[6;".len()..];
            let end = rest.iter().position(|byte| *byte == b't')?;
            let mut parts = std::str::from_utf8(&rest[..end]).ok()?.split(';');
            let height = parts.next()?.parse::<u32>().ok()?;
            let width = parts.next()?.parse::<u32>().ok()?;
            (height > 0 && width > 0).then_some((width, height))
        });
    Answer { supported, cell }
}

/// Whether the terminal has answered the device attributes request, which
/// always comes last.
#[cfg(unix)]
fn answer_complete(reply: &[u8]) -> bool {
    reply
        .windows(3)
        .zip(0..)
        .any(|(window, at)| window == b"\x1b[?" && reply[at + 3..].contains(&b'c'))
}

/// Ask the controlling terminal whether it draws kitty graphics and how big
/// its cells are. `None` when there is no terminal, it does not answer, or
/// its geometry is unknown.
#[cfg(unix)]
#[must_use]
pub fn detect() -> Option<Cells> {
    use std::io::{Read as _, Write as _};
    use std::time::{Duration, Instant};

    use rustix::termios::{self, OptionalActions, SpecialCodeIndex};

    struct Restore<'a> {
        tty: &'a std::fs::File,
        saved: termios::Termios,
    }

    impl Drop for Restore<'_> {
        fn drop(&mut self) {
            let _ = termios::tcsetattr(self.tty, OptionalActions::Now, &self.saved);
        }
    }

    let tty = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .open("/dev/tty")
        .ok()?;
    let size = termios::tcgetwinsize(&tty).ok()?;
    if size.ws_col == 0 || size.ws_row == 0 {
        return None;
    }
    let mut cell = (size.ws_xpixel > 0 && size.ws_ypixel > 0).then(|| {
        (
            u32::from(size.ws_xpixel) / u32::from(size.ws_col),
            u32::from(size.ws_ypixel) / u32::from(size.ws_row),
        )
    });

    let saved = termios::tcgetattr(&tty).ok()?;
    let mut raw = saved.clone();
    raw.make_raw();
    // Reads return empty after a tenth of a second without input rather
    // than blocking; `poll` is not an option because macOS does not support
    // it on terminal devices.
    raw.special_codes[SpecialCodeIndex::VMIN] = 0;
    raw.special_codes[SpecialCodeIndex::VTIME] = 1;
    termios::tcsetattr(&tty, OptionalActions::Now, &raw).ok()?;
    let _restore = Restore { tty: &tty, saved };

    let mut request = QUERY.to_vec();
    if cell.is_none() {
        request.extend_from_slice(CELL_SIZE_QUERY);
    }
    request.extend_from_slice(DEVICE_ATTRIBUTES);
    (&tty).write_all(&request).ok()?;
    (&tty).flush().ok()?;

    let deadline = Instant::now() + Duration::from_millis(500);
    let mut reply = Vec::new();
    let mut chunk = [0u8; 256];
    while !answer_complete(&reply) {
        if Instant::now() >= deadline {
            return None;
        }
        match (&tty).read(&mut chunk) {
            // A timed-out read: keep waiting until the deadline, which
            // covers a slow link to a terminal that does answer.
            Ok(0) => {}
            Err(_) => return None,
            Ok(read) => reply.extend_from_slice(&chunk[..read]),
        }
    }

    let answer = parse_answer(&reply);
    if !answer.supported {
        return None;
    }
    cell = cell.or(answer.cell);
    let (cell_width, cell_height) = cell.filter(|(width, height)| *width > 0 && *height > 0)?;
    Some(Cells {
        cell_width,
        cell_height,
        columns: size.ws_col,
        rows: size.ws_row,
    })
}

#[cfg(not(unix))]
#[must_use]
pub fn detect() -> Option<Cells> {
    None
}

/// One image ready for the terminal: the escape sequences that transmit it
/// and the placeholder rows the view carries in its place.
#[derive(Debug)]
pub struct Placement {
    pub transmission: Vec<u8>,
    pub placeholder: String,
}

/// Prepare `bytes` (a PNG, JPEG, or WebP) for display under image `id`,
/// fitted to `max_columns` and `max_rows` at its natural size or smaller.
/// `None` when the image cannot be decoded.
#[must_use]
pub fn place(
    id: u32,
    bytes: &[u8],
    cells: Cells,
    max_columns: u16,
    max_rows: u16,
) -> Option<Placement> {
    let mut reader = ImageReader::new(Cursor::new(bytes))
        .with_guessed_format()
        .ok()?;
    let mut limits = image::Limits::default();
    limits.max_image_width = Some(MAX_PIXELS);
    limits.max_image_height = Some(MAX_PIXELS);
    reader.limits(limits);
    let format = reader.format()?;

    let (width, height, keys, payload) = if format == ImageFormat::Png {
        let (width, height) = reader.into_dimensions().ok()?;
        (width, height, "f=100".to_string(), bytes.to_vec())
    } else {
        let decoded = reader.decode().ok()?.into_rgba8();
        let (width, height) = decoded.dimensions();
        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::fast());
        std::io::Write::write_all(&mut encoder, decoded.as_raw()).ok()?;
        let compressed = encoder.finish().ok()?;
        (
            width,
            height,
            format!("f=32,s={width},v={height},o=z"),
            compressed,
        )
    };
    if width == 0 || height == 0 || width > MAX_PIXELS || height > MAX_PIXELS {
        return None;
    }

    let (columns, rows) = fit(width, height, cells, max_columns, max_rows);
    Some(Placement {
        transmission: transmission(id, &format!("{keys},c={columns},r={rows}"), &payload),
        placeholder: placeholder(id, columns, rows),
    })
}

/// The cell box for a `width`×`height` pixel image: its natural size, scaled
/// down uniformly when it would not fit.
fn fit(width: u32, height: u32, cells: Cells, max_columns: u16, max_rows: u16) -> (u16, u16) {
    let max_columns = u32::from(max_columns.clamp(1, MAX_EXTENT));
    let max_rows = u32::from(max_rows.clamp(1, MAX_EXTENT));
    let natural_columns = width.div_ceil(cells.cell_width.max(1)).max(1);
    let natural_rows = height.div_ceil(cells.cell_height.max(1)).max(1);
    // Scale by the tighter constraint, in integer arithmetic: the shrunk
    // dimension is the limit, the other follows the natural ratio.
    let (columns, rows) = if natural_columns <= max_columns && natural_rows <= max_rows {
        (natural_columns, natural_rows)
    } else if natural_columns * max_rows >= natural_rows * max_columns {
        // Width is the tighter constraint.
        let rows = (natural_rows * max_columns).div_ceil(natural_columns);
        (max_columns, rows.clamp(1, max_rows))
    } else {
        let columns = (natural_columns * max_rows).div_ceil(natural_rows);
        (columns.clamp(1, max_columns), max_rows)
    };
    // Both are bounded by MAX_EXTENT, so the narrowing is lossless.
    (
        u16::try_from(columns).unwrap_or(MAX_EXTENT),
        u16::try_from(rows).unwrap_or(MAX_EXTENT),
    )
}

/// The chunked `a=T,U=1` transmission for `payload` under `id` with the
/// format and placement `keys`. Responses are suppressed (`q=2`) so nothing
/// lands on the pager's stdin.
fn transmission(id: u32, keys: &str, payload: &[u8]) -> Vec<u8> {
    let encoded = BASE64.encode(payload);
    let chunks: Vec<&[u8]> = encoded.as_bytes().chunks(CHUNK).collect();
    let last = chunks.len().saturating_sub(1);
    let mut out = Vec::with_capacity(encoded.len() + chunks.len() * 32);
    for (index, chunk) in chunks.iter().enumerate() {
        out.extend_from_slice(b"\x1b_G");
        if index == 0 {
            out.extend_from_slice(format!("a=T,U=1,q=2,i={id},{keys},").as_bytes());
        }
        let more = u8::from(index != last);
        out.extend_from_slice(format!("m={more};").as_bytes());
        out.extend_from_slice(chunk);
        out.extend_from_slice(b"\x1b\\");
    }
    out
}

/// `rows` lines of `columns` placeholder cells referencing image `id`. Each
/// cell carries its own row and column diacritics, so the pager may repaint
/// any cell in isolation.
fn placeholder(id: u32, columns: u16, rows: u16) -> String {
    let color = format!(
        "\x1b[38;2;{};{};{}m",
        (id >> 16) & 0xFF,
        (id >> 8) & 0xFF,
        id & 0xFF
    );
    let mut out = String::with_capacity(usize::from(rows) * (usize::from(columns) * 8 + 24));
    for &row in &DIACRITICS[..usize::from(rows.min(MAX_EXTENT))] {
        out.push_str(&color);
        for &column in &DIACRITICS[..usize::from(columns.min(MAX_EXTENT))] {
            out.push(PLACEHOLDER);
            out.push(row);
            out.push(column);
        }
        let _ = writeln!(out, "\x1b[0m");
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const CELLS: Cells = Cells {
        cell_width: 10,
        cell_height: 20,
        columns: 100,
        rows: 40,
    };

    #[cfg(unix)]
    #[test]
    fn support_needs_the_graphics_reply_before_device_attributes() {
        let yes = parse_answer(b"\x1b_Gi=31;OK\x1b\\\x1b[?62;22c");
        assert!(yes.supported);
        assert_eq!(yes.cell, None);
        let no = parse_answer(b"\x1b[?62;22c");
        assert!(!no.supported);
        assert!(answer_complete(b"\x1b_Gi=31;OK\x1b\\\x1b[?62;22c"));
        assert!(!answer_complete(b"\x1b_Gi=31;OK\x1b\\\x1b[?62;2"));
        assert!(!answer_complete(b"\x1b_Gi=31;OK\x1b\\"));
    }

    #[cfg(unix)]
    #[test]
    fn cell_size_report_is_parsed_when_present() {
        let answer = parse_answer(b"\x1b_Gi=31;OK\x1b\\\x1b[6;24;11t\x1b[?62c");
        assert_eq!(answer.cell, Some((11, 24)));
        assert_eq!(parse_answer(b"\x1b[6;0;11t\x1b[?62c").cell, None);
    }

    #[test]
    fn less_release_numbers_gate_placeholder_support() {
        assert_eq!(
            less_version("less 668 (POSIX regular expressions)\n"),
            Some(668)
        );
        assert_eq!(less_version("less 581.2 (PCRE2)"), None);
        assert_eq!(less_version("more"), None);
        assert_eq!(less_char_definitions(None), "10EEEE:p");
        assert_eq!(less_char_definitions(Some("  ")), "10EEEE:p");
        assert_eq!(
            less_char_definitions(Some("E000-F8FF:p")),
            "E000-F8FF:p,10EEEE:p"
        );
    }

    #[test]
    fn images_keep_their_natural_size_until_they_would_not_fit() {
        assert_eq!(fit(100, 40, CELLS, 80, 30), (10, 2));
        assert_eq!(fit(105, 41, CELLS, 80, 30), (11, 3));
        // Twice too wide: halve both.
        assert_eq!(fit(1600, 400, CELLS, 80, 30), (80, 10));
        // Twice too tall: halve both.
        assert_eq!(fit(400, 1200, CELLS, 80, 30), (20, 30));
        assert_eq!(fit(1, 1, CELLS, 80, 30), (1, 1));
        assert_eq!(fit(100_000, 1, CELLS, 1000, 1000), (MAX_EXTENT, 1));
    }

    #[test]
    fn placeholder_rows_address_every_cell_under_the_image_color() {
        let rows = placeholder(0x0001_0203, 3, 2);
        let lines: Vec<&str> = rows.lines().collect();
        assert_eq!(lines.len(), 2);
        for (row, line) in lines.iter().enumerate() {
            assert!(line.starts_with("\x1b[38;2;1;2;3m"));
            assert!(line.ends_with("\x1b[0m"));
            let cells: Vec<char> = line
                .trim_start_matches("\x1b[38;2;1;2;3m")
                .trim_end_matches("\x1b[0m")
                .chars()
                .collect();
            assert_eq!(cells.len(), 9);
            for column in 0..3 {
                assert_eq!(cells[column * 3], PLACEHOLDER);
                assert_eq!(cells[column * 3 + 1], DIACRITICS[row]);
                assert_eq!(cells[column * 3 + 2], DIACRITICS[column]);
            }
        }
    }

    #[test]
    fn transmissions_are_chunked_with_control_data_first() {
        let payload = vec![7u8; 6200];
        let bytes = transmission(258, "f=100,c=4,r=2", &payload);
        let text = String::from_utf8(bytes).unwrap();
        let chunks: Vec<&str> = text
            .split("\x1b\\")
            .filter(|chunk| !chunk.is_empty())
            .collect();
        // 6200 bytes → 8268 base64 chars → 4096 + 4096 + 76.
        assert_eq!(chunks.len(), 3);
        assert!(chunks[0].starts_with("\x1b_Ga=T,U=1,q=2,i=258,f=100,c=4,r=2,m=1;"));
        assert!(chunks[1].starts_with("\x1b_Gm=1;"));
        assert!(chunks[2].starts_with("\x1b_Gm=0;"));
        let data = |chunk: &str| chunk.split_once(';').map(|(_, data)| data.len());
        assert_eq!(data(chunks[0]), Some(4096));
        assert_eq!(data(chunks[1]), Some(4096));
        assert_eq!(data(chunks[2]), Some(76));
    }

    #[test]
    fn png_bytes_are_transmitted_verbatim_and_other_formats_as_pixels() {
        let png = encode(ImageFormat::Png);
        let placed = place(300, &png, CELLS, 80, 30).unwrap();
        let text = String::from_utf8_lossy(&placed.transmission).into_owned();
        assert!(text.starts_with("\x1b_Ga=T,U=1,q=2,i=300,f=100,c=4,r=1,m=0;"));
        assert_eq!(placed.placeholder.lines().count(), 1);

        let jpeg = encode(ImageFormat::Jpeg);
        let placed = place(301, &jpeg, CELLS, 80, 30).unwrap();
        let text = String::from_utf8_lossy(&placed.transmission).into_owned();
        assert!(text.starts_with("\x1b_Ga=T,U=1,q=2,i=301,f=32,s=40,v=20,o=z,c=4,r=1,m="));

        assert!(place(302, b"not an image", CELLS, 80, 30).is_none());
    }

    fn encode(format: ImageFormat) -> Vec<u8> {
        let image = image::RgbaImage::from_pixel(40, 20, image::Rgba([10, 200, 30, 255]));
        let mut out = Cursor::new(Vec::new());
        image::DynamicImage::ImageRgba8(image)
            .write_to(&mut out, format)
            .unwrap();
        out.into_inner()
    }
}
