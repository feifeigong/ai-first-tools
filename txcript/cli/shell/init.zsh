# ctrl+shift+r: pick a txcript session recorded in the current folder.
txcript-cwd-picker() {
  printf '\e[=0;1u'                       # legacy keys for the picker's raw reader
  txcript query --cwd "$PWD" < /dev/tty
  printf '\e[=1;1u'
  zle reset-prompt
}
zle -N txcript-cwd-picker
if [[ $TERM == (*kitty*|*ghostty*|*wezterm*) ]]; then
  # In legacy encoding ctrl+shift+r and ctrl+r send the same byte. Enable the
  # kitty keyboard protocol (flag 1, "disambiguate escape codes") only while
  # zle reads a line, via the stateless `CSI = u` set form.
  txcript--keys-on()  { printf '\e[=1;1u' }
  txcript--keys-off() { printf '\e[=0;1u' }
  autoload -Uz add-zle-hook-widget
  add-zle-hook-widget line-init txcript--keys-on
  add-zle-hook-widget line-finish txcript--keys-off
  # Under flag 1, every modified key arrives as a CSI-u sequence; feed the
  # legacy bytes back so every existing binding still fires.
  () {
    local i
    for i in {97..122}; do
      bindkey -s "\e[${i};5u" "${(#):-$((i - 96))}"     # ctrl+letter
      bindkey -s "\e[${i};7u" "\e${(#):-$((i - 96))}"   # ctrl+alt+letter
    done
    for i in {33..126}; do
      case $i in
        (92) bindkey -s "\e[${i};3u" '\e\\' ;;          # alt+backslash
        (94) bindkey -s "\e[${i};3u" '\e\^' ;;          # alt+caret
        (*)  bindkey -s "\e[${i};3u" "\e${(#):-$i}" ;;  # alt+printable
      esac
    done
  }
  bindkey -s '\e[32;3u' '\e '                           # alt+space
  bindkey -s '\e[127;3u' '\e^?'                         # alt+backspace: kill word
  bindkey -s '\e[127;5u' '^H'                           # ctrl+backspace
  bindkey -s '\e[127;7u' '\e^H'                         # ctrl+alt+backspace
  bindkey -s '\e[13;2u' '^M'                            # shift+enter
  bindkey -s '\e[13;3u' '\e^M'                          # alt+enter
  bindkey -s '\e[13;5u' '^M'                            # ctrl+enter
  bindkey '\e[99;5u' send-break                         # ctrl+c aborts the line
  bindkey -s '\e[27u' '\e'                              # bare ESC
  bindkey '\e[114;6u' txcript-cwd-picker                # ctrl+shift+r
fi
