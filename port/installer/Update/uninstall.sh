#!/bin/ksh
# Audi cluster integration: journaled removal (ModKit Update stage with uninstall.txt).
# Restores only what this module's journal recorded. Never touches the ModKit loader.
set -u
case "$0" in */*) here=${0%/*};; *) here=.;; esac   # no dirname: it is not on the update-mode PATH
here=$(cd "$here" && pwd -P)
. "$here/common.sh"
MANIFEST="$here/manifest.txt"
[[ -f "$MANIFEST" ]] || fail 'manifest.txt missing'
require_env
SCRATCH="$MEDIA_PATH/.audi-cluster-scratch.$$"
mkdir -p "$SCRATCH" || fail 'cannot create scratch on media'
trap 'rm -rf "$SCRATCH"' EXIT
selftest_hash_tool

case "$(current_state)" in
    NONE) log 'nothing recorded as installed by this module'; exit 0;;
    RESTORED) log 'already restored; journal retained'; exit 0;;
esac
perform_rollback || exit 2
