# Ultra-Practical Linux Coding Environment Optimization Spec

## Project Overview

This specification defines a comprehensive optimization of JyX's Linux development environment, focusing on:
- **Visual Enhancement**: Catppuccin Mocha theme across all tools
- **Practical Aliases**: High-frequency workflow shortcuts
- **Claude Code Integration**: Seamless tool usage in AI coding sessions
- **Fish Shell Architecture**: Modular, maintainable configuration

## Current Tool Inventory

### Core CLI Tools
- **Shell**: fish + starship prompt
- **File Operations**: bat, exa, rg, fd, fzf, tree, zoxide
- **Development**: git, gh, hub, docker, code
- **Cloud/DevOps**: gcloud, terraform, kubectl
- **Languages**: node/npm, go, cargo/rustc, python/pip, bun-js
- **System**: htop, yadm, tmux
- **Data**: jq
- **Terminal**: ghostty

## Architecture Strategy

### Configuration Management
- **Primary Shell**: Fish (`~/.config/fish/config.fish`)
- **Modular Configs**: `~/.config/fish/conf.d/` directory structure
- **Version Control**: yadm for dotfiles management
- **Theme System**: Catppuccin Mocha with tool-specific optimizations

### File Structure
```
~/.config/fish/
├── config.fish                 # Main fish config
├── conf.d/
│   ├── 01_aliases_files.fish   # File operations aliases
│   ├── 02_aliases_git.fish     # Git workflow aliases  
│   ├── 03_aliases_dev.fish     # Development server aliases
│   ├── 04_aliases_docker.fish  # Docker operation aliases
│   ├── 05_aliases_github.fish  # GitHub interaction aliases
│   ├── 10_theme_setup.fish     # Catppuccin theme configuration
│   ├── 11_env_vars.fish        # Environment variables
│   └── 99_claude_integration.fish # Claude Code optimizations
├── functions/                   # Custom Fish functions
└── themes/                     # Theme files
```

## Priority 1: File Operations Aliases

### Core Navigation & Search
```fish
# Directory navigation (zoxide integration)
alias cd='z'
alias cdi='zi'  # interactive cd
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'

# Enhanced listing
alias l='exa -la --git --icons'
alias ll='exa -l --git --icons'
alias la='exa -la --git --icons'
alias lt='exa --tree --level=2 --icons'
alias ltl='exa --tree --long --level=3 --icons'

# File searching (rg + fd + fzf integration)
alias f='fd'                    # find files
alias ff='fd --type f'          # find files only
alias fd='fd --type d'          # find directories only
alias fh='fd --hidden'          # include hidden files
alias rg='rg --smart-case --follow --hidden'
alias rgi='rg -i'              # case insensitive
alias rgf='rg --files-with-matches'  # just filenames

# Content viewing
alias cat='bat --paging=never'
alias less='bat --paging=always'
alias more='bat --paging=always'
alias preview='bat --style=numbers,changes,header'

# Interactive file operations
alias fzf='fzf --preview "bat --color=always {}"'
alias fzd='fd --type d | fzf --preview "exa --tree --level=2 {}"'
alias fzf='fd --type f | fzf --preview "bat --color=always {}"'
```

### Advanced File Functions
```fish
# Custom Fish functions (in ~/.config/fish/functions/)

# Find and edit file
function fe
    set file (fd --type f | fzf --preview "bat --color=always {}")
    if test -n "$file"
        code "$file"
    end
end

# Find and change to directory
function fcd
    set dir (fd --type d | fzf --preview "exa --tree --level=2 {}")
    if test -n "$dir"
        cd "$dir"
    end
end

# Ripgrep with fzf preview
function rge
    set result (rg --line-number --with-filename --smart-case $argv | fzf --delimiter=: --preview 'bat --color=always --highlight-line {2} {1}')
    if test -n "$result"
        set file (echo $result | cut -d: -f1)
        set line (echo $result | cut -d: -f2)
        code --goto "$file:$line"
    end
end
```

## Priority 2: Git Workflow Aliases

### Basic Git Operations
```fish
# Status and info
alias g='git'
alias gs='git status --short --branch'
alias gst='git status'
alias gl='git log --oneline --graph --decorate -10'
alias gla='git log --oneline --graph --decorate --all -10'
alias glg='git log --graph --pretty=format:"%C(yellow)%h%C(reset) - %C(blue)%an%C(reset), %C(green)%ar%C(reset) : %s"'

# Branch operations
alias gb='git branch'
alias gba='git branch -a'
alias gbd='git branch -d'
alias gbD='git branch -D'
alias gco='git checkout'
alias gcb='git checkout -b'
alias gm='git merge'
alias gmnf='git merge --no-ff'

# Commit operations  
alias ga='git add'
alias gaa='git add --all'
alias gc='git commit'
alias gcm='git commit -m'
alias gca='git commit --amend'
alias gcan='git commit --amend --no-edit'

# Push/Pull
alias gp='git push'
alias gpf='git push --force-with-lease'
alias gpl='git pull'
alias gpr='git pull --rebase'
alias gpu='git push -u origin (git branch --show-current)'

# Diff and show
alias gd='git diff'
alias gdc='git diff --cached'
alias gds='git diff --staged'
alias gdt='git difftool'
alias gsh='git show'
```

### Advanced Git Functions
```fish
# Custom Git functions

# Interactive rebase for last n commits
function gir
    set count (test -n "$argv[1]"; and echo $argv[1]; or echo "5")
    git rebase -i HEAD~$count
end

# Quick commit with message
function gcq
    git add --all
    git commit -m "$argv"
end

# Create and push new branch
function gnb
    set branch_name $argv[1]
    git checkout -b $branch_name
    git push -u origin $branch_name
end

# Git stash with message
function gstm
    git stash push -m "$argv"
end

# Undo last commit (keep changes)
function gundo
    git reset --soft HEAD~1
end

# Git log with file changes
function glf
    git log --follow --patch -- $argv[1]
end
```

## Priority 3: Development Server Aliases

### Common Development Tasks
```fish
# Package managers
alias n='npm'
alias nr='npm run'
alias ns='npm start'
alias nt='npm test'
alias ni='npm install'
alias nid='npm install --save-dev'
alias nig='npm install --global'
alias nup='npm update'

alias y='yarn'
alias yr='yarn run'
alias ya='yarn add'
alias yad='yarn add --dev'

alias p='python'
alias p3='python3'
alias pip='python -m pip'
alias venv='python -m venv'

# Server operations
alias serve='python -m http.server 8000'
alias liveserver='npx live-server'

# Process management
alias pf='ps aux | grep'
alias pk='pkill -f'
alias ports='netstat -tuln | grep'
alias listening='lsof -i -P -n | grep LISTEN'
```

### Development Functions
```fish
# Quick project setup
function newproject
    set project_name $argv[1]
    mkdir $project_name
    cd $project_name
    git init
    touch README.md
    touch .gitignore
    code .
end

# Kill process on port
function killport
    set port $argv[1]
    set pid (lsof -ti:$port)
    if test -n "$pid"
        kill -9 $pid
        echo "Killed process $pid on port $port"
    else
        echo "No process found on port $port"
    end
end

# Watch files and run command
function watchrun
    find . -name "*.py" -o -name "*.js" -o -name "*.ts" | entr -c $argv
end
```

## Priority 4: Docker Operations Aliases

### Container Management
```fish
# Docker basics
alias d='docker'
alias di='docker images'
alias dp='docker ps'
alias dpa='docker ps -a'
alias dr='docker run'
alias drit='docker run -it'
alias drm='docker rm'
alias drmi='docker rmi'

# Docker build and run
alias db='docker build'
alias dbt='docker build -t'
alias dex='docker exec'
alias deit='docker exec -it'
alias dl='docker logs'
alias dlf='docker logs -f'

# Docker compose
alias dc='docker-compose'
alias dcu='docker-compose up'
alias dcd='docker-compose down'
alias dcb='docker-compose build'
alias dcr='docker-compose restart'
alias dcs='docker-compose stop'
alias dcl='docker-compose logs'
alias dclf='docker-compose logs -f'
```

### Docker Functions
```fish
# Clean up Docker
function dcleanup
    echo "Removing stopped containers..."
    docker container prune -f
    echo "Removing unused images..."
    docker image prune -f
    echo "Removing unused volumes..."
    docker volume prune -f
    echo "Removing unused networks..."
    docker network prune -f
end

# Quick container shell access
function dsh
    set container $argv[1]
    set shell (test -n "$argv[2]"; and echo $argv[2]; or echo "bash")
    docker exec -it $container $shell
end

# Build and run with automatic naming
function dbr
    set image_name (basename (pwd))
    docker build -t $image_name .
    docker run -it --rm $image_name
end
```

## Priority 5: GitHub Interaction Aliases

### GitHub CLI (gh) Operations
```fish
# Repository operations
alias ghc='gh repo clone'
alias ghcr='gh repo create'
alias ghv='gh repo view'
alias ghvw='gh repo view --web'

# Pull requests
alias ghpr='gh pr create'
alias ghprl='gh pr list'
alias ghprv='gh pr view'
alias ghprm='gh pr merge'
alias ghprc='gh pr checkout'
alias ghprd='gh pr diff'

# Issues
alias ghil='gh issue list'
alias ghic='gh issue create'
alias ghiv='gh issue view'
alias ghie='gh issue edit'

# Workflows
alias ghw='gh workflow list'
alias ghr='gh run list'
alias ghrl='gh run view'
```

### Hub CLI Integration
```fish
# Hub operations (for legacy workflows)
alias hc='hub clone'
alias hcr='hub create'
alias hb='hub browse'
alias hpr='hub pull-request'
alias hf='hub fork'
```

### GitHub Functions
```fish
# Quick PR creation with template
function ghprq
    set title $argv[1]
    set body (test -n "$argv[2]"; and echo $argv[2]; or echo "")
    gh pr create --title "$title" --body "$body" --draft
end

# Clone and cd
function ghcc
    set repo $argv[1]
    gh repo clone $repo
    set repo_name (basename $repo)
    cd $repo_name
end

# Open current repo in browser
function ghopen
    gh repo view --web
end
```

## Visual Theme Configuration: Catppuccin Mocha

### Color Palette
```fish
# Catppuccin Mocha color definitions
set -gx CATPPUCCIN_ROSEWATER "rgb(245,224,220)"
set -gx CATPPUCCIN_FLAMINGO "rgb(242,205,205)"
set -gx CATPPUCCIN_PINK "rgb(245,194,231)"
set -gx CATPPUCCIN_MAUVE "rgb(203,166,247)"
set -gx CATPPUCCIN_RED "rgb(243,139,168)"
set -gx CATPPUCCIN_MAROON "rgb(235,160,172)"
set -gx CATPPUCCIN_PEACH "rgb(250,179,135)"
set -gx CATPPUCCIN_YELLOW "rgb(249,226,175)"
set -gx CATPPUCCIN_GREEN "rgb(166,227,161)"
set -gx CATPPUCCIN_TEAL "rgb(148,226,213)"
set -gx CATPPUCCIN_SKY "rgb(137,220,235)"
set -gx CATPPUCCIN_SAPPHIRE "rgb(116,199,236)"
set -gx CATPPUCCIN_BLUE "rgb(137,180,250)"
set -gx CATPPUCCIN_LAVENDER "rgb(180,190,254)"
set -gx CATPPUCCIN_TEXT "rgb(205,214,244)"
set -gx CATPPUCCIN_SUBTEXT1 "rgb(186,194,222)"
set -gx CATPPUCCIN_SUBTEXT0 "rgb(166,173,200)"
set -gx CATPPUCCIN_OVERLAY2 "rgb(147,153,178)"
set -gx CATPPUCCIN_OVERLAY1 "rgb(127,132,156)"
set -gx CATPPUCCIN_OVERLAY0 "rgb(108,112,134)"
set -gx CATPPUCCIN_SURFACE2 "rgb(88,91,112)"
set -gx CATPPUCCIN_SURFACE1 "rgb(69,71,90)"
set -gx CATPPUCCIN_SURFACE0 "rgb(49,50,68)"
set -gx CATPPUCCIN_BASE "rgb(30,30,46)"
set -gx CATPPUCCIN_MANTLE "rgb(24,24,37)"
set -gx CATPPUCCIN_CRUST "rgb(17,17,27)"
```  

### Tool-Specific Theme Configurations

#### Fish Shell
```fish
# ~/.config/fish/conf.d/10_theme_setup.fish

# Fish syntax highlighting colors
set fish_color_normal $CATPPUCCIN_TEXT
set fish_color_command $CATPPUCCIN_BLUE
set fish_color_keyword $CATPPUCCIN_MAUVE
set fish_color_quote $CATPPUCCIN_GREEN
set fish_color_redirection $CATPPUCCIN_PINK
set fish_color_end $CATPPUCCIN_PEACH
set fish_color_error $CATPPUCCIN_RED
set fish_color_param $CATPPUCCIN_ROSEWATER
set fish_color_comment $CATPPUCCIN_OVERLAY0
set fish_color_selection --background=$CATPPUCCIN_SURFACE0
set fish_color_search_match --background=$CATPPUCCIN_SURFACE0
set fish_color_operator $CATPPUCCIN_SKY
set fish_color_escape $CATPPUCCIN_PINK
set fish_color_autosuggestion $CATPPUCCIN_OVERLAY0
set fish_color_cancel $CATPPUCCIN_RED

# Completion colors  
set fish_pager_color_progress $CATPPUCCIN_OVERLAY0
set fish_pager_color_prefix $CATPPUCCIN_BLUE
set fish_pager_color_completion $CATPPUCCIN_TEXT
set fish_pager_color_description $CATPPUCCIN_OVERLAY1
```

#### Starship Prompt
```toml
# ~/.config/starship.toml
format = """
[](color_orange)\
$os\
$username\
[](bg:color_yellow fg:color_orange)\
$directory\
[](fg:color_yellow bg:color_aqua)\
$git_branch\
$git_status\
[](fg:color_aqua bg:color_blue)\
$c\
$elixir\
$elm\
$golang\
$gradle\
$haskell\
$java\
$julia\
$nodejs\
$nim\
$rust\
$scala\
[](fg:color_blue bg:color_bg3)\
$docker_context\
[](fg:color_bg3 bg:color_bg1)\
$time\
[ ](fg:color_bg1)\
"""

palette = 'catppuccin_mocha'

[palettes.catppuccin_mocha]
color_fg0 = '#cdd6f4'
color_bg1 = '#1e1e2e'
color_bg3 = '#313244'
color_blue = '#89b4fa'
color_aqua = '#94e2d5'
color_green = '#a6e3a1'
color_orange = '#fab387'
color_purple = '#f5c2e7'
color_red = '#f38ba8'
color_yellow = '#f9e2af'

[os]
disabled = false
style = "bg:color_orange fg:color_fg0"

[os.symbols]
Windows = "󰍲"
Ubuntu = "󰕈"
SUSE = ""
Raspbian = "󰐿"
Mint = "󰣭"
Macos = "󰀵"
Manjaro = ""
Linux = "󰌽"
Gentoo = "󰣨"
Fedora = "󰣛"
Alpine = ""
Amazon = ""
Android = ""
Arch = "󰣇"
Artix = "󰣇"
CentOS = ""
Debian = "󰣚"
Redhat = "󱄛"
RedHatEnterprise = "󱄛"

[username]
show_always = true
style_user = "bg:color_orange fg:color_fg0"
style_root = "bg:color_orange fg:color_fg0"
format = '[$user ]($style)'
disabled = false

[directory]
style = "fg:color_fg0 bg:color_yellow"
format = "[ $path ]($style)"
truncation_length = 3
truncation_symbol = "…/"

[directory.substitutions]
"Documents" = "󰈙 "
"Downloads" = " "
"Music" = " "
"Pictures" = " "

[git_branch]
symbol = ""
style = "bg:color_aqua"
format = '[[ $symbol $branch ](fg:color_fg0 bg:color_aqua)]($style)'

[git_status]
style = "bg:color_aqua"
format = '[[($all_status$ahead_behind )](fg:color_fg0 bg:color_aqua)]($style)'

[nodejs]
symbol = ""
style = "bg:color_blue"
format = '[[ $symbol ($version) ](fg:color_fg0 bg:color_blue)]($style)'

[c]
symbol = " "
style = "bg:color_blue"
format = '[[ $symbol ($version) ](fg:color_fg0 bg:color_blue)]($style)'

[rust]
symbol = ""
style = "bg:color_blue"
format = '[[ $symbol ($version) ](fg:color_fg0 bg:color_blue)]($style)'

[golang]
symbol = ""
style = "bg:color_blue"
format = '[[ $symbol ($version) ](fg:color_fg0 bg:color_blue)]($style)'

[php]
symbol = ""
style = "bg:color_blue"
format = '[[ $symbol ($version) ](fg:color_fg0 bg:color_blue)]($style)'

[time]
disabled = false
time_format = "%R" # Hour:Minute Format
style = "bg:color_bg1"
format = '[[  $time ](fg:color_fg0 bg:color_bg1)]($style)'

[line_break]
disabled = false

[character]
disabled = false
success_symbol = '[](bold fg:color_green)'
error_symbol = '[](bold fg:color_red)'
vimcmd_symbol = '[](bold fg:color_green)'
vimcmd_replace_one_symbol = '[](bold fg:color_purple)'
vimcmd_replace_symbol = '[](bold fg:color_purple)'
vimcmd_visual_symbol = '[](bold fg:color_yellow)'
```

#### Bat Configuration
```bash
# ~/.config/bat/config
--theme="Catppuccin-mocha"
--style="numbers,changes,header"
--italic-text=always
--paging=never
--wrap=never
```

#### Exa Colors
```fish
# ~/.config/fish/conf.d/10_theme_setup.fish
set -gx EXA_COLORS "uu=36:gu=37:sn=32:sb=32:da=34:ur=34:uw=35:ux=36:ue=36:gr=34:gw=35:gx=36:tr=34:tw=35:tx=36:"
```

#### FZF Theme
```fish
# ~/.config/fish/conf.d/10_theme_setup.fish
set -gx FZF_DEFAULT_OPTS "
    --color=bg+:#313244,bg:#1e1e2e,spinner:#f5e0dc,hl:#f38ba8
    --color=fg:#cdd6f4,header:#f38ba8,info:#cba6f7,pointer:#f5e0dc
    --color=marker:#f5e0dc,fg+:#cdd6f4,prompt:#cba6f7,hl+:#f38ba8
    --height 40% --layout=reverse --border --margin=1 --padding=1"
```

#### Ripgrep Configuration
```
# ~/.config/ripgrep/config  
--colors=line:fg:yellow
--colors=line:style:bold
--colors=path:fg:green
--colors=path:style:bold
--colors=match:fg:black
--colors=match:bg:yellow
--colors=match:style:nobold
--smart-case
--follow
--hidden
```

#### Git Delta Configuration
```
# ~/.gitconfig
[core]
    pager = delta

[interactive]
    diffFilter = delta --color-only

[delta]
    navigate = true
    light = false
    side-by-side = true
    line-numbers = true
    syntax-theme = Catppuccin-mocha
```

## Environment Variables Configuration

```fish
# ~/.config/fish/conf.d/11_env_vars.fish

# Editor preferences
set -gx EDITOR code
set -gx VISUAL code

# CLI tool preferences  
set -gx PAGER "bat --paging=always"
set -gx MANPAGER "sh -c 'col -bx | bat --language=man --plain'"

# FZF integration with other tools
set -gx FZF_DEFAULT_COMMAND 'fd --type f --hidden --follow --exclude .git'
set -gx FZF_CTRL_T_COMMAND "$FZF_DEFAULT_COMMAND"
set -gx FZF_ALT_C_COMMAND 'fd --type d --hidden --follow --exclude .git'

# Better history
set -gx HISTSIZE 10000
set -gx HISTFILESIZE 20000

# Development
set -gx NODE_ENV development
set -gx PYTHONPATH $HOME/.local/lib/python3.11/site-packages:$PYTHONPATH

# Path additions
fish_add_path $HOME/.local/bin
fish_add_path $HOME/.cargo/bin
fish_add_path $HOME/go/bin
fish_add_path $HOME/.npm-global/bin
```

## Claude Code Integration

### CLAUDE.md Configuration
```markdown
# Claude Code Configuration

## Tool Preferences

When working in this environment, please use these optimized CLI tools:

### File Operations
- Use `exa` instead of `ls` (with options: `exa -la --git --icons`)
- Use `bat` instead of `cat` (with options: `bat --style=numbers,changes,header`)
- Use `rg` instead of `grep` (with options: `rg --smart-case --follow --hidden`)
- Use `fd` instead of `find` (with options: `fd --type f --hidden --follow`)
- Use `z` instead of `cd` (zoxide integration)

### Git Operations  
- Use aliased git commands when possible: `gs` for status, `gl` for log, etc.
- Prefer `git push --force-with-lease` over `git push --force`
- Use `gh` CLI for GitHub operations when available

### Development
- Use `uv` for Python package management when available
- Prefer `npm run` scripts over direct command execution
- Use `docker-compose` commands with `dc` prefix

### Environment Integration
- All tools are themed with Catppuccin Mocha
- Fish shell with custom aliases is available
- Starship prompt provides git and language context

## Custom Functions Available

The following custom Fish functions are available:
- `fe` - Find and edit file with fzf
- `fcd` - Find and change directory with fzf  
- `rge` - Ripgrep with fzf preview and edit
- `killport` - Kill process on specific port
- `dcleanup` - Clean up Docker containers/images
- `ghcc` - Clone GitHub repo and cd into it

## Workflow Preferences

1. **File Search**: Use `fd` + `fzf` + `bat` pipeline for file discovery
2. **Content Search**: Use `rg` + `fzf` for content searching with preview
3. **Git Workflow**: Prefer short aliases (`gs`, `gst`, `gl`) and hub/gh integration
4. **Development**: Use npm/yarn aliases (`nr`, `ns`, `nt`) and custom functions

When suggesting commands, prefer the optimized versions and mention if a custom alias or function would be more efficient.
```

### Fish Functions for Claude Integration
```fish
# ~/.config/fish/conf.d/99_claude_integration.fish

# Set environment variable to indicate optimized tools are available
set -gx CLAUDE_OPTIMIZED_ENV 1

# Export tool preferences for Claude to detect
set -gx PREFERRED_LS "exa -la --git --icons"
set -gx PREFERRED_CAT "bat --style=numbers,changes,header"  
set -gx PREFERRED_GREP "rg --smart-case --follow --hidden"
set -gx PREFERRED_FIND "fd --type f --hidden --follow"
set -gx PREFERRED_CD "z"

# Function to show Claude available tools
function claude_tools
    echo "🎨 Optimized CLI Tools Available:"
    echo "  📁 Files: exa, bat, rg, fd, fzf, z"
    echo "  🔧 Git: Custom aliases (gs, gl, gc, etc.)"
    echo "  🐳 Docker: Aliases (d, dc, dcleanup)"
    echo "  🐙 GitHub: gh/hub CLI tools"
    echo "  ⚡ Functions: fe, fcd, rge, killport, ghcc"
    echo ""
    echo "🎯 Use 'alias' to see all available shortcuts"
    echo "🎨 Theme: Catppuccin Mocha across all tools"
end

# Function to validate environment setup
function claude_check
    echo "🔍 Checking optimized environment..."
    
    # Check critical tools
    set tools exa bat rg fd fzf z git gh docker
    for tool in $tools
        if command -v $tool >/dev/null
            echo "✅ $tool"
        else
            echo "❌ $tool (missing)"
        end
    end
    
    # Check theme setup
    if test -n "$CATPPUCCIN_TEXT"
        echo "✅ Catppuccin theme variables loaded"
    else
        echo "❌ Catppuccin theme variables not loaded"
    end
    
    # Check aliases
    if alias gs >/dev/null 2>&1
        echo "✅ Git aliases loaded"
    else
        echo "❌ Git aliases not loaded"
    end
end
```

## Installation and Setup Instructions

### 1. Install Missing Tools
```bash
# Install modern CLI tools
curl -sS https://starship.rs/install.sh | sh
cargo install exa bat fd-find ripgrep zoxide
curl -sSL https://install.python-poetry.org | python3 -

# Install GitHub CLI
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh

# Install Catppuccin themes
git clone https://github.com/catppuccin/bat.git
mkdir -p ~/.config/bat/themes
cp bat/*.tmTheme ~/.config/bat/themes/
bat cache --build
```

### 2. Configure Fish Shell
```bash
# Create configuration directories
mkdir -p ~/.config/fish/conf.d
mkdir -p ~/.config/fish/functions
mkdir -p ~/.config/fish/themes

# Copy all configuration files from this spec to their locations
# (Files listed in Architecture Strategy section)
```

### 3. Set up yadm
```bash
# Initialize yadm if not done
yadm init

# Add all configuration files
yadm add ~/.config/fish/
yadm add ~/.config/starship.toml
yadm add ~/.config/bat/
yadm add ~/.gitconfig
yadm add CLAUDE.md

# Commit initial configuration
yadm commit -m "Initial optimized CLI environment setup"
```

### 4. Test Installation
```bash
# Reload Fish configuration
source ~/.config/fish/config.fish

# Test tools and aliases
claude_check
claude_tools

# Test key workflows
gs    # Git status
l     # Enhanced ls
fe    # Find and edit
rge search_term  # Ripgrep with fzf
```

## Maintenance and Updates

### Adding New Aliases
1. Add to appropriate `~/.config/fish/conf.d/0X_aliases_*.fish` file
2. Reload: `source ~/.config/fish/config.fish`
3. Commit: `yadm add ~/.config/fish/conf.d/ && yadm commit -m "Add new aliases"`

### Theme Updates
1. Update colors in `~/.config/fish/conf.d/10_theme_setup.fish`
2. Update tool-specific configs
3. Test with `claude_check`
4. Commit changes with yadm

### Adding New Tools
1. Install tool
2. Add aliases to appropriate config file
3. Add tool-specific theme configuration
4. Update CLAUDE.md with new tool preferences
5. Update `claude_check` function to validate new tool

## Advanced Optimizations

### FZF Integration Enhancements
```fish
# Advanced FZF functions
function fzf_git_branch
    git branch --all | grep -v HEAD | sed 's/*//' | sed 's/remotes\/origin\///' | sort -u | fzf | xargs git checkout
end

function fzf_git_log
    git log --oneline --graph --color=always | fzf --ansi --preview 'echo {} | grep -o "[a-f0-9]\{7\}" | head -1 | xargs git show --color=always' | grep -o "[a-f0-9]\{7\}" | head -1 | xargs git show
end

function fzf_docker_container
    docker ps -a | fzf --header-lines=1 | awk '{print $1}' | xargs docker exec -it
end
```

### Performance Monitoring
```fish
# Add to ~/.config/fish/conf.d/11_env_vars.fish
function fish_greeting
    set_color $CATPPUCCIN_BLUE
    echo "🚀 Optimized CLI Environment Ready"
    set_color $CATPPUCCIN_TEXT
    echo "  $(date '+%A, %B %d %Y at %I:%M %p')"
    set_color $CATPPUCCIN_OVERLAY1
    echo "  💾 $(df -h / | awk 'NR==2{print $4}') disk free | ⚡ $(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//') load"
    set_color normal
    echo
end
```

## Troubleshooting

### Common Issues

1. **Colors not showing**: Check terminal supports 256 colors with `echo $TERM`
2. **Aliases not working**: Reload config with `source ~/.config/fish/config.fish`
3. **Git aliases conflicting**: Check existing git config with `git config --list`
4. **FZF not previewing**: Verify bat installation and PATH
5. **Starship not loading**: Check starship binary in PATH

### Reset Commands
```fish
# Reset fish configuration
rm -rf ~/.config/fish/
mkdir -p ~/.config/fish/conf.d

# Reset specific tool configs  
rm ~/.config/bat/config
rm ~/.config/starship.toml
rm ~/.gitconfig

# Restore from yadm
yadm checkout ~/.config/fish/
yadm checkout ~/.config/bat/
yadm checkout ~/.config/starship.toml
```

---

*This specification provides a complete, copy-paste ready configuration for an ultra-practical Linux coding environment optimized for visual appeal, productivity, and seamless Claude Code integration.*