# NexusOS zsh prompt -- /usr/share/nexusos/shell/nexus-prompt.zsh
# Two-line prompt in brand colours with git branch (vcs_info) and exit status.
autoload -Uz vcs_info
zstyle ':vcs_info:*' enable git
zstyle ':vcs_info:git:*' formats ' %F{#C47750}%b%f'
zstyle ':vcs_info:git:*' actionformats ' %F{#C47750}%b|%a%f'
precmd_functions+=(vcs_info)
setopt PROMPT_SUBST
PROMPT=$'%F{#29434A}╭─%f%F{#31C6BD}%n@%m%f %F{#9EB3B7}%~%f${vcs_info_msg_0_}\n%F{#29434A}╰─%f%(?.%F{#31C6BD}.%F{#D9574F})❯%f '
RPROMPT='%(?..%F{#D9574F}%?%f)'
