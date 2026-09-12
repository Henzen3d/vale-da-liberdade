#!/usr/bin/env python3
"""
Gera roteiro JSON com bate-volta individual e bloqueio automático
de repetição com o dia anterior (exceto continuações com transição).
"""
import argparse, json, re, sys
from datetime import date, timedelta
from pathlib import Path

EPISODES = Path(__file__).resolve().parent.parent / "episodes"

def normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def url_key(url: str) -> str:
    return url.split("?")[0].rstrip("/")

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

def is_continuation(item: dict) -> bool:
    keywords = [
        "prisão", "condenação", "julgamento", "inquérito", "investigação",
        "dados", "divulgado", "atualização", "desfecho", "ressuscita",
        "denúncia", "processo", "andamento", "nova fase", "atualizado",
        "segunda fase", "retomada", "reabertura", "desdobramento"
    ]
    text = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return any(k in text for k in keywords)

def build_overlap_map(today: date, previous: date):
    today_path = EPISODES / f"raw-{today.isoformat()}.md"
    prev_path = EPISODES / f"raw-{previous.isoformat()}.md"
    if not today_path.exists() or not prev_path.exists():
        return {}, {}

    today_items = extract_news(today_path)
    prev_items = extract_news(prev_path)

    prev_by_url = {}
    prev_by_title_sim = []
    for it in prev_items:
        u = url_key(it.get("url", ""))
        if u:
            prev_by_url[u] = it
        prev_by_title_sim.append(it)

    ok = []
    blocked = []
    for it in today_items:
        u = url_key(it.get("url", ""))
        title = it.get("title", "")
        repeated = None
        reason = None
        if u and u in prev_by_url:
            repeated = prev_by_url[u]
            reason = "url_match"
        else:
            for pit in prev_by_title_sim:
                if title_similarity(title, pit.get("title", "")) >= 0.75:
                    repeated = pit
                    reason = f"title_similarity={title_similarity(title, pit.get('title','')):.2f}"
                    break
        if repeated:
            blocked.append({
                "item": it,
                "match": repeated,
                "reason": reason,
                "continuation": is_continuation(it),
            })
        else:
            ok.append(it)
    return ok, blocked

def build_roteiro_for_date(target_date: date):
    # Template do roteiro para 2026-06-26 (pode ser expandido depois)
    if target_date != date(2026, 6, 26):
        raise NotImplementedError("Template de roteiro disponível apenas para 2026-06-26.")

    roteiro = {
        "manchetes": [
            "Estudante de 11 anos denuncia mãe mantida em cárcere privado e ajuda PM a prender foragido em Gaspar",
            "Barragem Norte volta a preocupar moradores e Defesa Civil diante do risco de enchentes",
            "Câmara de Blumenau aprova LDO de 2027",
            "Celesc investe R$ 364 milhões para modernizar rede elétrica em Blumenau e região",
            "Venezuela registra terremotos de alta magnitude com centenas de mortos",
            "Advogado que viralizou ao concordar com condenação de cliente é encontrado morto em Santa Catarina"
        ],
        "introducao": [
            {"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Peter", "texto": "Hoje temos um estudante de 11 anos salvando a própria mãe de cárcere privado, uma barragem que pode explodir com El Niño, um advogado que viralizou por fazer o óbvio — defender o cliente — e foi encontrado morto. Tudo isso enquanto o Estado anuncia R$ 364 milhões para luz e R$ 1 milhão para educação e segurança."},
            {"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Ricardo", "texto": "Peter, há fatos que escapam da narrativa de caos: a Defesa Civil monitora a Barragem Norte, a Câmara aprovou a LDO de 2027 e Santa Catarina ganhou caminhões de combate a incêndio no Alto Vale. Nem tudo é propaganda; há decisões que impactam vidas."},
            {"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Peter", "texto": "Ricardo, se as decisões fossem boas, não precisaríamos de monitores de barragem nem de bombeiros novos — o Estado já teria resolvido na primeira obra. Vamos aos fatos, começando pela segurança pública."},
        ],
        "quadros": [
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "Mulher tem celular roubado após homem pedir as horas em ponto de ônibus de Blumenau", "texto": "Em Blumenau, uma jovem de 21 anos teve o celular roubado após dar as horas a um homem no ponto de ônibus do Itoupavazinha. Ele aproveitou o momento para tomar o aparelho à força e fugir."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "ref_title": "Mulher tem celular roubado após homem pedir as horas em ponto de ônibus de Blumenau", "texto": "Modus operandi clássico: pergunta inocente, depois força bruta. O Estado monopoliza a segurança, mas um ponto de ônibus vira arena de roubo sem câmera, sem viatura, sem presença. O contribuinte paga PM e o bandido continua mandando noite adentro."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "Mulher tem celular roubado após homem pedir as horas em ponto de ônibus de Blumenau", "texto": "A PM registrou a ocorrência. O padrão em Blumenau é roubo de celulares em pontos isolados. Iluminação pública deficiente e ausência de câmeras municipais contribuem. A Prefeitura responderia melhor com infraestrutura preventiva."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "ref_title": "Mulher tem celular roubado após homem pedir as horas em ponto de ônibus de Blumenau", "texto": "Infraestrutura preventiva custa dinheiro. E dinheiro público tem dono: a máquina eleitoral. O recurso para câmeras desaparece no orçamento e reaparece em maracutaia de campanha."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "Discussão por internet termina com tiro e apreensão de cinco armas em Blumenau", "texto": "No Ribeirão Fresco, uma discussão por equipamento de internet terminou com disparo de arma, prisão e apreensão de cinco armas. Um técnico de 38 anos foi à residência para retirar o aparelho após cancelamento do contrato."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "ref_title": "Discussão por internet termina com tiro e apreensão de cinco armas em Blumenau", "texto": "Cinco armas apreendidas dentro de uma casa por causa de discussão de internet. O Estado proíbe o cidadão de ter arma para defesa, mas uma casa em Blumenau tinha cinco armas ilegais. A legislação desarma o sujeito de boa-fé e não toca no criminoso. Excelente balanço."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "Discussão por internet termina com tiro e apreensão de cinco armas em Blumenau", "texto": "A PM atendeu, controlou a situação e prendeu o responsável pelos disparos. A operação foi relativamente rápida. Não dá para culpar a legislação de armas por uma discussão particular que escalou para crime."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "Suspeito de feminicídio em Lages é encontrado morto em Agrolândia", "texto": "Outro caso: o suspeito do feminicídio de Adriana Aparecida dos Santos, de 37 anos, foi encontrado morto em um sítio em Agrolândia. Ele era companheiro da vítima. Um vizinho localizou o corpo ao ir à propriedade para um trabalho."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "ref_title": "Suspeito de feminicídio em Lages é encontrado morto em Agrolândia", "texto": "Suspeito de feminicídio aparece morto antes de ser julgado — de novo. O Estado não consegue evitar o assassinato nem garantir que o responsável responda em vida. A justiça brasileira é póstuma por decreto."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "Suspeito de feminicídio em Lages é encontrado morto em Agrolândia", "texto": "A Polícia Civil investiga as circunstâncias da morte. Não há indício de crime contra o suspeito. O fato não apaga o feminicídio anterior, mas encerra o ciclo de investigação."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "ATO DE CORAGEM: Denúncia de estudante de 11 anos ajuda PM a resgatar mãe vítima de cárcere privado e prender foragido", "texto": "Em Gaspar, um estudante de 11 anos denunciou à Rede de Segurança Escolar que a mãe estava sendo agredida e mantida em cárcere privado pelo companheiro. Ele procurou a equipe da escola, que acionou a PM. O homem de 38 anos foi preso em flagrante."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "ref_title": "ATO DE CORAGEM: Denúncia de estudante de 11 anos ajuda PM a resgatar mãe vítima de cárcere privado e prender foragido", "texto": "Um garoto de 11 anos fez o que toda a rede de proteção estatal deveria ter feito. A escola foi o último recurso, não o primeiro. O Estado falha na prevenção e deixa o menor decidir entre calar ou arriscar a própria vida."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "ATO DE CORAGEM: Denúncia de estudante de 11 anos ajuda PM a resgatar mãe vítima de cárcere privado e prender foragido", "texto": "A PM também resgatou uma mulher que sofria violência doméstica há cerca de dois meses no bairro Margem Esquerda, em Gaspar. A denúncia partiu da própria Rede de Segurança Escolar. Os policiais encontraram a vítima em visível estado de abalo emocional."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "ref_title": "ATO DE CORAGEM: Denúncia de estudante de 11 anos ajuda PM a resgatar mãe vítima de cárcere privado e prender foragido", "texto": "Dois meses de sofrimento e a única saída foi um policial aparecer por denúncia externa. Se a Rede de Segurança Escolar sequer existia, a mulher continuaria no cárcere privado cada semana que o Estado demora para agir."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "ref_title": "Botão do pânico leva à prisão de homem por descumprimento de medida protetiva em Presidente Getúlio", "texto": "E em Presidente Getúlio, o botão do pânico do aplicativo PMSC Cidadão levou à prisão de um homem por descumprimento de medida protetiva. A vítima acionou o recurso ao ver o ex-companheiro na residência."},
            {"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "ref_title": "Botão do pânico leva à prisão de homem por descumprimento de medida protetiva em Presidente Getúlio", "texto": "A tecnologia existe e funciona: um botão no celular impede nova agressão. O problema é que a proteção chega só depois que a mulher já sofreu. Medida protetiva não é prevenção, é remendo. E ainda assim o Estado demora para cumpri-la sem tecnologia."},
            {"quadro": "SAÚDE", "speaker": "Peter", "ref_title": "Espera por consulta com neurologista pediatra pode chegar a um ano em Blumenau, diz secretário", "texto": "Na saúde pública, a espera por consulta com neurologista pediatra em Blumenau pode chegar a um ano. O dado é oficial e dizima qualquer discurso de saúde universal. Crianças aguardando sentadas enquanto a burocracia estadual empilha processos."},
            {"quadro": "SAÚDE", "speaker": "Ricardo", "ref_title": "Espera por consulta com neurologista pediatra pode chegar a um ano em Blumenau, diz secretário", "texto": "O secretário afirma que o município tem ampliado a oferta, mas a ação judicial do Conselho Tutelar contra a prefeitura mostra que a realidade é mais dura do que o anúncio. O Ministério Público agora cobra fulfillment do dever constitucional."},
            {"quadro": "SAÚDE", "speaker": "Peter", "ref_title": "Espera por consulta com neurologista pediatra pode chegar a um ano em Blumenau, diz secretário", "texto": "Ação judicial é o único jeito de filhos da República conseguirem atendimento. Se o Estado entregasse o que promete, o MP não seria necessário. Enquanto isso, a criança espera 365 dias por uma consulta que deveria ser imediata."},
            {"quadro": "EDUCAÇÃO", "speaker": "Peter", "ref_title": "De alunos a protagonistas: Viva Música gera oportunidades, transformação e inclusão social em Blumenau e Indaial", "texto": "Na educação, o Projeto Viva Música é exceção que virou referência em Blumenau e Indaial. Um aluno que começou aos 15 anos em aulas gratuitas de trompete hoje integra a Banda Municipal de Blumenau, a Experimental Big Band de Joinville e dá aulas particulares."},
            {"quadro": "EDUCAÇÃO", "speaker": "Ricardo", "ref_title": "De alunos a protagonistas: Viva Música gera oportunidades, transformação e inclusão social em Blumenau e Indaial", "texto": "Esse é o tipo de política que deveria ser regra na rede municipal, não exceção sustentada por associação e voluntários. Projetos de inclusão por música e arte devolvem perspectiva para jovens que a escola pública abandonou."},
            {"quadro": "EDUCAÇÃO", "speaker": "Peter", "ref_title": "De alunos a protagonistas: Viva Música gera oportunidades, transformação e inclusão social em Blumenau e Indaial", "texto": "Quando a escola pública não cumpre o papel, a iniciativa privada e a sociedade civil fazem o remendo. O mérito é do Viva Música, não da SME. Se a rede ensinasse música e leitura como deve ser, não dependeríamos de associação de cegos para cobrir o fracasso."},
            {"quadro": "EDUCAÇÃO", "speaker": "Ricardo", "ref_title": "Blumenau recebe R$ 1 milhão em recursos anunciados para educação e segurança pública", "texto": "E em Blumenau, o secretariado de Educação recebe R$ 500 mil dos R$ 1 milhão anunciados pelo deputado Alex Brasil. O valor deve ser aplicado em infraestrutura escolar. Veremos se o recurso realmente transforma sala de aula ou vira obra de campanha."},
            {"quadro": "EDUCAÇÃO", "speaker": "Peter", "ref_title": "Blumenau recebe R$ 1 milhão em recursos anunciados para educação e segurança pública", "texto": "Meio milhão anunciado às vésperas de eleição tem cheiro de palanque. O risco é o dinheiro sair do estado e aparecer em placa de inauguração antes de chegar à escola. Acompanhem o gasto por nota fiscal e não por foto de deputado."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Peter", "ref_title": "Câmara aprova LDO de Blumenau para 2027", "texto": "Na política local, a Câmara de Blumenau aprovou a LDO de 2027 em segunda discussão. O projeto é do Executivo e só define diretrizes orçamentárias, mas na prática funciona como carta branca para gastos futuros."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Ricardo", "ref_title": "Câmara aprova LDO de Blumenau para 2027", "texto": "A LDO é obrigatória e segue rito constitucional. A aprovação em segunda votação indica debate prévio. O risco não é a ferramenta, é a execução: se a receita for superestimada, o orçamento vira ficção."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Peter", "ref_title": "Câmara aprova LDO de Blumenau para 2027", "texto": "Em Blumenau, toda LDO é receituário de ilusão. Aprovam em junho, executam metade no ano seguinte e em dezembro aparece déficit. O contribuinte paga a conta de um planejamento que nunca foi real."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Peter", "ref_title": "Celesc moderniza rede elétrica em Blumenau, Brusque, Pomerode e região com investimentos que somam R$ 364 milhões", "texto": "A Celesc anunciou R$ 364 milhões em modernização da rede elétrica em Blumenau, Brusque, Pomerode e região. Até 2025, R$ 166,9 milhões já haviam sido executados. O restante promete expandir capacidade para indústria têxtil e metalmecânica."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Ricardo", "ref_title": "Celesc moderniza rede elétrica em Blumenau, Brusque, Pomerode e região com investimentos que somam R$ 364 milhões", "texto": "Investimento em infraestrutura elétrica atrai indústria e cria emprego. Modernizar a ARBLU é estratégico para Blumenau. Mas R$ 364 milhões num Estado quebrado dependem de agências reguladoras e contratos públicos — sempre sujeitos a desvios e atrasos."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Peter", "ref_title": "Celesc moderniza rede elétrica em Blumenau, Brusque, Pomerode e região com investimentos que somam R$ 364 milhões", "texto": "A Celesc tem a popularidade de todo monopólio: aparece com dinheiro novo, mas o usuário paga a conta todos os meses na tarifa. Modernização deveria ter sido feita há 10 anos. O investimento resolve o problema que o próprio Estado criou ao negligenciar a rede."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Peter", "ref_title": "CCJ barra projeto que previa agente de bordo nos ônibus de Blumenau", "texto": "A CCJ da Câmara de Blumenau barrou o projeto de agente de bordo nos ônibus, de iniciativa popular. A proposta previa dois operadores por veículo, mas a comissão considerou o projeto inconstitucional por 4 votos a 1."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Ricardo", "ref_title": "CCJ barra projeto que previa agente de bordo nos ônibus de Blumenau", "texto": "A questão é jurídica, não ideológica. A Constituição veda a criação de cargos por iniciativa popular. O transporte coletivo é problema real, mas a solução não pode ser casuística. Precisa de projeto técnico do Executivo."},
            {"quadro": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA", "speaker": "Peter", "ref_title": "CCJ barra projeto que previa agente de bordo nos ônibus de Blumenau", "texto": "Inconstitucional? O Estado adapta a Constituição quando interessa aos amigos do transporte, mas para projeto popular a carta é intocável. O caminhoneiro tem lobby; o usuário de ônibus não tem voto nem voz."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Ricardo", "ref_title": "Blumenau recebe R$ 1 milhão em recursos anunciados para educação e segurança pública", "texto": "Na comunidade, Blumenau ganha 500 mil reais em recursos estaduais para educação e segurança pública. O anúncio foi do deputado Alex Brasil e faz parte de uma verba de emenda parlamentar."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Peter", "ref_title": "Blumenau recebe R$ 1 milhão em recursos anunciados para educação e segurança pública", "texto": "Recurso de emenda é política de balcão: o deputado anuncia, a prefeitura agradece e o contribuinte paga. Acompanhem se o valor chega à escola e não desaparece em 'estrutura de segurança' que nunca aparece."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Ricardo", "ref_title": "Alto Vale recebe novos caminhões de combate a incêndio para reforçar atendimento dos bombeiros", "texto": "A Câmara aprovou verbas para a Barragem Norte e caminhões novos para os bombeiros do Alto Vale. Os veículos vão para Rio do Sul, Trombudo Central e Ituporanga. Se a manutenção for contínua, o risco de enchente diminui de verdade."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Peter", "ref_title": "Alto Vale recebe novos caminhões de combate a incêndio para reforçar atendimento dos bombeiros", "texto": "Caminhões novos e a barragem continua dependendo de explicação de defesa civil. O Estado só investe em emergência quando o povo começa a reclamar nas redes. Se não houver pressão, a barragem segue invisível e o din some em outra prioridade."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Ricardo", "ref_title": "Programação de fim de semana no Norte Shopping Blumenau.", "texto": "E no lazer, o Norte Shopping Blumenau prepara programação de fim de semana com desfile de moda tecnológica, competições esportivas e shows gratuitos. Eventos como esse movimentam economia local sem depender de dinheiro público."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Peter", "ref_title": "Programação de fim de semana no Norte Shopping Blumenau.", "texto": "Shopping privado faz evento privado com dinheiro privado. O Estado não precisa patrocinar lazer quando o mercado responde por demanda. Mas claro, se for para dar isenção fiscal para grande rede, o dinheiro público aparece na hora."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Ricardo", "ref_title": "Blumenau terá pesquisa sobre a gastronomia da cidade para fortalecer políticas públicas do turismo no setor.", "texto": "A gastronomia de Blumenau também terá Censo do Setor de Alimentos e Bebidas no segundo semestre. O Observatório de Turismo vai mapear estrutura e desafios dos empreendimentos. Se o resultado reduzir burocracia, todos ganham."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Peter", "ref_title": "Blumenau terá pesquisa sobre a gastronomia da cidade para fortalecer políticas públicas do turismo no setor.", "texto": "Censo para mapear é o primeiro passo para taxar. O Estado adora levantar dado para depois exigir alvará, licença e taxa. O setor gastronômico blumenauense já respira por falta de burocracia; com censo, o fôlego diminui."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Ricardo", "ref_title": "Goteiras no Ginásio Henrique Holetz geram cancelamento de jogos em Ituporanga", "texto": "Em Ituporanga, o Ginásio Henrique Holetz cancelou jogos do Campeonato Estadual Sub-10 de Futsal por goteiras no teto e problemas de conservação. A Câmara cobra explicações. O problema de estrutura básica afeta o esporte que o Estado diz priorizar."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Peter", "ref_title": "Goteiras no Ginásio Henrique Holetz geram cancelamento de jogos em Ituporanga", "texto": "Goteira em ginásio estadual e jogos de futsal infantil cancelados. O Estado não mantém teto nem reforma quadra, mas gasta milhões com centro de eventos e festa internacional. A prioridade do poder é sempre a mesma: a própria foto."},
            {"quadro": "ESPORTES E INTERESSE COMUNITÁRIO", "speaker": "Ricardo", "ref_title": "Programação de fim de semana no Norte Shopping Blumenau.", "texto": "E fechando o bloco comunitário: o Festival gastronômico de Pomerode terá mais espaço em 2026 e a Expotur Ibirama acontece nos dias 3 e 4 de julho, com entrada gratuita. Eventos de comunidade que não esperam o Estado decidir para acontecer."},
            {"quadro": "BRASIL", "speaker": "Ricardo", "ref_title": "Santa Catarina ultrapassa 10 mil vagas de emprego pelo Sine e reforça ações de intermediação.", "texto": "No Brasil, Santa Catarina ultrapassou 10 mil vagas de emprego abertas pelo Sine SC, sendo 282 exclusivas para Pessoas com Deficiência. As oportunidades estão distribuídas por todas as regiões do estado."},
            {"quadro": "BRASIL", "speaker": "Peter", "ref_title": "Santa Catarina ultrapassa 10 mil vagas de emprego pelo Sine e reforça ações de intermediação.", "texto": "Dez mil vagas no Sine enquanto Blumenau tem crianças esperando consulta de neurologia há um ano. O mercado oferece trabalho, mas o Estado entrega fila. Dados concretos: 10.040 vagas, 282 exclusivas para PCD. A máquina de emprego público não resolve o problema real."},
            {"quadro": "MUNDO", "speaker": "Ricardo", "ref_title": "Advogado que viralizou após concordar com condenação de cliente é encontrado morto em Santa Catarina", "texto": "No mundo, a Venezuela registrou dois terremotos de magnitude acima de 7, com pelo menos 235 mortos e 4.300 feridos. O epicentro foi próximo a Caracas e abalou aeroporto e prédios."},
            {"quadro": "MUNDO", "speaker": "Peter", "ref_title": "Advogado que viralizou após concordar com condenação de cliente é encontrado morto em Santa Catarina", "texto": "Venezuela tem infraestrutura combalida por décadas de socialismo e destruição institucional. O Estado controla tudo e quando o solo treme, quem paga o preço é a população. O número de mortos reflete falência estatal em manter construção e resposta a emergências."},
        ],
        "fechamento": [
            {"quadro": "FECHAMENTO EDITORIAL", "speaker": "Peter", "texto": "Encerro com isso: em Gaspar, um menino de 11 anos foi mais eficiente que toda a rede de proteção do Estado. Em Caracas, a infraestrutura ruiu. Em Blumenau, R$ 364 milhões prometem luz nova, mas a luz que falta é a da responsabilidade estatal."},
            {"quadro": "FECHAMENTO EDITORIAL", "speaker": "Ricardo", "texto": "Eu deixo o recado: acompanhem a execução da LDO de 2027, fiscalizem o Censo da Gastronomia e denunciem suspeitas de violência doméstica à Rede de Segurança Escolar. A sociedade funciona quando cada um faz a sua parte — e não quando espera o Estado fazer tudo."},
        ]
    }

    return roteiro

def filter_roteiro(roteiro: dict, target_date: date):
    previous = target_date - timedelta(days=1)
    ok, blocked = build_overlap_map(target_date, previous)

    # Mapa de ref_title -> situação
    blocked_titles = {}
    for b in blocked:
        t = b["item"].get("title", "")
        if t:
            blocked_titles[t] = b

    filtered_quadros = []
    added_transitions = set()

    for blk in roteiro.get("quadros", []):
        ref = blk.get("ref_title", "")
        if not ref:
            filtered_quadros.append(blk)
            continue

        # normalizar título para comparação
        norm_ref = normalize(ref)

        # Procurar correspondência no mapa de bloqueados
        match = None
        for b in blocked_titles.values():
            b_title = b["item"].get("title", "")
            if normalize(b_title) == norm_ref:
                match = b
                break

        if match is None:
            filtered_quadros.append(blk)
            continue

        # Caso haja match:
        if match.get("continuation"):
            # Permitir, mas inserir transição (apenas uma vez por notícia)
            key = norm_ref
            if key not in added_transitions:
                transition = {
                    "quadro": blk.get("quadro", ""),
                    "speaker": "Ricardo",
                    "texto": f"Continuando o acompanhamento do caso “{match['item'].get('title','')}”, temos novos desdobramentos nesta sexta-feira.",
                    "is_transition": True
                }
                filtered_quadros.append(transition)
                added_transitions.add(key)
            filtered_quadros.append(blk)
        else:
            # Bloqueado: pular (não adiciona)
            continue

    roteiro["quadros"] = filtered_quadros
    roteiro["overlap_filter"] = {
        "date": target_date.isoformat(),
        "previous": previous.isoformat(),
        "blocked": [b["item"].get("title") for b in blocked if not b["continuation"]],
        "continued": [b["item"].get("title") for b in blocked if b["continuation"]],
    }
    return roteiro

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Data YYYY-MM-DD")
    args = parser.parse_args()
    target = date.fromisoformat(args.date)

    roteiro = build_roteiro_for_date(target)
    roteiro = filter_roteiro(roteiro, target)

    out = EPISODES / f"roteiro-{target.isoformat()}.json"
    out.write_text(json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Roteiro salvo em: {out}")
    print(f"Total falas: {sum(len(v) for v in [roteiro['introducao'], roteiro['quadros'], roteiro['fechamento']])}")
    if roteiro.get("overlap_filter"):
        flt = roteiro["overlap_filter"]
        print(f"Repetidas bloqueadas: {len(flt.get('blocked', []))}")
        print(f"Continuações mantidas: {len(flt.get('continued', []))}")

if __name__ == "__main__":
    main()
