"""Shell completion script generation for ccpkg (Contract: §3 adoption features).

`ccpkg completions <zsh|bash>` prints a completion script to stdout; the user
installs it however their shell expects (we never edit their rc). The scripts
offer the verb / sub-verb tree -- derived by introspecting the live argparse
parser so it cannot drift from the real CLI -- plus dynamic values the script
fetches at TAB-time via `ccpkg completions items`.

Stdlib only, Python 3.9.
"""

import argparse
from typing import Dict, List, Optional

from . import config
from . import manifest

# apply's preset words are plain positionals (not argparse choices), so they are
# the one value-set we cannot introspect. Keep in sync with cli.main's dispatch.
APPLY_PRESETS = ("minimal", "recommended", "everything")

# completions' own value words (this verb's positional is freeform in argparse).
COMPLETIONS_VALUES = ("zsh", "bash", "items", "templates", "mcp")


def _subparsers_action(parser):
    # type: (argparse.ArgumentParser) -> Optional[argparse._SubParsersAction]
    for action in parser._actions:  # noqa: SLF001 - argparse has no public API for this
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def command_tree():
    # type: () -> Dict[str, List[str]]
    """{verb: [sub-verbs...]} introspected from the live parser, plus the two
    hardcoded value-sets (apply presets, completions words). Sub-verb lists are
    empty for verbs that take no sub-command."""
    from . import cli  # local import: cli imports nothing from here

    parser = cli._build_parser()
    top = _subparsers_action(parser)
    tree = {}  # type: Dict[str, List[str]]
    if top is None:
        return tree
    for verb, subparser in top.choices.items():
        sub = _subparsers_action(subparser)
        tree[verb] = list(sub.choices.keys()) if sub is not None else []
    return tree


def list_items(root=None):
    # type: (Optional[str]) -> List[str]
    """Every manifest item path, sorted + de-duped. The dynamic feed for
    `status diff <TAB>`. Resolves the manifest from the asset root by default."""
    root = root or config.repo_root()
    try:
        items = manifest.parse(config.manifest_path(root))
    except (OSError, ValueError):
        return []
    return sorted({item.path for item in items})


def _verbs():
    # type: () -> List[str]
    return list(command_tree().keys())


def _subverbs(verb):
    # type: (str) -> List[str]
    return command_tree().get(verb, [])


def bash_script():
    # type: () -> str
    tree = command_tree()
    verbs = " ".join(tree.keys())
    status_subs = " ".join(tree.get("status", []))
    new_subs = " ".join(tree.get("new", []))
    mcp_subs = " ".join(tree.get("mcp", []))
    suggest_subs = " ".join(tree.get("suggest", []))
    gallery_subs = " ".join(tree.get("gallery", []))
    presets = " ".join(APPLY_PRESETS)
    completions_vals = " ".join(COMPLETIONS_VALUES)
    return """\
# ccpkg bash completion. Install: ccpkg completions bash > /etc/bash_completion.d/ccpkg
# or add `source <(ccpkg completions bash)` to your ~/.bashrc.
_ccpkg() {{
    local cur verb
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "{verbs}" -- "$cur") )
        return
    fi
    verb="${{COMP_WORDS[1]}}"
    case "$verb" in
        apply)
            [ "$COMP_CWORD" -eq 2 ] && COMPREPLY=( $(compgen -W "{presets} $(ccpkg completions templates 2>/dev/null)" -- "$cur") )
            ;;
        status)
            if [ "$COMP_CWORD" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "{status_subs}" -- "$cur") )
            elif [ "$COMP_CWORD" -eq 3 ] && [ "${{COMP_WORDS[2]}}" = "diff" ]; then
                COMPREPLY=( $(compgen -W "$(ccpkg completions items 2>/dev/null)" -- "$cur") )
            fi
            ;;
        new)
            [ "$COMP_CWORD" -eq 2 ] && COMPREPLY=( $(compgen -W "{new_subs}" -- "$cur") )
            ;;
        suggest)
            [ "$COMP_CWORD" -eq 2 ] && COMPREPLY=( $(compgen -W "{suggest_subs}" -- "$cur") )
            ;;
        gallery)
            [ "$COMP_CWORD" -eq 2 ] && COMPREPLY=( $(compgen -W "{gallery_subs}" -- "$cur") )
            ;;
        mcp)
            if [ "$COMP_CWORD" -eq 2 ]; then
                COMPREPLY=( $(compgen -W "{mcp_subs}" -- "$cur") )
            elif [ "$COMP_CWORD" -ge 3 ] && [ "${{COMP_WORDS[2]}}" = "add" ]; then
                COMPREPLY=( $(compgen -W "$(ccpkg completions mcp 2>/dev/null)" -- "$cur") )
            fi
            ;;
        completions)
            [ "$COMP_CWORD" -eq 2 ] && COMPREPLY=( $(compgen -W "{completions_vals}" -- "$cur") )
            ;;
    esac
}}
complete -F _ccpkg ccpkg
""".format(verbs=verbs, presets=presets, status_subs=status_subs,
           new_subs=new_subs, mcp_subs=mcp_subs, suggest_subs=suggest_subs,
           gallery_subs=gallery_subs, completions_vals=completions_vals)


def zsh_script():
    # type: () -> str
    tree = command_tree()
    verbs = " ".join(tree.keys())
    status_subs = " ".join(tree.get("status", []))
    new_subs = " ".join(tree.get("new", []))
    mcp_subs = " ".join(tree.get("mcp", []))
    suggest_subs = " ".join(tree.get("suggest", []))
    gallery_subs = " ".join(tree.get("gallery", []))
    presets = " ".join(APPLY_PRESETS)
    completions_vals = " ".join(COMPLETIONS_VALUES)
    return """\
#compdef ccpkg
# ccpkg zsh completion. Install: ccpkg completions zsh > ~/.zsh/completions/_ccpkg
# (with that dir on your $fpath), then restart your shell.
_ccpkg() {{
    if (( CURRENT == 2 )); then
        compadd -- {verbs}
        return
    fi
    local verb=${{words[2]}}
    case $verb in
        apply)
            (( CURRENT == 3 )) && compadd -- {presets} ${{(f)"$(ccpkg completions templates 2>/dev/null)"}}
            ;;
        status)
            if (( CURRENT == 3 )); then
                compadd -- {status_subs}
            elif (( CURRENT == 4 )) && [[ ${{words[3]}} == diff ]]; then
                compadd -- ${{(f)"$(ccpkg completions items 2>/dev/null)"}}
            fi
            ;;
        new)
            (( CURRENT == 3 )) && compadd -- {new_subs}
            ;;
        suggest)
            (( CURRENT == 3 )) && compadd -- {suggest_subs}
            ;;
        gallery)
            (( CURRENT == 3 )) && compadd -- {gallery_subs}
            ;;
        mcp)
            if (( CURRENT == 3 )); then
                compadd -- {mcp_subs}
            elif (( CURRENT >= 4 )) && [[ ${{words[3]}} == add ]]; then
                compadd -- ${{(f)"$(ccpkg completions mcp 2>/dev/null)"}}
            fi
            ;;
        completions)
            (( CURRENT == 3 )) && compadd -- {completions_vals}
            ;;
    esac
}}
_ccpkg "$@"
""".format(verbs=verbs, presets=presets, status_subs=status_subs,
           new_subs=new_subs, mcp_subs=mcp_subs, suggest_subs=suggest_subs,
           gallery_subs=gallery_subs, completions_vals=completions_vals)


def render(shell):
    # type: (str) -> Optional[str]
    """Script text for a shell name, or None if unsupported."""
    if shell == "zsh":
        return zsh_script()
    if shell == "bash":
        return bash_script()
    return None
