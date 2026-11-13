# shellcheck shell=sh
# NexusOS shared aliases for bash and zsh -- /usr/share/nexusos/shell/nexus-aliases.sh
# Sourced by /etc/skel/.zshrc and optionally from ~/.bashrc. No alias shadows a
# command with different semantics; destructive commands are not aliased.

alias ll='ls -alF --group-directories-first'
alias la='ls -A'
alias l='ls -CF'
alias ..='cd ..'
alias ...='cd ../..'
alias gs='git status -sb'
alias gl='git log --oneline --graph --decorate -n 20'
alias gd='git diff'
alias k='kubectl'
alias dps='docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
alias nx='nexus'

# Ubuntu packages fd and bat under different binary names.
command -v fdfind >/dev/null 2>&1 && ! command -v fd >/dev/null 2>&1 && alias fd='fdfind'
command -v batcat >/dev/null 2>&1 && ! command -v bat >/dev/null 2>&1 && alias bat='batcat'
