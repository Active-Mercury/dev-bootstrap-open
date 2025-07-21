# List all shell functions defined in the current session:
typeset -f \
  | sed -n 's/^\([[:alnum:]_][[:alnum:]_]*\)[[:space:]]*().*/\1/p' \
  | sort -u
