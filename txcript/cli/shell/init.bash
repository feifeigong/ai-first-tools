# ctrl+shift+r: pick a txcript session recorded in the current folder.
txcript_cwd_picker() {
  printf '\e[=0;1u'                       # legacy keys for the picker's raw reader
  txcript query --cwd "$PWD" < /dev/tty
  printf '\e[=1;1u'
}
case $TERM in (*kitty*|*ghostty*|*wezterm*)
  # In legacy encoding ctrl+shift+r and ctrl+r send the same byte. Enable the
  # kitty keyboard protocol (flag 1, "disambiguate escape codes") only while
  # readline reads a line: on when the prompt is shown, off just before the
  # command runs.
  PROMPT_COMMAND="printf '\\e[=1;1u'${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
  PS0="\$(printf '\\e[=0;1u')${PS0-}"
  # Under flag 1, every modified key arrives as a CSI-u sequence; feed the
  # legacy bytes back so every existing binding still fires.
  _txcript_letters=abcdefghijklmnopqrstuvwxyz
  for ((_txcript_i = 0; _txcript_i < 26; _txcript_i++)); do
    _txcript_l=${_txcript_letters:_txcript_i:1}
    _txcript_k=$((97 + _txcript_i))
    bind "\"\e[${_txcript_k};5u\": \"\C-${_txcript_l}\""     # ctrl+letter
    bind "\"\e[${_txcript_k};7u\": \"\e\C-${_txcript_l}\""   # ctrl+alt+letter
  done
  for ((_txcript_k = 33; _txcript_k <= 126; _txcript_k++)); do
    printf -v _txcript_l "\\$(printf '%03o' "$_txcript_k")"
    case $_txcript_l in ('"'|'\') _txcript_l=\\$_txcript_l ;; esac
    bind "\"\e[${_txcript_k};3u\": \"\e${_txcript_l}\""      # alt+printable
  done
  unset _txcript_letters _txcript_i _txcript_l _txcript_k
  bind '"\e[32;3u": "\e "'                                   # alt+space
  bind '"\e[127;3u": "\e\C-?"'                               # alt+backspace: kill word
  bind '"\e[127;5u": "\C-h"'                                 # ctrl+backspace
  bind '"\e[127;7u": "\e\C-h"'                               # ctrl+alt+backspace
  bind '"\e[13;2u": "\C-m"'                                  # shift+enter
  bind '"\e[13;3u": "\e\C-m"'                                # alt+enter
  bind '"\e[13;5u": "\C-m"'                                  # ctrl+enter
  bind '"\e[99;5u": abort'                                   # ctrl+c
  bind '"\e[27u": "\e"'                                      # bare ESC
  bind -x '"\e[114;6u": txcript_cwd_picker'                  # ctrl+shift+r
esac
