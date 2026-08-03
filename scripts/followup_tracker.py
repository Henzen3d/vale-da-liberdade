"""
followup_tracker.py — PROTÓTIPO ISOLADO (não integrado ao pipeline ainda)

Objetivo: dar memória entre episódios ao Webjornal Vale da Liberdade,
permitindo detectar quando uma notícia de hoje é desdobramento de algo
já coberto em dias anteriores, e sugerir ao roteirista uma "retomada".

Reaproveita (conceitualmente — NexusLocal roda em Docker separado e
independente deste pipeline, então não há import direto entre os dois;
a ideia é replicar a mesma técnica/lib, não compartilhar runtime):
- fastembed como lib de embeddings (instalar como dependência própria
  neste projeto; NexusLocal serve só como referência de qualidade e
  threshold que já validamos noutro contexto, não como serviço chamado)
- a lógica de threshold de similaridade já usada em cluster_articles()
  do ai_news_filter.py

Não integrado ainda: este arquivo roda isolado, lendo/escrevendo um
news_memory.json de teste, para validar o comportamento antes de
plug no pipeline real (cmd_update_archive, geração de roteiro etc).
"""

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# ── Config (ajustável depois via config file, como no plano de audio) ──
MEMORY_PATH = "news_memory.json"
# Modelo de embedding — paraphrase-multilingual-MiniLM-L12-v2 (118M params, multilíngue)
# Teste de discriminação (2026-07-27) mostrou que este modelo tem 1.8x mais poder de
# separação entre pares relacionados e não-relacionados em português vs bge-small-en-v1.5.
# bge-small-en-v1.5 infla scores genericamente (0.59-0.70 para pares não-relacionados),
# o que torna o threshold instável. multilingual-MiniLM dá 0.006-0.222 para não-relacionados.
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
# Três zonas de similaridade (calibradas para a escala do multilingual-MiniLM)
# Dados do teste de discriminação:
#   Pares relacionados (com boost): min=0.565, max=0.758
#   Pares não-relacionados: min=-0.073, max=0.222
#   Gap = 0.343, ponto médio = 0.393
# Thresholds baseados no ponto médio do gap para maximizar separação
SIMILARITY_THRESHOLD_LOW = 0.40   # abaixo disso: não é desdobramento
SIMILARITY_THRESHOLD_HIGH = 0.50  # acima disso: desdobramento automático
# entre LOW e HIGH: marca como [POSSÍVEL DESDOBRAMENTO] para confirmação humana
RETENTION_DAYS = 21          # após isso, item vira "arquivado" e sai do pool ativo
MIN_MENTIONS_FOR_MONITORING = 2
# Palavras-gatilho simples para fechamento de caso (heurística inicial;
# pode evoluir para classificação via LLM depois)
CLOSURE_KEYWORDS = [
    "condenado", "condenada", "absolvido", "absolvida", "encerrado",
    "encerrada", "resolvido", "resolvida", "concluído", "concluída",
    "sentença definitiva", "arquivado o caso", "caso encerrado",
]
# Padrões de entidades exatas que forçam boost de similaridade
# IMPORTANTE: usar grupos não-capturantes (?:...) para que re.findall retorne
# o match completo, não apenas o grupo interno
ENTITY_PATTERNS = [
    r'BR-\d+',                              # rodovias federais (BR-470, BR-101, etc.)
    r'SC-\d+',                              # rodovias estaduais
    r'R\$\s*[\d.,]+\s*(?:milh[oõ]es|bilh[oõ]es|mil)?',  # valores monetários
    r'\b\d+\s*(?:km|quil[oô]metro[s]?)\b',  # distâncias
]


@dataclass
class NewsItem:
    id: str
    data: str  # ISO date (YYYY-MM-DD)
    manchete: str
    topico_slug: str
    embedding: list = field(default_factory=list)
    status: str = "aberto"  # aberto | monitorando | resolvido | arquivado
    mencoes: int = 1
    primeira_mencao: str = ""
    ultima_mencao: str = ""

    def to_dict(self):
        return asdict(self)


class FollowupTracker:
    def __init__(self, memory_path: str = MEMORY_PATH, embed_fn=None, model_name: str = EMBEDDING_MODEL):
        """
        embed_fn: função injetável que recebe uma string e retorna um vetor.
        Se não fornecida, usa sentence-transformers com o modelo especificado.
        model_name: modelo do sentence-transformers (padrão: paraphrase-multilingual-MiniLM-L12-v2, 384d, 118M params)
        """
        self.memory_path = memory_path
        
        if embed_fn:
            self.embed_fn = embed_fn
        elif SENTENCE_TRANSFORMERS_AVAILABLE:
            self._embedder = SentenceTransformer(model_name)
            self.embed_fn = self._sentence_transformers_embed
        else:
            self.embed_fn = self._fallback_embed
        
        self.items: list[NewsItem] = self._load()
    
    def _sentence_transformers_embed(self, text: str) -> list:
        """Usa sentence-transformers para gerar embedding denso (384d)"""
        return self._embedder.encode(text).tolist()

    # ── Persistência ──
    def _load(self) -> list[NewsItem]:
        if not os.path.exists(self.memory_path):
            return []
        with open(self.memory_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [NewsItem(**item) for item in raw]

    def save(self):
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump([item.to_dict() for item in self.items], f, ensure_ascii=False, indent=2)

    # ── Embedding placeholder (trocar por fastembed na integração real) ──
    @staticmethod
    def _fallback_embed(text: str) -> list:
        """Fallback burro só para o protótipo rodar sem dependências.
        Substituir por fastembed.TextEmbedding na integração — instalar
        como dependência própria deste projeto (pip install fastembed),
        já que NexusLocal roda em Docker isolado e não pode ser chamado
        daqui."""
        tokens = re.findall(r"\w+", text.lower())
        vec = [0.0] * 32
        for t in tokens:
            vec[hash(t) % 32] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _cosine_sim(a: list, b: list) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    
    @staticmethod
    def _extract_entities(texto: str) -> set:
        """Extrai entidades exatas (rodovias, valores monetários, etc.) do texto."""
        entities = set()
        for pattern in ENTITY_PATTERNS:
            matches = re.findall(pattern, texto, re.IGNORECASE)
            entities.update(matches)
        return entities
    
    def _similarity_with_entity_boost(self, emb_novo: list, emb_pool: list, texto_novo: str, texto_pool: str) -> float:
        """Calcula similaridade semântica e aplica boost se há overlap de entidades exatas."""
        sim_base = self._cosine_sim(emb_novo, emb_pool)
        
        # Extrair entidades de ambos os textos
        entidades_novo = self._extract_entities(texto_novo)
        entidades_pool = self._extract_entities(texto_pool)
        
        # Se há overlap de entidades, aplicar boost
        if entidades_novo and entidades_pool:
            overlap = entidades_novo & entidades_pool
            if overlap:
                # Boost mais agressivo: 0.10 por entidade compartilhada
                # Máximo boost: 0.20 (sobe similaridade em até 20 pontos)
                boost = min(0.20, len(overlap) * 0.10)
                return min(1.0, sim_base + boost)
        
        return sim_base

    # ── Manutenção do pool ──
    def _prune_expired(self, today: datetime):
        cutoff = today - timedelta(days=RETENTION_DAYS)
        for item in self.items:
            last = datetime.fromisoformat(item.ultima_mencao or item.data)
            if item.status != "arquivado" and last < cutoff:
                item.status = "arquivado"

    def _active_pool(self) -> list[NewsItem]:
        return [i for i in self.items if i.status in ("aberto", "monitorando")]

    # ── Detecção de fechamento (heurística inicial) ──
    @staticmethod
    def _looks_closed(texto: str) -> bool:
        low = texto.lower()
        return any(kw in low for kw in CLOSURE_KEYWORDS)

    # ── API principal ──
    def find_followups(self, noticias_hoje: list[dict], data_hoje: Optional[str] = None) -> list[dict]:
        """
        noticias_hoje: lista de dicts com pelo menos {"id", "manchete", "texto"}
        Retorna lista de sugestões de desdobramento no formato:
        {"noticia_id": ..., "desdobramento_de": ..., "primeira_mencao": ...,
         "mencoes_anteriores": N, "similaridade": float, "tipo": "automatico"|"possivel",
         "tag_sugerida": "[DESDOBRAMENTO: ...]"|"[POSSÍVEL DESDOBRAMENTO: ...]"}
        
        Lógica de três zonas:
        - similaridade >= SIMILARITY_THRESHOLD_HIGH: desdobramento automático
        - SIMILARITY_THRESHOLD_LOW <= similaridade < SIMILARITY_THRESHOLD_HIGH: possível desdobramento (requer confirmação)
        - similaridade < SIMILARITY_THRESHOLD_LOW: não é desdobramento
        """
        today = datetime.fromisoformat(data_hoje) if data_hoje else datetime.now()
        self._prune_expired(today)
        pool = self._active_pool()

        followups = []
        for noticia in noticias_hoje:
            texto = noticia.get("manchete", "") + " " + noticia.get("texto", "")
            emb = self.embed_fn(texto)
            melhor_match = None
            melhor_sim = 0.0
            melhor_texto_pool = ""
            
            for item in pool:
                # Usar similaridade com boost de entidade
                sim = self._similarity_with_entity_boost(emb, item.embedding, texto, item.manchete)
                if sim > melhor_sim:
                    melhor_sim = sim
                    melhor_match = item
                    melhor_texto_pool = item.manchete

            # Zona 1: acima do threshold alto → desdobramento automático
            if melhor_match and melhor_sim >= SIMILARITY_THRESHOLD_HIGH:
                melhor_match.mencoes += 1
                melhor_match.ultima_mencao = today.date().isoformat()
                if melhor_match.mencoes >= MIN_MENTIONS_FOR_MONITORING:
                    melhor_match.status = "monitorando"
                if self._looks_closed(texto):
                    melhor_match.status = "resolvido"

                followups.append({
                    "noticia_id": noticia["id"],
                    "desdobramento_de": melhor_match.id,
                    "topico_slug": melhor_match.topico_slug,
                    "primeira_mencao": melhor_match.primeira_mencao,
                    "mencoes_anteriores": melhor_match.mencoes - 1,
                    "similaridade": round(melhor_sim, 3),
                    "tipo": "automatico",
                    "tag_sugerida": f"[DESDOBRAMENTO: {melhor_match.topico_slug} — coberto desde {melhor_match.primeira_mencao}]",
                })
            
            # Zona 2: entre threshold baixo e alto → possível desdobramento (não atualiza pool)
            elif melhor_match and melhor_sim >= SIMILARITY_THRESHOLD_LOW:
                followups.append({
                    "noticia_id": noticia["id"],
                    "desdobramento_de": melhor_match.id,
                    "topico_slug": melhor_match.topico_slug,
                    "primeira_mencao": melhor_match.primeira_mencao,
                    "mencoes_anteriores": melhor_match.mencoes - 1,
                    "similaridade": round(melhor_sim, 3),
                    "tipo": "possivel",
                    "tag_sugerida": f"[POSSÍVEL DESDOBRAMENTO: {melhor_match.topico_slug} — confirmar manualmente]",
                })
                # Não atualiza mencoes/status do pool — requer confirmação humana
            
            # Zona 3: abaixo do threshold baixo → nova entrada no pool
            else:
                slug = self._slugify(noticia.get("manchete", noticia["id"]))
                novo = NewsItem(
                    id=noticia["id"],
                    data=today.date().isoformat(),
                    manchete=noticia.get("manchete", ""),
                    topico_slug=slug,
                    embedding=emb,
                    primeira_mencao=today.date().isoformat(),
                    ultima_mencao=today.date().isoformat(),
                )
                self.items.append(novo)

        return followups

    @staticmethod
    def _slugify(texto: str, max_words: int = 4) -> str:
        tokens = re.findall(r"\w+", texto.lower())
        return "-".join(tokens[:max_words]) if tokens else "sem-titulo"


# ── Teste manual rápido (roda isolado, não toca no pipeline real) ──
if __name__ == "__main__":
    tracker = FollowupTracker(memory_path="news_memory_test.json")

    dia1 = [{"id": "n1", "manchete": "Acidente grave interdita BR-470 em Blumenau", "texto": "Colisão entre dois caminhões bloqueia pista"}]
    r1 = tracker.find_followups(dia1, data_hoje="2026-07-25")
    print("Dia 1 (esperado: vazio, é a 1a menção):", r1)

    dia2 = [{"id": "n2", "manchete": "BR-470 segue interditada após acidente com caminhões", "texto": "Bloqueio na pista já dura mais de 24h"}]
    r2 = tracker.find_followups(dia2, data_hoje="2026-07-26")
    print("Dia 2 (esperado: desdobramento detectado):", r2)

    tracker.save()
    print("\nEstado final do pool:")
    for item in tracker.items:
        print(item.to_dict())
