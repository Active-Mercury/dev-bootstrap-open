#!/usr/bin/env bash
#
# Basic git shortcuts meant to be 'source'-d.

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
