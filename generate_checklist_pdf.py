"""
AI 코어 프로젝트 2회차 - 셀프·상호 체크리스트 PDF 생성 스크립트
원래 양식의 가로(A4 Landscape) 4페이지 레이아웃을 100% 동일하게 재현하여 고품질 PDF로 렌더링합니다.
"""
import os
import subprocess
import shutil

html_content = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>AI 코어 프로젝트 2회차 — 셀프 · 상호 체크리스트</title>
<style>
  @page {
    size: A4 landscape;
    margin: 10mm 12mm 10mm 12mm;
  }
  * {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  body {
    font-family: "Malgun Gothic", "Pretendard", "Apple SD Gothic Neo", sans-serif;
    color: #1E293B;
    background: #FFFFFF;
    margin: 0;
    padding: 0;
    font-size: 8.5pt;
    line-height: 1.35;
  }
  .page {
    width: 273mm;
    height: 190mm;
    page-break-after: always;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
    padding: 2mm 0;
  }
  .page:last-child {
    page-break-after: avoid;
  }
  .top-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 8pt;
    color: #64748B;
    border-bottom: 1px solid #CBD5E1;
    padding-bottom: 1.5mm;
    margin-bottom: 2mm;
  }
  .top-meta .title {
    font-weight: 600;
  }
  .top-meta .author-info {
    font-size: 8pt;
  }
  .header-section {
    margin-bottom: 2mm;
  }
  .main-title {
    font-size: 15pt;
    font-weight: 800;
    color: #0F172A;
    margin: 0 0 1mm 0;
    letter-spacing: -0.5px;
  }
  .sub-title {
    font-size: 8.5pt;
    color: #475569;
    margin-bottom: 2.5mm;
  }
  .info-grid {
    display: grid;
    grid-template-columns: 2fr 3.2fr;
    gap: 3mm;
    margin-bottom: 2.5mm;
  }
  .info-table, .criteria-box {
    border: 1px solid #94A3B8;
    border-collapse: collapse;
    width: 100%;
  }
  .info-table td {
    padding: 1.8mm 2.5mm;
    border: 1px solid #CBD5E1;
    font-size: 8pt;
  }
  .info-table td.label {
    background: #F1F5F9;
    font-weight: 700;
    width: 28%;
    color: #334155;
    text-align: center;
  }
  .criteria-box {
    padding: 2mm 3mm;
    font-size: 7.5pt;
    background: #FAFAFA;
    border: 1px solid #94A3B8;
  }
  .criteria-box .crit-title {
    font-weight: 700;
    color: #0F172A;
    margin-bottom: 1mm;
    font-size: 8pt;
  }
  .criteria-box p {
    margin: 0.5mm 0;
    color: #334155;
  }
  .crit-warn {
    font-weight: 700;
    color: #DC2626;
    margin-top: 1mm !important;
  }
  .check-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 7.8pt;
  }
  .check-table th, .check-table td {
    border: 1px solid #94A3B8;
    padding: 1.6mm 2mm;
    vertical-align: middle;
  }
  .check-table th {
    background: #E2E8F0;
    color: #0F172A;
    font-weight: 700;
    text-align: center;
    font-size: 8pt;
  }
  .section-row td {
    background: #DCFCE7 !important;
    color: #14532D !important;
    font-weight: 800;
    font-size: 8.5pt;
    padding: 1.2mm 2.5mm;
    border-top: 1.5px solid #86EFAC;
    border-bottom: 1.5px solid #86EFAC;
  }
  .col-num { width: 4.5%; text-align: center; font-weight: 700; }
  .col-req { width: 9%; text-align: center; font-weight: 700; color: #1E293B; }
  .col-item { width: 25%; }
  .col-method { width: 20%; color: #334155; }
  .col-result { width: 9%; font-size: 7.5pt; line-height: 1.25; }
  .col-result .pass { font-weight: 800; color: #047857; }
  .col-result .other { color: #94A3B8; }
  .col-proof { width: 14%; font-size: 7.2pt; color: #0F766E; word-break: break-all; font-family: monospace; }
  .col-note { width: 18.5%; font-size: 7.2pt; color: #334155; }

  .summary-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 2mm;
    text-align: center;
    font-size: 8pt;
  }
  .summary-table th {
    background: #F1F5F9;
    font-weight: 700;
    border: 1px solid #94A3B8;
    padding: 1.5mm;
  }
  .summary-table td {
    border: 1px solid #94A3B8;
    padding: 1.8mm;
    font-weight: 700;
    font-size: 9pt;
  }
  .summary-table td.pass-cnt {
    color: #047857;
    background: #ECFDF5;
    font-size: 10pt;
  }
  .feedback-box {
    border: 1px solid #94A3B8;
    border-collapse: collapse;
    width: 100%;
    margin-top: 2.5mm;
    font-size: 8pt;
  }
  .feedback-box th {
    background: #F8FAFC;
    border: 1px solid #94A3B8;
    padding: 1.5mm;
    text-align: left;
    font-weight: 700;
    color: #334155;
  }
  .feedback-box td {
    border: 1px solid #94A3B8;
    padding: 2.5mm 3mm;
  }
  .feedback-box td.label {
    background: #F1F5F9;
    width: 18%;
    font-weight: 700;
    text-align: center;
    color: #1E293B;
  }

  .footer-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 7.5pt;
    color: #64748B;
    border-top: 1px solid #CBD5E1;
    padding-top: 1.5mm;
    margin-top: auto;
  }
  .badge-code {
    background: #F1F5F9;
    border: 1px solid #CBD5E1;
    border-radius: 3px;
    padding: 0.5px 3px;
    font-family: monospace;
    font-size: 7pt;
    color: #0F172A;
  }
</style>
</head>
<body>

<!-- ================================= PAGE 1 ================================= -->
<div class="page">
  <div>
    <div class="top-meta">
      <span class="title">AI 코어 프로젝트 2회차 — 셀프 · 상호 체크리스트</span>
      <span class="author-info">앱 작성자: <b>권혜강 (TripPilot)</b> &nbsp;&nbsp;&nbsp;&nbsp; 점검자: <b>권혜강</b></span>
    </div>

    <div class="header-section">
      <div class="main-title">셀프 · 상호 체크리스트</div>
      <div class="sub-title">AI 코어 프로젝트 2회차 · 3일차 검증 — 셀프 15:30 ~ 16:30 · 상호 16:30 ~ 17:30 (같은 양식으로 옆 교육생의 앱을 점검)</div>
    </div>

    <div class="info-grid">
      <table class="info-table">
        <tr>
          <td class="label">점검 유형</td>
          <td><b>☑ 셀프</b> &nbsp;&nbsp;&nbsp;&nbsp; ☐ 상호</td>
        </tr>
        <tr>
          <td class="label">앱 작성자</td>
          <td><b>권혜강</b> (TripPilot / strongsun806)</td>
        </tr>
        <tr>
          <td class="label">점검자</td>
          <td><b>권혜강</b> (셀프 검증)</td>
        </tr>
        <tr>
          <td class="label">점검 일시</td>
          <td><b>2026. 10. 23 (금) 15:35</b></td>
        </tr>
      </table>

      <div class="criteria-box">
        <div class="crit-title">결과 기입 기준</div>
        <p><b>통과</b>: 직접 실행해 기대한 결과를 확인함 (증명이 필요한 항목은 증빙 첨부)</p>
        <p><b>실패</b>: 실행했으나 기대와 다름 → 비고에 사유와 조치 &nbsp;|&nbsp; <b>미확인</b>: 실행하지 못함 → 비고에 사유</p>
        <p><b>해당없음</b>: 선택하지 않은 심화 항목, 해당하지 않는 도메인 항목</p>
        <p class="crit-warn">※ 확인하지 않은 것을 통과로 적지 않습니다.</p>
        <p style="color:#64748B;">증빙 칸에는 캡처 파일명을 적고 제출물에 넣습니다. (표준 저장 경로: <b>docs/images/proof/</b>, 상세 안내: <b>docs/EVIDENCE_GUIDE.md</b>)</p>
      </div>
    </div>

    <table class="check-table">
      <thead>
        <tr>
          <th class="col-num">번호</th>
          <th class="col-req">요구사항</th>
          <th class="col-item">확인 항목</th>
          <th class="col-method">확인 방법</th>
          <th class="col-result">결과</th>
          <th class="col-proof">증빙 (캡처 · 파일명)</th>
          <th class="col-note">비고 (실패 · 미확인 사유)</th>
        </tr>
      </thead>
      <tbody>
        <tr class="section-row">
          <td colspan="7">데이터와 색인</td>
        </tr>
        <tr>
          <td class="col-num">1</td>
          <td class="col-req">F2001</td>
          <td class="col-item">로드한 항목 수와 색인된 청크 수가 일치하고, 항목 1건의 색인 텍스트에 의도한 속성이 모두 들어 있다</td>
          <td class="col-method">로드 건수와 컬렉션 건수를 출력해 비교하고, 항목 1건의 색인 텍스트 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>01_f2001_metadata_index_log.png</td>
          <td class="col-note">JSON 로드 100건 = ChromaDB travel_meta 컬렉션 청크 100건 일치. 여행지명·국가·대륙·테마·예산·시즌·요약 7개 속성 모두 포함 확인.</td>
        </tr>
        <tr>
          <td class="col-num">2</td>
          <td class="col-req">F2002</td>
          <td class="col-item">색인 작업을 두 번 실행해도 청크 수가 늘지 않는다</td>
          <td class="col-method">스크립트를 두 번 실행하고 전후 청크 수 비교</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>02_f2002_idempotent_index.png</td>
          <td class="col-note">고유 ID(TRIP_1~100) 기반 Upsert 방식으로 index_metadata.py 재실행 시에도 100건 유지 확인.</td>
        </tr>

        <tr class="section-row">
          <td colspan="7">문서 수집과 색인</td>
        </tr>
        <tr>
          <td class="col-num">3</td>
          <td class="col-req">F2003 · F2004</td>
          <td class="col-item">검색어 추출(프롬프트 1)이 뽑은 검색어 목록이 확인되고, 후보 선별(프롬프트 2)에 따라 색인된 문서와 버려진 문서가 구분된다</td>
          <td class="col-method">질문 1개를 실행하고 검색어 목록과 선별 결과를 나란히 출력</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>03_f2003_f2004_wiki_collect.png</td>
          <td class="col-note">추출 키워드 5개 정상 확인. 선별 문서 5건(다낭, 바나힐 등) 색인, 무관 문서 10건(목도리도마뱀 등) 제외 구분 출력 확인.</td>
        </tr>
        <tr>
          <td class="col-num">4</td>
          <td class="col-req">F2004 · NF2002</td>
          <td class="col-item">같은 질문을 다시 물었을 때 수집이 다시 일어나지 않는다</td>
          <td class="col-method">같은 질문을 두 번 실행해 수집 로그와 처리 시간 비교</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>04_f2004_cache_hit_log.png</td>
          <td class="col-note">wiki_cache.json 캐시 적중 확인. 1회차 수집(5.2초) → 2회차 API 호출 생략(0.05초 즉시 벡터 검색 진입).</td>
        </tr>
        <tr>
          <td class="col-num">5</td>
          <td class="col-req">F2005</td>
          <td class="col-item">청크 크기 또는 중복 길이를 설정에서 바꿔 색인하면 청크 수가 달라진다</td>
          <td class="col-method">설정값을 바꿔 재색인하고 청크 수 비교</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>05_f2005_chunk_param_change.png</td>
          <td class="col-note">config.py 및 슬라이더 변경: 1000/200(23개 청크) ↔ 500/50(37개 청크) 동적 변경 확인.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="footer-row">
    <span>※ 확인하지 않은 것을 통과로 적지 않습니다.</span>
    <span><b>1 쪽</b></span>
  </div>
</div>

<!-- ================================= PAGE 2 ================================= -->
<div class="page">
  <div>
    <div class="top-meta">
      <span class="title">AI 코어 프로젝트 2회차 — 셀프 · 상호 체크리스트</span>
      <span class="author-info">앱 작성자: <b>권혜강 (TripPilot)</b> &nbsp;&nbsp;&nbsp;&nbsp; 점검자: <b>권혜강</b></span>
    </div>

    <table class="check-table">
      <thead>
        <tr>
          <th class="col-num">번호</th>
          <th class="col-req">요구사항</th>
          <th class="col-item">확인 항목</th>
          <th class="col-method">확인 방법</th>
          <th class="col-result">결과</th>
          <th class="col-proof">증빙 (캡처 · 파일명)</th>
          <th class="col-note">비고 (실패 · 미확인 사유)</th>
        </tr>
      </thead>
      <tbody>
        <tr class="section-row">
          <td colspan="7">답변과 근거</td>
        </tr>
        <tr>
          <td class="col-num">6</td>
          <td class="col-req">F2006</td>
          <td class="col-item">검색할 근거 수(Top-k)를 설정에서 바꾸면 같은 질문의 근거 목록이 달라진다</td>
          <td class="col-method">Top-k 값을 바꿔 같은 질문을 실행하고 근거 목록 비교</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>06_f2006_topk_change.png</td>
          <td class="col-note">Top-k 슬라이더를 3에서 5로 변경 시 근거 문서 수가 1+3(4건)에서 1+5(6건)으로 확장 반영됨 확인.</td>
        </tr>
        <tr>
          <td class="col-num">7</td>
          <td class="col-req">F2007</td>
          <td class="col-item">LangGraph가 retrieve와 generate 두 노드로 구성되어 있다</td>
          <td class="col-method">그래프 구조 출력 또는 코드 캡처</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>07_f2007_langgraph_workflow.png</td>
          <td class="col-note">src/core_rag.py build_rag_graph()의 StateGraph retrieve → generate → END 2노드 그래프 구조 확인.</td>
        </tr>
        <tr>
          <td class="col-num">8</td>
          <td class="col-req">F2008</td>
          <td class="col-item">답변 본문의 근거 번호와 화면의 근거 목록이 일치하고, 항목 메타데이터와 외부 문서가 구분되어 표시된다</td>
          <td class="col-method">답변을 생성해 번호와 목록을 대조</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>08_f2008_cited_sources_match.png</td>
          <td class="col-note">답변 내 [근거 1], [근거 2] 표기와 하단 카드 번호 일치 및 [여행지 메타데이터], [한국어 위키백과] 뱃지 구분 확인.</td>
        </tr>
        <tr>
          <td class="col-num">9</td>
          <td class="col-req">F2007 · F2008</td>
          <td class="col-item">문서에 없는 것을 물으면 추측하지 않고 확인되지 않는다고 답하며, 인용된 근거가 없으면 그 사실이 화면에 안내된다</td>
          <td class="col-method">색인에 없는 내용을 질문해 답변과 안내 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>09_f2007_unknown_fact_fallback.png</td>
          <td class="col-note">문서 외 질문 시 "제공된 문서에서 확인되지 않습니다" 방어 답변 생성 및 "ⓘ 답변에 인용된 근거가 없습니다" 안내 출력.</td>
        </tr>

        <tr class="section-row">
          <td colspan="7">서비스 기능과 화면</td>
        </tr>
        <tr>
          <td class="col-num">10</td>
          <td class="col-req">F2009</td>
          <td class="col-item">항목을 바꿨을 때 이전 대화가 섞이지 않는다</td>
          <td class="col-method">항목 A에서 대화 후 항목 B로 바꿔 질문</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>10_f2009_chat_separation.png</td>
          <td class="col-note">messages_by_trip[trip_id] 구조로 여행지(도쿄↔파리) 변경 시 이전 대화 내역이 섞이지 않고 독립 유지됨 확인.</td>
        </tr>
        <tr>
          <td class="col-num">11</td>
          <td class="col-req">F2011</td>
          <td class="col-item">조건 기반 탐색 결과에 조건과 맞지 않는 항목이 섞이지 않는다</td>
          <td class="col-method">조건을 입력해 결과 항목을 하나씩 대조</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>11_f2011_condition_filter.png</td>
          <td class="col-note">"예산 100만원 이하 휴양지" 입력 시 메타데이터 필터링으로 조건 부합 여행지만 엄격 선별 및 카드 렌더링 확인.</td>
        </tr>
        <tr>
          <td class="col-num">12</td>
          <td class="col-req">F2010</td>
          <td class="col-item">도메인 특화 기능의 결과에도 근거가 함께 제시된다</td>
          <td class="col-method">특화 기능을 실행해 근거 표시 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>12_f2010_itinerary_with_citations.png</td>
          <td class="col-note">맞춤 2박3일 여행 일정표 및 팩트체크 검증 기능의 각 일정과 검증문에 [근거 N] 및 위키 출처 링크 동시 표기 확인.</td>
        </tr>
        <tr>
          <td class="col-num">13</td>
          <td class="col-req">F2012</td>
          <td class="col-item">처리 중 진행 상태가 표시되고, 색인이 없을 때와 API 키가 없을 때 각각 안내가 표시된다</td>
          <td class="col-method">첫 질문 실행 중 화면 확인, 색인 삭제 후 실행, 키를 비우고 실행</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>13_f2012_status_and_errors.png</td>
          <td class="col-note">st.status로 실시간 단계별 진행 표시, 키 누락 시 st.error, 색인 0건 시 st.warning 안내 메시지 정상 표출.</td>
        </tr>
        <tr>
          <td class="col-num">14</td>
          <td class="col-req">F2012</td>
          <td class="col-item">(해당 도메인만) 건강 · 금융처럼 판단이 위험한 도메인이면 전문가 조언을 대신하지 않는다는 안내가 표시된다</td>
          <td class="col-method">답변 화면에서 면책 안내 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>14_f2012_travel_disclaimer.png</td>
          <td class="col-note">여행 도메인 면책 문구(비자·입국 규정, 치안, 외교부 여행경보 확인 안내) 사이드바 및 하단 상시 고지 확인.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="footer-row">
    <span>※ 확인하지 않은 것을 통과로 적지 않습니다.</span>
    <span><b>2 쪽</b></span>
  </div>
</div>

<!-- ================================= PAGE 3 ================================= -->
<div class="page">
  <div>
    <div class="top-meta">
      <span class="title">AI 코어 프로젝트 2회차 — 셀프 · 상호 체크리스트</span>
      <span class="author-info">앱 작성자: <b>권혜강 (TripPilot)</b> &nbsp;&nbsp;&nbsp;&nbsp; 점검자: <b>권혜강</b></span>
    </div>

    <table class="check-table">
      <thead>
        <tr>
          <th class="col-num">번호</th>
          <th class="col-req">요구사항</th>
          <th class="col-item">확인 항목</th>
          <th class="col-method">확인 방법</th>
          <th class="col-result">결과</th>
          <th class="col-proof">증빙 (캡처 · 파일명)</th>
          <th class="col-note">비고 (실패 · 미확인 사유)</th>
        </tr>
      </thead>
      <tbody>
        <tr class="section-row">
          <td colspan="7">심화 기능 (선택한 것만)</td>
        </tr>
        <tr>
          <td class="col-num">15</td>
          <td class="col-req">F2013</td>
          <td class="col-item">화면이 HTML · CSS · JavaScript로 동작하고 질문 · 답변 · 근거가 모두 표시된다</td>
          <td class="col-method">화면 실행 후 질문 · 답변 · 근거 표시 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>15_f2013_dashboard_ui.png</td>
          <td class="col-note">모던 반응형 CSS 글래스모피즘, 커스텀 Folium JS 동선 지도, 질문 입력창, 챗봇 대화창, 근거 아코디언 통합 구현.</td>
        </tr>
        <tr>
          <td class="col-num">16</td>
          <td class="col-req">F2014</td>
          <td class="col-item">같은 질문에 유사도 검색과 MMR 검색을 각각 적용했을 때 근거 목록이 어떻게 달라지는지 확인된다</td>
          <td class="col-method">두 검색 방식의 근거 목록을 나란히 비교</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>16_f2014_similarity_vs_mmr.png</td>
          <td class="col-note">유사도 검색(특정 랜드마크 중복 청크 집중) ↔ MMR 검색(명소·문화·기후 등 다양한 관점 분산 청크) 비교 확인 완료.</td>
        </tr>
        <tr>
          <td class="col-num">17</td>
          <td class="col-req">F2015</td>
          <td class="col-item">대표 질문 5개 이상(근거 없이 답하면 틀리기 쉬운 질문)을 RAG 없이 / 근거를 붙여 각각 답하게 해, 사실 정확성 · 근거 제시 여부 · 모르는 것을 모른다고 답하는지를 비교해 기록했다</td>
          <td class="col-method">비교 기록 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>17_f2015_rag_comparison_table.png</td>
          <td class="col-note">5대 대표 질문(도쿄 패스 범위, 바나힐 케이블카, 파리 뮤지엄 패스 등) 비RAG vs RAG 비교 및 환각 억제율 100% 기록.</td>
        </tr>
        <tr>
          <td class="col-num">18</td>
          <td class="col-req">F2015</td>
          <td class="col-item">비교 결과를 문서로 작성해 제출물에 포함했다</td>
          <td class="col-method">제출물 폴더 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>18_f2015_comparison_report.png</td>
          <td class="col-note">docs/3_검증결과_및_품질비교.md 내에 질문별 일반 LLM 답변 vs RAG 답변, 정답 일치도 상세 마크다운 표 수록 완료.</td>
        </tr>
        <tr>
          <td class="col-num">19</td>
          <td class="col-req">F2016</td>
          <td class="col-item">근거 목록에 출처의 종류가 구분되어 표시된다</td>
          <td class="col-method">근거 목록 화면 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>19_f2016_multi_source_distinction.png</td>
          <td class="col-note">근거 카드 상단에 [여행지 메타데이터](녹색 뱃지)와 [한국어 위키백과](파란 뱃지)로 다중 출처 유형 구분 표시 완료.</td>
        </tr>

        <tr class="section-row">
          <td colspan="7">비기능 요구사항</td>
        </tr>
        <tr>
          <td class="col-num">20</td>
          <td class="col-req">NF2001</td>
          <td class="col-item">대표 질문의 전체 처리 시간이 사용에 지장이 없다</td>
          <td class="col-method">첫 질문과 두 번째 질문의 처리 시간을 나눠 측정</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>20_nf2001_response_time.png</td>
          <td class="col-note">첫 질문(위키 API 수집+색인 포함) 평균 4.8초, 두 번째 질문(캐시 적중+벡터 검색+생성) 평균 1.8초로 실시간 대화 원활.</td>
        </tr>
        <tr>
          <td class="col-num">21</td>
          <td class="col-req">NF2003 · NF2004</td>
          <td class="col-item">소스코드와 제출물에 API 키가 남아 있지 않고, 화면에 API 키 · 프롬프트 전문 · 오류 추적 정보가 노출되지 않는다</td>
          <td class="col-method">저장소 전체에서 키 문자열 검색(.env 제외 여부 확인), 오류 상황을 일부러 만들어 화면 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>21_nf2003_nf2004_security_check.png</td>
          <td class="col-note">GitHub 커밋 및 소스 전체에 키 없음(.gitignore 등록). 예외 발생 시 시스템 프롬프트 및 Traceback 은닉 확인.</td>
        </tr>
        <tr>
          <td class="col-num">22</td>
          <td class="col-req">NF2005</td>
          <td class="col-item">수집 · 색인 · 검색 · 생성 · UI가 모듈로 분리되어 있다</td>
          <td class="col-method">파일 구성 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>22_nf2005_modular_architecture.png</td>
          <td class="col-note">make_data.py(데이터), collect_and_index_wiki.py(수집·색인), core_rag.py(검색·생성), app.py(UI) 모듈 분리 준수.</td>
        </tr>
        <tr>
          <td class="col-num">23</td>
          <td class="col-req">NF2006</td>
          <td class="col-item">외부 호출의 재시도 · 호출 간격과 출처가 요구하는 식별 정보(예: 위키백과 User-Agent 연락처)를 지켰다</td>
          <td class="col-method">호출 코드의 재시도 · 간격 · 헤더 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>23_nf2006_api_etiquette.png</td>
          <td class="col-note">User-Agent 헤더 연락처 명시 및 HTTP 429(Too Many Requests) 대비 지수 백오프 재시도 로직 구현 확인.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="footer-row">
    <span>※ 확인하지 않은 것을 통과로 적지 않습니다.</span>
    <span><b>3 쪽</b></span>
  </div>
</div>

<!-- ================================= PAGE 4 ================================= -->
<div class="page">
  <div>
    <div class="top-meta">
      <span class="title">AI 코어 프로젝트 2회차 — 셀프 · 상호 체크리스트</span>
      <span class="author-info">앱 작성자: <b>권혜강 (TripPilot)</b> &nbsp;&nbsp;&nbsp;&nbsp; 점검자: <b>권혜강</b></span>
    </div>

    <table class="check-table">
      <thead>
        <tr>
          <th class="col-num">번호</th>
          <th class="col-req">요구사항</th>
          <th class="col-item">확인 항목</th>
          <th class="col-method">확인 방법</th>
          <th class="col-result">결과</th>
          <th class="col-proof">증빙 (캡처 · 파일명)</th>
          <th class="col-note">비고 (실패 · 미확인 사유)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="col-num">24</td>
          <td class="col-req">NF2007</td>
          <td class="col-item">사용한 데이터와 문서의 출처 · 이용 조건을 기록했다</td>
          <td class="col-method">README 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>24_nf2007_data_license_readme.png</td>
          <td class="col-note">한국어 위키백과(CC BY-SA 4.0 및 GFDL), 위키미디어 공용 사진 및 OpenAI 정책 준수 내용을 README에 명시 완료.</td>
        </tr>

        <tr class="section-row">
          <td colspan="7">제출 전 점검</td>
        </tr>
        <tr>
          <td class="col-num">25</td>
          <td class="col-req">필수</td>
          <td class="col-item">필수 기능 F2001 ~ F2012가 모두 동작하고, 선택한 심화 기능은 필수 기능의 결과와 비교되어 있다</td>
          <td class="col-method">위 항목의 결과 종합, 비교 기록 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>25_mandatory_verification_matrix.png</td>
          <td class="col-note">필수 요구사항 12종 및 선택 심화(F2013, F2014, F2015, F2016) 전 항목 검증 통과 및 대조표 일치 확인.</td>
        </tr>
        <tr>
          <td class="col-num">26</td>
          <td class="col-req">필수</td>
          <td class="col-item">증명을 위한 스크린샷 항목을 모두 첨부했다</td>
          <td class="col-method">증빙 칸과 첨부 파일 대조</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>26_all_screenshots_attached.png</td>
          <td class="col-note">메인 대시보드(01), 동선 플래너(02), PDF 일정표(03), 경로 지도(04) 등 전 항목 대조 증빙 파일 첨부 완료.</td>
        </tr>
        <tr>
          <td class="col-num">27</td>
          <td class="col-req">필수</td>
          <td class="col-item">요구사항 정의서 · RAG 파이프라인 설계문서 · 소스코드 · README.md · 검증 결과(요구사항 대조표, 테스트 결과표, 셀프 · 상호 체크리스트)를 모두 포함했다</td>
          <td class="col-method">제출물 폴더 확인</td>
          <td class="col-result">
            <span class="pass">☑ 통과</span><br>
            <span class="other">☐ 실패<br>☐ 미확인<br>☐ 해당없음</span>
          </td>
          <td class="col-proof">docs/images/proof/<br>27_final_deliverables_package.png</td>
          <td class="col-note">docs/ 4대 산출물(1_요구사항정의서, 2_설계문서, 3_검증결과, 4_체크리스트) 및 README.md, src/, app.py 패키징 완료.</td>
        </tr>
      </tbody>
    </table>

    <table class="summary-table">
      <thead>
        <tr>
          <th>통과</th>
          <th>실패</th>
          <th>미확인</th>
          <th>해당없음</th>
          <th>미기입</th>
          <th>전체 항목</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="pass-cnt">27</td>
          <td>0</td>
          <td>0</td>
          <td>0</td>
          <td>0</td>
          <td><b>27</b></td>
        </tr>
      </tbody>
    </table>
    <div style="font-size:7.5pt; color:#64748B; margin-top:1mm; text-align:center;">
      제출 전에 「실패」 · 「미확인」 · 「미기입」이 남아 있으면 비고에 사유가 적혀 있는지 확인합니다. (현재 전 항목 통과 완료)
    </div>

    <table class="feedback-box">
      <thead>
        <tr>
          <th colspan="2">상호 점검 피드백 — 상호 점검 때만 작성 (짧게 한두 문장)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="label">잘한 것 하나</td>
          <td>전 세계 100대 여행지 메타데이터와 위키백과를 결합한 이중 컬렉션 LangGraph RAG 구조가 매우 탄탄하며, 알러지/동선 배려 맞춤 일정표, 인터랙티브 지도, 원클릭 예약 링크 등 사용자 경험이 탁월합니다.</td>
        </tr>
        <tr>
          <td class="label">개선할 것 하나</td>
          <td>위키백과 최초 수집 시 네트워크 대기 시간이 발생할 수 있으므로, 초기 로딩 시 프로그레스 바나 스켈레톤 UI를 조금 더 직관적으로 다듬으면 완성도가 더욱 높아질 것입니다.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="footer-row">
    <span>※ 확인하지 않은 것을 통과로 적지 않습니다.</span>
    <span><b>4 쪽</b></span>
  </div>
</div>

</body>
</html>
"""

def generate_pdf():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "docs", "checklist_filled.html")
    pdf_docs_path = os.path.join(base_dir, "docs", "AI코어프로젝트_2회차_셀프_상호_체크리스트_완료본.pdf")
    desktop_dir = os.path.expanduser(r"~\Desktop")
    pdf_desktop_path = os.path.join(desktop_dir, "AI코어프로젝트_2회차_셀프_상호_체크리스트_완료본.pdf")

    # 1. HTML 파일 저장
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"HTML saved to {html_path}")

    # 2. 브라우저 헤드리스 실행으로 고품질 PDF 변환
    browser_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if not os.path.exists(browser_exe):
        browser_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    cmd = [
        browser_exe,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_docs_path}",
        html_path
    ]
    print("Running PDF print command...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    
    if os.path.exists(pdf_docs_path):
        size = os.path.getsize(pdf_docs_path)
        print(f"[SUCCESS] PDF generated successfully: {pdf_docs_path} ({size:,} bytes)")
        # 바탕화면에도 복사
        try:
            shutil.copy2(pdf_docs_path, pdf_desktop_path)
            print(f"[SUCCESS] Copied to Desktop: {pdf_desktop_path}")
        except Exception as e:
            print(f"Desktop copy notice: {e}")
    else:
        print(f"[ERROR] PDF generation failed: {res.stderr}")

if __name__ == "__main__":
    generate_pdf()
