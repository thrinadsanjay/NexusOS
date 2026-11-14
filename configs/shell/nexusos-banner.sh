# shellcheck shell=sh
# NexusOS terminal banner -- installed as /etc/profile.d/nexusos-banner.sh by nexusos-branding.
#
# Shown once per interactive login shell. It never runs for scripts, non-interactive
# shells, dumb terminals, or when the user opts out with either:
#   * export NEXUSOS_NO_BANNER=1
#   * touch ~/.hushlogin   (standard login(1) convention)

nexusos_banner() {
    case "$-" in *i*) ;; *) return 0 ;; esac
    [ -n "${NEXUSOS_NO_BANNER:-}" ] && return 0
    [ -f "${HOME:-/nonexistent}/.hushlogin" ] && return 0
    [ "${TERM:-dumb}" = "dumb" ] && return 0
    [ -t 1 ] || return 0

    _nx_logo=/usr/share/nexusos/ascii-logo.txt
    _nx_release=/usr/lib/nexusos/release
    _nx_teal=$(printf '\033[38;2;49;198;189m')
    _nx_copper=$(printf '\033[38;2;196;119;80m')
    _nx_dim=$(printf '\033[38;2;158;179;183m')
    _nx_reset=$(printf '\033[0m')

    if [ -r "$_nx_logo" ]; then
        printf '%s' "$_nx_teal"
        cat "$_nx_logo"
        printf '%s' "$_nx_reset"
    fi

    _nx_edition="Engineering Edition"
    _nx_build=""
    _nx_creator=""
    if [ -r "$_nx_release" ]; then
        # Parse only the keys we need; never source the file into the login shell.
        _nx_edition=$(sed -n 's/^NEXUSOS_EDITION="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$_nx_release")
        _nx_build=$(sed -n 's/^NEXUSOS_BUILD="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$_nx_release")
        _nx_creator=$(sed -n 's/^NEXUSOS_CREATOR="\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' "$_nx_release")
    fi
    printf '  %sNexusOS%s %s %s%s%s\n' "$_nx_teal" "$_nx_reset" "$_nx_edition" "$_nx_dim" "$_nx_build" "$_nx_reset"
    printf '  %sBUILD. AUTOMATE. DEPLOY.%s  %s·  type%s nexus help\n' "$_nx_copper" "$_nx_reset" "$_nx_dim" "$_nx_reset"
    [ -n "$_nx_creator" ] && printf '  %sCrafted by%s %s%s%s\n' "$_nx_dim" "$_nx_reset" "$_nx_copper" "$_nx_creator" "$_nx_reset"
    printf '\n'

    unset _nx_logo _nx_release _nx_teal _nx_copper _nx_dim _nx_reset _nx_edition _nx_build _nx_creator
}

nexusos_banner
unset -f nexusos_banner
