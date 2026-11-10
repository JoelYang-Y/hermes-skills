#!/usr/bin/env bash
# 把本机 Hermes 技能库同步到 hermes-skills 仓库：镜像文件 + 重建 README 索引 + 提交 + 推送。
#
# 用法:
#   scripts/sync.sh                 # 同步 $HOME/.hermes/skills -> $HOME/hermes-skills 并推送
#   scripts/sync.sh --dry-run       # 只看会做什么，不落盘、不提交
#   scripts/sync.sh --no-push       # 落盘并提交，但不推送
#   scripts/sync.sh --verbose       # 附带每个分类的技能/文件数明细
#   scripts/sync.sh --src DIR --dst DIR [--dry-run] [--no-push] [-v]
set -euo pipefail

SRC="$HOME/.hermes/skills"
DST="$HOME/hermes-skills"
DRY=0
PUSH=1
VERBOSE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC="$2"; shift 2 ;;
    --dst) DST="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    --no-push) PUSH=0; shift ;;
    --verbose|-v) VERBOSE=1; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

SRC="${SRC/#\~/$HOME}"
DST="${DST/#\~/$HOME}"

[ -d "$SRC" ] || { echo "源目录不存在: $SRC" >&2; exit 1; }
[ -d "$DST" ] || { echo "目标目录不存在: $DST" >&2; exit 1; }
[ -d "$DST/.git" ] || { echo "目标目录不是 git 仓库: $DST" >&2; exit 1; }

# 注意：模式以 / 开头表示锚定传输根。
# 仓库自身的 README.md / .gitignore / scripts/ 必须显式排除，否则 --delete 会把它们删掉
# （源目录里没有这些文件），而技能内部的 scripts/ 子目录仍然正常同步。
RSYNC_ARGS=(
  -a --delete
  --exclude='/.git/'
  --exclude='/.gitignore'
  --exclude='/.gitattributes'
  --exclude='/README.md'
  --exclude='/scripts/'
  --exclude='.archive/'
  --exclude='.curator_backups/'
  --exclude='.hub/'
  --exclude='.locks/'
  --exclude='.curator_*'
  --exclude='.bundled_manifest'
  --exclude='.usage.json*'
  --exclude='.DS_Store'
)
[ "$DRY" = "1" ] && RSYNC_ARGS+=(--dry-run -v)

echo "== 同步 $SRC -> $DST"
rsync "${RSYNC_ARGS[@]}" "$SRC/" "$DST/"

# 清掉「无任何 SKILL.md」的空分类骨架：源端可能残留只剩 DESCRIPTION.md 的分类目录，
# git 虽不跟踪空目录，但带元数据的目录会作为空分类进入仓库。
REMOVED=()
while IFS= read -r d; do
  name="$(basename "$d")"
  if [ "$name" = "scripts" ]; then
    continue
  fi
  count="$(find "$d" -name SKILL.md | wc -l | tr -d ' ')"
  files="$(find "$d" -type f | wc -l | tr -d ' ')"
  if [ "$count" = "0" ] && [ "$files" -le 1 ]; then
    REMOVED+=("$name")
    if [ "$DRY" != "1" ]; then
      rm -rf "$d"
    fi
  elif [ "$VERBOSE" = "1" ]; then
    echo "   $name: ${count} 个 SKILL.md / ${files} 个文件"
  fi
done < <(find "$DST" -mindepth 1 -maxdepth 1 -type d -not -name '.*')
if [ "${#REMOVED[@]}" -gt 0 ]; then
  if [ "$DRY" = "1" ]; then
    echo "== [dry-run] 将移除 ${#REMOVED[@]} 个空分类骨架: ${REMOVED[*]}"
  else
    echo "== 移除 ${#REMOVED[@]} 个空分类骨架: ${REMOVED[*]}"
  fi
else
  echo "== 空分类骨架: 无"
fi

if [ "$DRY" = "1" ]; then
  echo "== dry-run 结束（未重建 README、未提交）"
  exit 0
fi

OUT="$(python3 "$DST/scripts/gen_readme.py" "$DST")"
echo "$OUT" | grep -v '^STAT ' || true
N_SKILL="$(echo "$OUT" | sed -n 's/^STAT skills=\([0-9]*\) cats=.*/\1/p')"
N_CAT="$(echo "$OUT" | sed -n 's/^STAT skills=[0-9]* cats=\([0-9]*\).*/\1/p')"
[ -n "$N_SKILL" ] || N_SKILL="$(find . -name SKILL.md -not -path './.git/*' | wc -l | tr -d ' ')"
[ -n "$N_CAT" ] || N_CAT="?"

cd "$DST"
if [ -z "$(git status --porcelain)" ]; then
  echo "== 无变更，跳过提交"
  exit 0
fi

git add -A
git commit -q -m "sync: 同步技能库（${N_SKILL} 个技能 / ${N_CAT} 个分类）"
echo "== 已提交: $(git log --oneline -1)"

if [ "$PUSH" = "1" ]; then
  git push -q origin HEAD
  echo "== 已推送: $(git rev-parse --short HEAD)"
fi
