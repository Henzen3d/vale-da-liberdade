#!/usr/bin/env python3
"""Gera capturas Full HD (1920x1080) dos componentes broadcast em mockup-brower.html

Salva em youtube/Evolucao-Visual/shots/broadcast-v3/ para verificação visual e comparação com referências.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = (ROOT / "references" / "youtube" / "mockup-browser" / "mockup-brower.html").as_uri()
OUT_DIR = ROOT / "youtube" / "Evolucao-Visual" / "shots" / "broadcast-v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)

COMPONENTS = [
    {
        "name": "01_source_browser",
        "data": {
            "kind": "source",
            "categoria": "POLÍTICA & ECONOMIA",
            "titulo": "Governo autoriza liberação de crédito extraordinário para infraestrutura no Sul",
            "resumo": "Medida provisória publicada nesta manhã viabiliza investimentos imediatos em rodovias federais e pontes atingidas pelas chuvas.",
            "autor": "Redação VDL",
            "data": "06 de Setembro de 2026",
            "leitura": "3 min",
            "url": "https://g1.globo.com/sc/santa-catarina/noticia/2026/09/obras-rodovias-sul.ghtml",
            "eyebrow": "URGENTE • BRASÍLIA",
            "lowerTitle": "GOVERNO LIBERA CRÉDITO PARA INFRAESTRUTURA NO SUL",
            "lowerSubtitle": "Medida provisória destina recursos para recuperação de rodovias e contenção de encostas.",
            "live": "AO VIVO",
            "tag": "VALE DA LIBERDADE"
        }
    },
    {
        "name": "02_quote_card",
        "data": {
            "kind": "quote",
            "categoria": "DECLARAÇÃO OFICIAL",
            "eyebrow": "DECLARAÇÃO • BASTIDORES",
            "lowerTitle": "LÍDER DA OPOSIÇÃO CRITICA ARTICULAÇÃO POLÍTICA",
            "lowerSubtitle": "Parlamentar afirma que negociações no Congresso ignoraram bancadas regionais.",
            "author_name": "Senador Rogério Marinho",
            "author_role": "Líder da Oposição no Senado",
            "quote_text": "Não se constrói consenso atropelando o regimento e ignorando a voz dos estados que mais produzem.",
            "source_name": "Discurso em Plenário",
            "date": "06/09/2026",
            "verified": True
        }
    },
    {
        "name": "03_document_zoom",
        "data": {
            "kind": "document",
            "categoria": "PODER JUDICIÁRIO",
            "eyebrow": "DECISÃO JUDICIAL • EXCLUSIVO",
            "lowerTitle": "TRIBUNAL SUSPENDE AUMENTO DA TARIFA DE ÔNIBUS",
            "lowerSubtitle": "Liminar da Vara da Fazenda Pública determina cumprimento imediato sob pena de multa.",
            "doc_type": "sentenca",
            "case_number": "PROCESSO Nº 500214-2026.8.24.0008",
            "doc_institution": "VARA DA FAZENDA PÚBLICA DE BLUMENAU",
            "doc_title": "PODER JUDICIÁRIO DO ESTADO DE SANTA CATARINA",
            "lead_text": "Vistos etc. Trata-se de ação civil pública com pedido de tutela provisória de urgência movida contra o consórcio de transporte coletivo.",
            "highlight_text": "DEFIRO A LIMINAR para suspender a eficácia do decreto municipal que autorizou o reajuste tarifário, mantendo o valor anterior até o julgamento do mérito.",
            "notice": "Intimem-se com máxima urgência as concessionárias e a Procuradoria Municipal para cumprimento em 24 horas."
        }
    },
    {
        "name": "04_timeline_facts",
        "data": {
            "kind": "timeline",
            "categoria": "CRONOLOGIA DOS FATOS",
            "eyebrow": "LINHA DO TEMPO • CASO TARIFA",
            "lowerTitle": "A BATALHA JUDICIAL SOBRE O TRANSPORTE COLETIVO",
            "lowerSubtitle": "Entenda os principais marcos da disputa entre concessionárias, prefeitura e usuários.",
            "timeline_title": "CRONOGRAMA DE DECISÕES DA TARIFA",
            "year": "2026",
            "events": [
                {
                    "date": "15/JAN/2026",
                    "title": "Pedido do Consórcio",
                    "description": "Empresas solicitam aumento de 14,8% alegando alta de insumos e combustíveis."
                },
                {
                    "date": "22/MAR/2026",
                    "title": "Decreto Autorizado",
                    "description": "Prefeitura pública decreto concedendo reajuste parcial de 8,5%."
                },
                {
                    "date": "10/MAI/2026",
                    "title": "Ação do Ministério Público",
                    "description": "Promotoria aponta falhas no cálculo da planilha de custos e ingressa com ACP."
                },
                {
                    "date": "HOJE",
                    "title": "Liminar Deferida",
                    "description": "Justiça suspende o aumento e determina retorno da tarifa antiga aos usuários."
                }
            ]
        }
    },
    {
        "name": "05_data_chart",
        "data": {
            "kind": "chart",
            "categoria": "INDICADOR ECONÔMICO",
            "eyebrow": "ECONOMIA & MERCADO • INVESTIMENTOS",
            "lowerTitle": "APORTE FEDERAL RECORDE PARA O VALE DO ITAJAÍ",
            "lowerSubtitle": "Recursos destinados a duplicações de rodovias e contenção de cheias superam anos anteriores.",
            "metric_label": "INVESTIMENTOS EM INFRAESTRUTURA REGIONAL",
            "metric_prefix": "R$ ",
            "metric_value": "145,8",
            "metric_suffix": " MI",
            "trend": "up",
            "delta_text": "+18,4% acima do orçamento de 2025",
            "context": "Volume aprovado pela União para a conclusão de viadutos e contenção no Vale do Itajaí.",
            "sub_items": [
                {"label": "2024 (Executado)", "value": "R$ 88,2 mi", "pct": "55%"},
                {"label": "2025 (Executado)", "value": "R$ 123,1 mi", "pct": "78%"},
                {"label": "2026 (Orçado e Liberado)", "value": "R$ 145,8 mi", "pct": "96%"}
            ]
        }
    },
    {
        "name": "06_comparison_editorial",
        "data": {
            "kind": "comparison",
            "categoria": "ANÁLISE COMPARATIVA",
            "eyebrow": "CONFRONTO • PROMESSA VS FATO",
            "lowerTitle": "O IMPACTO DO REAJUSTE DO IPTU NO BOLSO DO CIDADÃO",
            "lowerSubtitle": "Comparativo detalhado entre o que foi defendido em palanque e o texto aprovado no Diário Oficial.",
            "comparison_title": "PROMESSA DE CAMPANHA × REALIDADE ORÇAMENTÁRIA",
            "side_a": {
                "header": "PROMESSA ELEITORAL (2024)",
                "highlight": "0% DE AUMENTO REAL",
                "details": "Compromisso expresso assinado durante o debate televisivo de congelar tributos municipais.",
                "tag_status": "compromisso"
            },
            "side_b": {
                "header": "DECRETO EXECUTIVO (2026)",
                "highlight": "+12,4% NO CARNÊ",
                "details": "Revisão da planta de valores venais aprovada pela câmara com impacto imediato em todas as zonas.",
                "tag_status": "fato"
            }
        }
    },
    {
        "name": "07_recorte_jornal",
        "data": {
            "kind": "recorte",
            "categoria": "REPERCUSSÃO NA IMPRENSA",
            "eyebrow": "MANCHETE NACIONAL • DESTAQUE",
            "lowerTitle": "PESQUISA REVELA SENTIMENTO POPULAR SOBRE GESTÃO PÚBLICA",
            "lowerSubtitle": "Levantamento estatístico de abrangência nacional ganha a capa dos principais veículos.",
            "source_name": "FOLHA DE S.PAULO",
            "headline": "Quase 90% dos brasileiros veem corrupção disseminada no poder público",
            "sublead": "Estudo aponta que a ampla maioria dos eleitores demonstra desconfiança com as instituições e cobra maior transparência nos gastos.",
            "date": "EDIÇÃO IMPRESSA • 06 DE SETEMBRO DE 2026"
        }
    }
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        
        for item in COMPONENTS:
            name = item["name"]
            data = item["data"]
            url = f"{HTML_PATH}?freeze=1"
            await page.goto(url, wait_until="networkidle")
            
            # Executa a atualização
            await page.evaluate("(data) => { window.VDL_MOCKUP.update(data); }", data)
            
            # Aguarda um pequeno tempo para rendering dos estilos e layouts
            await page.wait_for_timeout(300)
            
            out_file = OUT_DIR / f"{name}.png"
            await page.screenshot(path=str(out_file), full_page=False)
            print(f"Salvo: {out_file.name}")
            
        await browser.close()
    print("Todas as capturas concluidas com sucesso!")

if __name__ == "__main__":
    asyncio.run(main())
