#!/usr/bin/env python3
"""
Compara os raw.md de dois dias e identifica:
1. URLs repetidas (mesma notícia)
2. Títulos muito parecidos (mesmo fato com wording diferente)
3. Notícias que podem ser tratadas como continuação natural

Uso:
  python3 scripts/check_episode_overlap.py --date 2026-06-25 2026-06-26

Saída:
  - Relatório em stdout
  - Arquivo JSON com parecer para o roteirista usar como transição
"""
import argparse, json, re, sys
from pathlib import Path

EPISODES = Path(__file__).resolve().parent.parent / "episodes"

def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def url_key(url: str):
    # remove tracking params e normaliza domínio
    url = url.split("?")[0].rstrip("/")
    return url

def title_similarity(a: str, b: str) -> float:
    from collections import Counter
    ta, tb = normalize(a), normalize(b)
    wa, wb = Counter(ta.split()), Counter(tb.split())
    if not wa or not wb:
        return 0.0
    inter = sum((wa & wb).values())
    union = sum((wa | wb).values())
    return inter / union if union else 0.0

def extract_news(path: Path):
    items = []
    current = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#### •"):
            if current.get("title"):
                items.append(current)
            current = {"title": line.replace("#### •", "").strip()}
        elif "**URL**:" in line:
            m = re.search(r"\(([^)]+)\)", line)
            if m:
                current["url"] = m.group(1)
        elif line.startswith("- **Resumo**:"):
            current["summary"] = line.replace("- **Resumo**:", "").strip()
    if current.get("title"):
        items.append(current)
    return items

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", nargs="+", help="Datas YYYY-MM-DD a comparar (2 ou mais)")
    args = parser.parse_args()
    dates = args.date
    if len(dates) < 2:
        print("Forneça ao menos duas datas.")
        sys.exit(1)

    news_by_date = {}
    for d in dates:
        p = EPISODES / f"raw-{d}.md"
        if not p.exists():
            print(f"Arquivo não encontrado: {p}")
            sys.exit(1)
        news_by_date[d] = extract_news(p)

    # Checar repetição por URL e por similaridade de título
    base = dates[-1]  # último dia como "novo"
    base_items = news_by_date[base]
    refs = dates[:-1]

    report = {
        "base_date": base,
        "compared_with": refs,
        "continued": [],     # mesma notícia + hints de continuação
        "repeated_no_news": [],  # mesma notícia sem evolução clara
        "unique": [],        # parece nova
        "transitions": [],   # sugestão de transição pronta
    }

    for item in base_items:
        url = item.get("url", "")
        title = item.get("title", "")
        status = "unique"
        match_date = None
        overlap = []

        for ref in refs:
            for ref_item in news_by_date[ref]:
                ref_url = ref_item.get("url", "")
                ref_title = ref_item.get("title", "")
                same_url = url_key(url) == url_key(ref_url) if url and ref_url else False
                sim = title_similarity(title, ref_title)
                if same_url or sim >= 0.75:
                    status = "repeated"
                    match_date = ref
                    overlap.append((ref, ref_title, "url" if same_url else f"similarity={sim:.2f}"))

        if status == "unique":
            report["unique"].append({"title": title, "url": url})
        else:
            # Checar se parece continuação com novos desdobramentos
            keywords_continuity = [
                "prisão", "condenação", "julgamento", " inquérito", "investigação",
                "dados", "divulgado", "atualização", "desfecho", "ressuscita",
                "denúncia", "processo", "andamento", "nova fase"
            ]
            text = (title + " " + item.get("summary", "")).lower()
            is_continuation = any(k in text for k in keywords_continuity)

            entry = {
                "title": title,
                "url": url,
                "matches": [{"date": m[0], "ref_title": m[1], "reason": m[2]} for m in overlap],
                "likely_continuation": is_continuation,
            }
            if is_continuation:
                report["continued"].append(entry)
                base_words = re.sub(r"[^\w]+", " ", title).split()
                key_term = " ".join(base_words[:4]) if len(base_words) >= 4 else title
                report["transitions"].append({
                    "for": title,
                    "suggestion": f"Continuando o acompanhamento do caso {key_term}, temos novos desdobramentos nesta quinta-feira."
                })
            else:
                report["repeated_no_news"].append(entry)

    out = EPISODES / f"overlap-{base}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nRelatório salvo em: {out}")

if __name__ == "__main__":
    main()
