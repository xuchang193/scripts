# 历史命令优化
HISTSIZE=10000    # 历史记录大小
SAVEHIST=10000    # 保存历史条数
HISTFILE=~/.zsh_history  # 历史文件
setopt SHARE_HISTORY     # 多终端共享历史
setopt HIST_IGNORE_DUPS  # 不记录重复命令
setopt HIST_IGNORE_SPACE # 空格开头的命令不记录

# 补全功能优化
autoload -U compinit
compinit
zstyle ':completion:*' menu select    # 补全可选择
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Z}' # 大小写


# 开启彩色终端 + ll/la 快捷命令
if [ -x /usr/bin/dircolors ]; then
    eval "$(dircolors -b)"
    alias ls='ls --color=auto'
    alias grep='grep --color=auto'
fi
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

setopt CORRECT
setopt CORRECT_ALL

### my options
export PATH="$HOME/scripts:$PATH"
alias killcode=killcode.sh
alias qt=qt.sh
alias fullpath=fullpath.sh 
alias autostart=autostart.sh

### SEMulator3D filemd5track
export PATH="/home/xuchang/Coventor/SEMulator3D11/bin/linux_x64:$PATH"
export PATH="/home/xuchang/software/filemd5track:$PATH"

export QT_QPA_PLATFORM=xcb
