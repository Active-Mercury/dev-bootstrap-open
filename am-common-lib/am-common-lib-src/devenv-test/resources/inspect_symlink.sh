#!/usr/bin/env bash

inspect_symlink() {
  local name="$1"
  local path target

  # 1) find it in PATH (forces an error if it’s a shell function/builtin)
  if ! path=$(type -P -- "$name"); then
    echo >&2 "$name: command not found in PATH"
    return 1
  fi

  # 2) resolve every symlink to the real file
  if ! target=$(readlink -f -- "$path"); then
    echo >&2 "$name points to $path, which does not exist"
    return 2
  fi

  # 3) sanity‐check that the final target really exists
  if [[ ! -e $target ]]; then
    echo >&2 "$name points to $target, which does not exist"
    return 3
  fi

  # 4) finally, test the executable bit
  if [[ ! -x $target ]]; then
    echo >&2 "$name points to $target, which is not executable"
    return 4
  fi

  # All good: quiet success
  return 0
}
