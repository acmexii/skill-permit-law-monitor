# Permit Law Monitor (인허가 법령 모니터)

기업 인허가 유형을 주면 관련 법령집을 국가법령정보센터에서 내려받아 조문 색인을 만들고, 소관부처 공지를 찾아 주며, 조문 근거 Q&A와 매일 아침 개정·공지 보고(채팅+메일)까지 세팅하는 에이전트 스킬입니다.

## 구성

- `SKILL.md` — 워크플로(범위 확인 → 법령·별표 PDF 다운로드 → 텍스트·조문 색인 → 소관부처 공지 → 일일 모니터링·메일)
- `scripts/poll.py` — law.go.kr 현행 버전 비교, 조문 단위 diff, 소관부처 게시판 신규 감지 (위험물안전관리법·소방청 설정 예시)
- `references/INDEX_example.md` — 조문 색인 예시 (위험물안전관리법령)
- `references/mail_template_example.html` — 일일 보고 메일 예시

## 설치

```sh
git clone https://github.com/acmexii/skill-permit-law-monitor.git ~/.codex/skills/permit-law-monitor
```

## 사용

> $permit-law-monitor 로 "유해화학물질 영업허가" 법령집 받고, 매일 9시에 개정 사항 보고해 줘.

## 요구 사항

Python 3, `pdftotext`(poppler-utils), 브라우저 자동화(law.go.kr 다운로드용). law.go.kr Open API는 IP 등록 시 대체 가능.

※ 법률 자문이 아닌 정보 제공용입니다.
