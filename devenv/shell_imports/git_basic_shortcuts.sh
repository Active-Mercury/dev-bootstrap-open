#!/usr/bin/env bash
#
# Basic git shortcuts meant to be 'source'-d (bash and zsh).

ga() {
  git add "$@"
}

gb() {
  git branch "$@"
}

gc() {
  git commit "$@"
}

gco() {
  git checkout "$@"
}

gd() {
  git diff "$@"
}

gl() {
  git log "$@"
}

gst() {
  git status "$@"
}

# --- Tab-completion wiring ------------------------------------------------
# Propagate git's native completions to each shortcut so that, e.g.,
# "gco <TAB>" offers branch names just like "git checkout <TAB>".

if [[ -n "$BASH_VERSION" ]]; then
  # Ensure git's bash-completion helpers are loaded.
  if ! declare -f __git_complete >/dev/null 2>&1; then
    for _gbs_comp_file in \
      /usr/share/bash-completion/completions/git \
      /etc/bash_completion.d/git-completion.bash \
      /usr/share/git-core/contrib/completion/git-completion.bash \
      /Library/Developer/CommandLineTools/usr/share/git-core/git-completion.bash; do
      if [[ -f "$_gbs_comp_file" ]]; then
        # shellcheck disable=SC1090
        source "$_gbs_comp_file"
        break
      fi
    done
    unset _gbs_comp_file
  fi

  if declare -f __git_complete >/dev/null 2>&1; then
    __git_complete ga  _git_add
    __git_complete gb  _git_branch
    __git_complete gc  _git_commit
    __git_complete gco _git_checkout
    __git_complete gd  _git_diff
    __git_complete gl  _git_log
    __git_complete gst _git_status
  fi

elif [[ -n "$ZSH_VERSION" ]]; then
  if (( ${+functions[compdef]} )); then
    compdef _git ga=git-add
    compdef _git gb=git-branch
    compdef _git gc=git-commit
    compdef _git gco=git-checkout
    compdef _git gd=git-diff
    compdef _git gl=git-log
    compdef _git gst=git-status
  fi
fi
