# List all aliases in the current session:
alias \
  | sed -e 's/^alias //' -e 's/=.*$//' \
  | sort -u
