#!/bin/sh
# 업무용(~/.claude-work) 세션을 seCall `--auto`가 보게 하는 depth1 심링크를 갱신한다.
#
# 왜 필요한가 (제약 상세는 README.md 「주의」의 "업무용 세션 수집" 항목):
#   1. seCall의 세션 포맷 감지는 경로 문자열 기반이라 경로에 `/.claude/projects/`가
#      있어야 한다 — `~/.claude-work/projects/…`는 unknown session format으로 실패.
#   2. `--auto` 스캔 깊이는 `projects/<프로젝트디렉토리>/*.jsonl` 딱 한 단계다.
#   3. 심링크는 그 depth 1 자리에서만 따라간다.
#   => 업무용 프로젝트 디렉토리를 개인용과 같은 depth의 형제로 걸어줘야 수집된다.
#      디렉토리명은 겉치레다 — seCall은 프로젝트명을 jsonl 안의 cwd에서 뽑는다.
#
# launchd 08:40 실행 (스크럽 08:45 → sync 09:00 보다 앞). 로컬 파일만 만지므로
# iCloud TCC/FDA와 무관하고, 그래서 sync/reindex/wiki와 달리 /bin/sh 래퍼를 써도 된다.
#
# ⚠️ 한시적 — 2026-08-11에 설정을 ~/.claude로 통일하면 아래를 전부 제거할 것:
#      launchctl bootout gui/$(id -u)/com.max.claude-work-links
#      rm -f ~/Library/LaunchAgents/com.max.claude-work-links.plist
#      rm -f ~/.claude/projects/_work--*
#      git rm scripts/link_work_projects.sh launchd/com.max.claude-work-links.plist
#    통일 후엔 업무 세션이 ~/.claude/projects에 직접 쌓이므로 링크가 불필요해진다.
#    (scrub_secrets.py의 DEFAULT_ROOTS에서 ~/.claude-work/projects 항목도 같이 정리)
set -eu

WORK="$HOME/.claude-work/projects"
DEST="$HOME/.claude/projects"

if [ ! -d "$WORK" ]; then
	echo "work projects dir 없음, 할 일 없음: $WORK"
	exit 0
fi

# 업무용 프로젝트 디렉토리가 사라진 경우 남는 끊어진 링크 정리.
# glob이 하나도 안 맞으면 패턴 문자열 그대로 들어오므로 -L로 걸러낸다.
for link in "$DEST"/_work--*; do
	[ -L "$link" ] || continue
	[ -e "$link" ] && continue
	rm -f "$link"
	echo "끊어진 링크 제거: $(basename "$link")"
done

linked=0
for dir in "$WORK"/*/; do
	[ -d "$dir" ] || continue
	name=$(basename "$dir")
	ln -sfn "$WORK/$name" "$DEST/_work--$name"
	linked=$((linked + 1))
done

# ${linked} 중괄호 필수 — 한글이 바로 뒤에 붙으면 bash가 변수명의 일부로 먹는다.
echo "[link-work-projects] ${linked}개 업무 프로젝트 디렉토리 링크됨"
