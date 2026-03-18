"""
Allure TestOps → PDF exporter
Для каждого тест-кейса запрашивает ВСЕ эндпоинты, которые UI вызывает
при открытии страницы /project/{p}/test-cases/{id}:

  GET /api/rs/testcase/{id}                — основная карточка
  GET /api/rs/testcase/{id}/attachment     — вложения (Attachments)
  GET /api/rs/testcase/{id}/result         — история запусков (Results)
  GET /api/rs/testcase/{id}/issue          — связанные задачи (Issues)
"""

import requests
import json
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
import html as _html
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class AllureExporter:

    # ── Config ────────────────────────────────────────────────────────────────

    def __init__(self, config_path: str = "config.json"):
        self.cfg = self._load_config(config_path)
        self.headers = {
            "Authorization": f"Api-Token {self.cfg['api_token']}",
            "Content-Type": "application/json",
        }
        self.base = self.cfg["allure_url"].rstrip("/")
        self.out  = Path(self.cfg["output_dir"])
        self.out.mkdir(parents=True, exist_ok=True)

    def _load_config(self, path: str) -> Dict:
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            for k in ("api_token", "allure_url", "test_plan_id"):
                if k not in cfg:
                    raise ValueError(f"Нет поля '{k}' в {path}")
            log.info("Конфиг загружен: %s", path)
            return cfg
        except FileNotFoundError:
            log.error("Файл не найден: %s", path); sys.exit(1)
        except json.JSONDecodeError:
            log.error("Ошибка JSON: %s", path); sys.exit(1)

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, ep: str, params: Optional[Dict] = None) -> Optional[Any]:
        url = f"{self.base}/api/rs/{ep.lstrip('/')}"
        try:
            r = requests.get(url, headers=self.headers,
                             params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                log.debug("HTTP 404 (нет данных)  %s", ep)
            else:
                log.warning("HTTP %s  %s", r.status_code, ep)
            return None
        except requests.RequestException as e:
            log.error("Ошибка сети: %s", e)
            return None

    def _pages(self, ep: str, params: Dict) -> List[Dict]:
        out, page = [], 0
        sz = params.get("pageSize", 100)
        while True:
            d = self._get(ep, {**params, "page": page, "pageSize": sz})
            if not d:
                break
            if isinstance(d, dict) and "content" in d:
                chunk = d["content"]
                out.extend(chunk)
                if d.get("last", True) or len(chunk) < sz:
                    break
                page += 1
            elif isinstance(d, list):
                out.extend(d); break
            else:
                break
        return out

    # ── Collect IDs via treeSelection ─────────────────────────────────────────

    def _collect_ids(self, plan_id: int, proj: int) -> List[int]:
        plan = self._get(f"testplan/{plan_id}")
        if not plan:
            return []
        sel     = plan.get("treeSelection", {})
        tree_id = plan.get("tree", {}).get("id")
        g_inc   = sel.get("groupsInclude", [])
        l_inc   = sel.get("leafsInclude",  [])
        l_exc   = set(sel.get("leafsExclude", []))

        log.info("treeSelection: %d групп / %d листов / %d исключений",
                 len(g_inc), len(l_inc), len(l_exc))

        seen: set = set()
        ids:  List[int] = []

        for path in g_inc:
            gid = path[-1] if path else None
            if gid is None:
                continue
            log.info("Группа %s (treeId=%s)…", gid, tree_id)
            items = self._pages("testcase", {
                "projectId": proj,
                "treeId":    tree_id,
                "groupId":   gid,
                "pageSize":  100,
            })
            added = 0
            for tc in items:
                tid = tc.get("id")
                if tid and tid not in seen and tid not in l_exc:
                    seen.add(tid); ids.append(tid); added += 1
            log.info("  -> %d кейсов", added)

        for tid in l_inc:
            if tid not in seen and tid not in l_exc:
                seen.add(tid); ids.append(tid)

        log.info("Итого id: %d", len(ids))
        return ids

    # ── Fetch ONE test-case: all UI tabs ──────────────────────────────────────

    def _fetch_full(self, tc_id: int, proj: int) -> Optional[Dict]:
        """
        Запрашивает все данные, которые UI показывает на странице кейса:

        Вкладка Overview (основная карточка):
          /api/rs/testcase/{id}
            name, description, precondition,
            steps[]{name, expectedResult, steps[]},
            tags[], links[], status, workflow,
            customFields[], parameters[],
            automated, external, duration,
            createdBy/Date, lastModifiedBy/Date

        Вкладка Attachments:
          /api/rs/testcase/{id}/attachment
            [{id, name, contentType, size}]

        Вкладка Results (история запусков):
          /api/rs/testcase/{id}/result
            [{status, start, stop, launchName, …}]

        Вкладка Issues (связанные задачи):
          /api/rs/testcase/{id}/issue
            [{id, name, url, type}]
        """
        # 1. Основная карточка
        tc = self._get(f"testcase/{tc_id}", {"projectId": proj})
        if not tc:
            log.warning("Кейс %d недоступен", tc_id)
            return None

        # 2. Вложения — правильный эндпоинт: /api/rs/attachment?testCaseId=
        raw = self._get("attachment",
                        {"testCaseId": tc_id, "projectId": proj, "pageSize": 200})
        tc["_attachments"] = (
            raw.get("content", []) if isinstance(raw, dict) else
            raw if isinstance(raw, list) else []
        )

        # 3. История запусков (последние 10)
        raw = self._get(f"testcase/{tc_id}/result",
                        {"projectId": proj, "pageSize": 10})
        tc["_results"] = (
            raw.get("content", []) if isinstance(raw, dict) else
            raw if isinstance(raw, list) else []
        )

        # 4. Связанные задачи
        raw = self._get(f"testcase/{tc_id}/issue",
                        {"projectId": proj})
        if isinstance(raw, dict):
            tc["_issues"] = raw.get("content",
                             raw.get("issues",
                             raw.get("items", [])))
        elif isinstance(raw, list):
            tc["_issues"] = raw
        else:
            tc["_issues"] = []

        return tc

    # ── Group by section ──────────────────────────────────────────────────────

    @staticmethod
    def _sections(cases: List[Dict]) -> List[Dict]:
        secs: Dict[str, Dict] = {}
        for tc in cases:
            tags = tc.get("tags") or []
            if tags:
                name = tags[0].get("name", "Общее")
            else:
                m = re.match(r"\[([^\]]+)\]", tc.get("name", ""))
                name = m.group(1) if m else "Общее"
            secs.setdefault(name, {"name": name, "testCases": []})
            secs[name]["testCases"].append(tc)

        def key(s):
            n = s["name"]
            if re.match(r"^NTPR", n): return (0, n)
            if n.startswith("["):      return (1, n)
            return (2, n)

        result = sorted(secs.values(), key=key)
        for s in result:
            s["testCases"].sort(key=lambda x: (x.get("name",""), x.get("id",0)))
        return result

    # ── Text helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _plain(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[изображение: \1]", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
        text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
        text = re.sub(r"_{1,2}([^_\n]+)_{1,2}", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        for ent, ch in [("&nbsp;"," "),("&amp;","&"),("&lt;","<"),
                        ("&gt;",">"),("&quot;",'"'),("&#39;","'")]:
            text = text.replace(ent, ch)
        return text.strip()

    @staticmethod
    def _ts(ms) -> str:
        if not ms:
            return ""
        try:
            return datetime.fromtimestamp(int(ms)/1000).strftime("%d.%m.%Y %H:%M")
        except Exception:
            return str(ms)

    @staticmethod
    def _dur(ms) -> str:
        if not ms or int(ms) <= 0:
            return ""
        s = int(ms) // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h}ч {m}м {s}с" if h else (f"{m}м {s}с" if m else f"{s}с")

    # ── PDF ───────────────────────────────────────────────────────────────────

    def _setup_fonts(self):
        fn, fb = "Helvetica", "Helvetica-Bold"
        for path, name, bpath, bname in [
            ("C:\\Windows\\Fonts\\arial.ttf",  "Arial",
             "C:\\Windows\\Fonts\\arialbd.ttf", "Arial-Bold"),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      "DejaVu",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVu-Bold"),
            ("fonts/DejaVuSans.ttf",      "DejaVu",
             "fonts/DejaVuSans-Bold.ttf", "DejaVu-Bold"),
        ]:
            try:
                pdfmetrics.registerFont(TTFont(name,  path))
                pdfmetrics.registerFont(TTFont(bname, bpath))
                fn, fb = name, bname
                log.info("Шрифт: %s", name)
                break
            except Exception:
                pass
        return fn, fb

    def _render_steps(self, steps, story, s_step, s_res, depth=0):
        pad = "&nbsp;" * (depth * 6)
        for i, step in enumerate(steps, 1):
            name     = self._plain(step.get("name", "") or "")
            expected = self._plain(step.get("expectedResult", "") or "")
            children = step.get("steps", []) or []
            si = ParagraphStyle(f"si{depth}_{i}", parent=s_step,
                                leftIndent=s_step.leftIndent + depth*6)
            sr = ParagraphStyle(f"sr{depth}_{i}", parent=s_res,
                                leftIndent=s_res.leftIndent  + depth*6)
            if name:
                story.append(Paragraph(
                    f"{pad}<b>{i}.</b> {_html.escape(name)}", si))
            if expected:
                story.append(Paragraph(
                    f"{pad}&nbsp;&nbsp;&nbsp;"
                    f"<i>Ожидаемый результат:</i> {_html.escape(expected)}", sr))
            if children:
                self._render_steps(children, story, s_step, s_res, depth+1)

    def _generate_pdf(self, sections: List[Dict], path: Path):
        fn, fb = self._setup_fonts()

        doc = SimpleDocTemplate(
            str(path), pagesize=A4,
            leftMargin=20*mm, rightMargin=20*mm,
            topMargin=20*mm,  bottomMargin=20*mm,
        )
        base = getSampleStyleSheet()

        def ps(name, parent="Normal", **kw):
            # fontName=fn — дефолт; если вызывающий код передал свой fontName — он победит
            kw.setdefault("fontName", fn)
            return ParagraphStyle(name, parent=base[parent], **kw)

        C_BLUE   = colors.HexColor("#1a2c42")
        C_GREY   = colors.HexColor("#555555")
        C_LINK   = colors.HexColor("#0055cc")
        C_TAG    = colors.HexColor("#2255aa")
        C_RES    = colors.HexColor("#336699")
        C_GREEN  = colors.HexColor("#217a21")
        C_RED    = colors.HexColor("#c0392b")
        C_ORANGE = colors.HexColor("#d35400")

        STATUS_C = {
            "passed":  C_GREEN,  "failed":  C_RED,
            "broken":  C_ORANGE, "skipped": C_GREY,
        }

        s_title   = ps("s_title",  "Heading1", fontName=fb,
                       fontSize=18, spaceAfter=4, alignment=1)
        s_sub     = ps("s_sub",    fontSize=10, textColor=C_GREY,
                       spaceAfter=18, alignment=1)
        s_section = ps("s_sec",    "Heading2", fontName=fb,
                       fontSize=13, spaceBefore=14, spaceAfter=5,
                       textColor=C_BLUE)
        s_tc      = ps("s_tc",     "Heading3", fontName=fb,
                       fontSize=11, spaceBefore=10, spaceAfter=3,
                       leftIndent=4*mm)
        s_meta    = ps("s_meta",   fontSize=9,  textColor=C_GREY,
                       spaceAfter=2, leftIndent=8*mm)
        s_label   = ps("s_lbl",    fontName=fb,
                       fontSize=10, spaceAfter=2, leftIndent=8*mm, spaceBefore=5)
        s_body    = ps("s_body",   fontSize=10, spaceAfter=2,
                       leftIndent=12*mm, leading=14)
        s_code    = ps("s_code",   fontName="Courier",
                       fontSize=9,  spaceAfter=2, leftIndent=12*mm, leading=13)
        s_step    = ps("s_step",   fontSize=10, spaceAfter=2,
                       leftIndent=14*mm, leading=14)
        s_sres    = ps("s_sres",   fontSize=9,  spaceAfter=2,
                       leftIndent=18*mm, leading=13, textColor=C_RES)
        s_tag     = ps("s_tag",    fontSize=9,  spaceAfter=3,
                       leftIndent=8*mm, textColor=C_TAG)
        s_link    = ps("s_link",   fontSize=9,  spaceAfter=2,
                       leftIndent=8*mm, textColor=C_LINK)
        s_param   = ps("s_param",  fontSize=9,  spaceAfter=2, leftIndent=12*mm)
        s_att     = ps("s_att",    fontSize=9,  spaceAfter=2,
                       leftIndent=12*mm, textColor=C_GREY)
        s_cf      = ps("s_cf",     fontSize=9,  spaceAfter=2, leftIndent=12*mm)
        s_result  = ps("s_result", fontSize=9,  spaceAfter=2,
                       leftIndent=12*mm, leading=13)
        s_issue   = ps("s_issue",  fontSize=9,  spaceAfter=2,
                       leftIndent=12*mm, textColor=C_LINK)

        def lbl(text):
            story.append(Paragraph(f"<b>{_html.escape(text)}</b>", s_label))

        def meta(label, val):
            if val:
                story.append(Paragraph(
                    f"{label}: <b>{_html.escape(str(val))}</b>", s_meta))

        def body(raw):
            in_code, buf = False, []
            for line in raw.splitlines():
                stripped = line.strip()
                if stripped.startswith("```"):
                    if in_code:
                        for cl in buf:
                            story.append(Paragraph(
                                _html.escape(cl) or "&nbsp;", s_code))
                        buf, in_code = [], False
                    else:
                        in_code = True
                    continue
                if in_code:
                    buf.append(line)
                elif stripped:
                    story.append(Paragraph(_html.escape(stripped), s_body))
            for cl in buf:
                story.append(Paragraph(_html.escape(cl) or "&nbsp;", s_code))

        # ── Шапка ─────────────────────────────────────────────────────────────
        story: list = []
        plan_name = self.cfg.get("plan_name",
                                 "NT Proxy (Шлюз доступа на базе СКДПУ НТ)")
        story.append(Paragraph(_html.escape(plan_name), s_title))
        story.append(Paragraph(f"Тест-план #{self.cfg['test_plan_id']}", s_title))
        story.append(Paragraph(
            f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}", s_sub))
        story.append(Spacer(1, 4*mm))
        total = sum(len(s["testCases"]) for s in sections)
        story.append(Paragraph(f"Всего тест-кейсов: {total}", s_meta))
        story.append(Spacer(1, 6*mm))

        # ── Разделы ────────────────────────────────────────────────────────────
        n = 1
        for si, sec in enumerate(sections, 1):
            story.append(Paragraph(
                f"{si}. {_html.escape(sec['name'])}", s_section))

            for tc in sec["testCases"]:
                tid  = tc.get("id", "")
                proj = tc.get("projectId", "")
                name = tc.get("name", "Без имени")

                # Заголовок
                story.append(Paragraph(
                    f"{n}. {_html.escape(name)} "
                    f"<font color='#888888' size='9'>[ID: {tid}]</font>",
                    s_tc))

                # Ссылка на страницу UI
                ui_url = f"{self.base}/project/{proj}/test-cases/{tid}"
                story.append(Paragraph(
                    f'<a href="{ui_url}" color="#0055cc">{ui_url}</a>',
                    s_link))

                # Метаданные
                meta("Статус",   (tc.get("status")   or {}).get("name"))
                meta("Воркфлоу",(tc.get("workflow")  or {}).get("name"))
                meta("Тип", "Автоматизированный" if tc.get("automated") else "Ручной")
                if tc.get("external"):
                    story.append(Paragraph("Внешний: <b>да</b>", s_meta))
                created = f"{tc.get('createdBy','')}  {self._ts(tc.get('createdDate'))}".strip()
                if created:
                    meta("Создан", created)
                modified = f"{tc.get('lastModifiedBy','')}  {self._ts(tc.get('lastModifiedDate'))}".strip()
                if modified:
                    meta("Изменён", modified)
                if tc.get("duration"):
                    meta("Продолжительность", self._dur(tc["duration"]))

                # Теги
                tags = tc.get("tags") or []
                if tags:
                    story.append(Paragraph(
                        "<b>Теги:</b> " +
                        ", ".join(_html.escape(t.get("name","")) for t in tags),
                        s_tag))

                # Custom Fields
                cfs = tc.get("customFields") or []
                if cfs:
                    lbl("Пользовательские поля:")
                    for cf in cfs:
                        k = _html.escape(str(cf.get("name",  "") or ""))
                        v = _html.escape(str(cf.get("value", "") or ""))
                        if k or v:
                            story.append(Paragraph(f"• <b>{k}:</b> {v}", s_cf))

                # Параметры
                params_list = tc.get("parameters") or []
                if params_list:
                    lbl("Параметры:")
                    for p in params_list:
                        pn = _html.escape(str(p.get("name",  "") or ""))
                        pv = _html.escape(str(p.get("value", "") or ""))
                        story.append(Paragraph(f"• <b>{pn}</b> = {pv}", s_param))

                # Ссылки (links)
                links = tc.get("links") or []
                if links:
                    lbl("Ссылки:")
                    for lk in links:
                        lu  = lk.get("url", "") or ""
                        ln  = _html.escape(lk.get("name") or lu)
                        lt  = _html.escape(lk.get("type", "") or "")
                        pre = f"[{lt}] " if lt else ""
                        line = (f'{pre}<a href="{lu}" color="#0055cc">{ln}</a>'
                                if lu else f"{pre}{ln}")
                        story.append(Paragraph(line, s_link))

                # Описание
                desc = self._plain(tc.get("description", "") or "")
                if desc:
                    lbl("Описание:")
                    body(desc)

                # Предусловия
                pre = self._plain(tc.get("precondition", "") or "")
                if pre:
                    lbl("Предусловия:")
                    body(pre)

                # Шаги
                steps = tc.get("steps") or []
                if steps:
                    lbl("Шаги:")
                    self._render_steps(steps, story, s_step, s_sres)
                else:
                    story.append(Paragraph("<i>Шаги не определены</i>", s_meta))

                # Вложения
                atts = tc.get("_attachments") or []
                if atts:
                    lbl("Вложения:")
                    for a in atts:
                        an  = _html.escape(a.get("name", "") or "")
                        ac  = _html.escape(a.get("contentType", "") or "")
                        asz = a.get("size", 0)
                        aid = a.get("id", "")
                        sz  = f"  ({asz} байт)" if asz else ""
                        ct  = f"  [{ac}]"       if ac  else ""
                        if aid:
                            aurl = f"{self.base}/api/testcase/attachment/{aid}/content"
                            line = f'• <a href="{aurl}" color="#0055cc">{an}</a>{ct}{sz}'
                        else:
                            line = f"• {an}{ct}{sz}"
                        story.append(Paragraph(line, s_att))

                # История запусков
                results = tc.get("_results") or []
                if results:
                    lbl("Последние результаты:")
                    for res in results:
                        status = (res.get("status") or "").lower()
                        scol   = STATUS_C.get(status, C_GREY)
                        sname  = _html.escape(status.upper() or "—")
                        launch = _html.escape(res.get("launchName", "") or "")
                        start  = self._ts(res.get("start"))
                        dur    = self._dur(
                            (res.get("stop", 0) or 0) - (res.get("start", 0) or 0))
                        parts = [f'<font color="{scol.hexval()}"><b>{sname}</b></font>']
                        if launch: parts.append(launch)
                        if start:  parts.append(start)
                        if dur:    parts.append(f"({dur})")
                        story.append(Paragraph("• " + "  ".join(parts), s_result))

                # Связанные задачи
                issues = tc.get("_issues") or []
                if issues:
                    lbl("Связанные задачи:")
                    for iss in issues:
                        iname = _html.escape(
                            iss.get("name", "") or iss.get("id", "") or "—")
                        iurl  = iss.get("url", "") or ""
                        itype = _html.escape(iss.get("type", "") or "")
                        pre_  = f"[{itype}] " if itype else ""
                        line  = (f'{pre_}<a href="{iurl}" color="#0055cc">{iname}</a>'
                                 if iurl else f"{pre_}{iname}")
                        story.append(Paragraph("• " + line, s_issue))

                story.append(Spacer(1, 5*mm))
                n += 1

            if si < len(sections):
                story.append(HRFlowable(
                    width="100%", thickness=0.5,
                    color=colors.HexColor("#cccccc"),
                    spaceBefore=2*mm, spaceAfter=4*mm,
                ))

        doc.build(story)
        log.info("PDF создан: %s", path)

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        plan_id = int(self.cfg["test_plan_id"])
        log.info("Выгрузка тест-плана #%d…", plan_id)

        plan = self._get(f"testplan/{plan_id}")
        if not plan:
            log.error("Тест-план недоступен"); return
        with open(self.out / "testplan_info.json", "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2, default=str)

        proj = plan.get("projectId")
        if not proj:
            log.error("projectId не найден"); return
        log.info("projectId = %d", proj)

        ids = self._collect_ids(plan_id, proj)
        if not ids:
            log.error("Нет тест-кейсов"); return

        log.info("Загружаем %d тест-кейсов…", len(ids))
        cases: List[Dict] = []
        for i, tid in enumerate(ids, 1):
            log.info("  [%d/%d] кейс %d…", i, len(ids), tid)
            tc = self._fetch_full(tid, proj)
            if tc:
                cases.append(tc)
        log.info("Загружено: %d", len(cases))

        sections = self._sections(cases)
        with open(self.out / "testplan_tree.json", "w", encoding="utf-8") as f:
            json.dump(sections, f, ensure_ascii=False, indent=2, default=str)

        pdf_name = self.cfg.get("pdf_name", f"testplan_{plan_id}_full.pdf")
        self._generate_pdf(sections, self.out / pdf_name)

        total = sum(len(s["testCases"]) for s in sections)
        log.info("")
        log.info("=" * 50)
        log.info("ЭКСПОРТ ЗАВЕРШЁН")
        log.info("Директория : %s", self.out.absolute())
        log.info("Тест-план  : #%d  (project %d)", plan_id, proj)
        log.info("Разделов   : %d", len(sections))
        log.info("Тест-кейсов: %d", total)
        log.info("PDF        : %s", self.out / pdf_name)
        log.info("=" * 50)


def main():
    AllureExporter("config.json").run()


if __name__ == "__main__":
    main()